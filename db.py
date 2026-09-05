"""Supabase data layer — saara DB access yahan se hota hai."""
import uuid
import datetime as dt
import streamlit as st
from supabase import create_client, Client

BUCKET = "product-images"
PROD_SELECT = "*, categories(name, icon)"


# ------------------------------------------------------------------ clients
@st.cache_resource(show_spinner=False)
def _client(key_name: str) -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets[key_name])


def sb() -> Client:
    """Public (anon) client — sirf active catalog / settings read."""
    return _client("SUPABASE_ANON_KEY")


def sba() -> Client:
    """Service-role client. Streamlit server-side chalta hai, browser mein
    kabhi expose nahi hota. Chat, orders aur admin writes isi se."""
    return _client("SUPABASE_SERVICE_KEY")


def bust():
    """Admin ke kisi bhi write ke baad site turant live update ho jaye."""
    st.cache_data.clear()


def _safe(q: str) -> str:
    for ch in ",()%*":
        q = q.replace(ch, " ")
    return q.strip()


# ------------------------------------------------------------------ settings
@st.cache_data(ttl=15, show_spinner=False)
def get_settings() -> dict:
    shop = st.secrets.get("shop", {})
    out = {
        "shop_name": shop.get("name", "Shop"),
        "owner_whatsapp": shop.get("owner_whatsapp", ""),
        "delivery_fee": "0",
        "free_over": "0",
        "announcement": "",
    }
    try:
        for r in sb().table("settings").select("*").execute().data or []:
            if r.get("value") not in (None, ""):
                out[r["key"]] = r["value"]
    except Exception:
        pass
    return out


def save_setting(key: str, value):
    sba().table("settings").upsert({"key": key, "value": str(value)}).execute()
    bust()


# ------------------------------------------------------------------ categories
@st.cache_data(ttl=15, show_spinner=False)
def get_categories(active_only: bool = True) -> list:
    q = sba().table("categories").select("*")
    if active_only:
        q = q.eq("is_active", True)
    return q.order("sort_order").order("name").execute().data or []


def save_category(payload: dict, cid: str | None = None):
    if cid:
        sba().table("categories").update(payload).eq("id", cid).execute()
    else:
        sba().table("categories").insert(payload).execute()
    bust()


def delete_category(cid: str):
    sba().table("categories").delete().eq("id", cid).execute()
    bust()


# ------------------------------------------------------------------ products
@st.cache_data(ttl=15, show_spinner=False)
def get_products(search: str = "", category_id: str | None = None,
                 only_sale: bool = False, only_featured: bool = False,
                 limit: int = 120, active_only: bool = True) -> list:
    q = (sba() if not active_only else sb()).table("products").select(PROD_SELECT)
    if active_only:
        q = q.eq("is_active", True)
    if category_id:
        q = q.eq("category_id", category_id)
    if only_sale:
        q = q.not_.is_("sale_price", "null")
    if only_featured:
        q = q.eq("is_featured", True)
    s = _safe(search)
    if s:
        q = q.or_(f"title.ilike.%{s}%,description.ilike.%{s}%,offer_text.ilike.%{s}%")
    rows = q.order("created_at", desc=True).limit(limit).execute().data or []
    return [enrich(r) for r in rows]


@st.cache_data(ttl=15, show_spinner=False)
def get_product(pid: str) -> dict | None:
    r = sb().table("products").select(PROD_SELECT).eq("id", pid).limit(1).execute().data
    return enrich(r[0]) if r else None


def enrich(p: dict) -> dict:
    """Sale / discount fields compute karta hai."""
    price = float(p.get("price") or 0)
    sale = p.get("sale_price")
    sale = float(sale) if sale not in (None, "") else None
    on_sale = sale is not None and 0 < sale < price
    p["price"] = price
    p["sale_price"] = sale
    p["on_sale"] = on_sale
    p["final_price"] = sale if on_sale else price
    p["discount_pct"] = int(round((price - sale) / price * 100)) if on_sale and price else 0
    cat = p.get("categories") or {}
    p["category_name"] = cat.get("name") or "General"
    p["category_icon"] = cat.get("icon") or "🛍️"
    imgs = p.get("images") or []
    p["images"] = [i for i in imgs if i][:5]
    p["cover"] = p["images"][0] if p["images"] else ""
    p["highlights"] = p.get("highlights") or []
    return p


def save_product(payload: dict, pid: str | None = None):
    if pid:
        sba().table("products").update(payload).eq("id", pid).execute()
    else:
        sba().table("products").insert(payload).execute()
    bust()


def delete_product(pid: str):
    sba().table("products").delete().eq("id", pid).execute()
    bust()


# ------------------------------------------------------------------ banners
@st.cache_data(ttl=15, show_spinner=False)
def get_banners(active_only: bool = True) -> list:
    q = sba().table("banners").select("*")
    if active_only:
        q = q.eq("is_active", True)
    return q.order("sort_order").execute().data or []


def save_banner(payload: dict, bid: str | None = None):
    if bid:
        sba().table("banners").update(payload).eq("id", bid).execute()
    else:
        sba().table("banners").insert(payload).execute()
    bust()


def delete_banner(bid: str):
    sba().table("banners").delete().eq("id", bid).execute()
    bust()


# ------------------------------------------------------------------ storage
def upload_image(file, folder: str = "products") -> str:
    ext = (file.name.rsplit(".", 1)[-1] if "." in file.name else "jpg").lower()
    path = f"{folder}/{dt.date.today():%Y%m}/{uuid.uuid4().hex}.{ext}"
    sba().storage.from_(BUCKET).upload(
        path=path,
        file=file.getvalue(),
        file_options={"content-type": file.type or "image/jpeg", "upsert": "true"},
    )
    return sba().storage.from_(BUCKET).get_public_url(path).rstrip("?")


# ------------------------------------------------------------------ orders
def create_order(payload: dict) -> dict:
    """Order insert **service_role** (sba) se hota hai, anon se nahi.

    Wajah: `orders` par anon ki sirf INSERT policy hai, SELECT ki nahi. Magar
    PostgREST default `Prefer: return=representation` bhejta hai, yani
    `insert ... returning *` — aur RETURNING ke liye SELECT policy bhi chahiye
    hoti hai. Is liye anon client
    `42501 new row violates row-level security policy for table "orders"`
    phaink deta tha. Ye insert Streamlit ke server par chalta hai (browser mein
    key kabhi nahi jaati), is liye service key safe hai — chat_messages bhi
    isi tarah kaam karta hai. Faida: customers ko `orders` par koi bhi
    permission dene ki zaroorat nahi rehti.
    """
    data = {k: v for k, v in (payload or {}).items() if v is not None}
    try:
        res = sba().table("orders").insert(data).execute()
    except Exception as ex:
        # Purani DB mein `orders.email` column nahi hota
        # (migration_02_email.sql). Sirf ek optional column ki wajah se order
        # kabhi fail nahi hona chahiye -> usko hata kar dobara koshish.
        if "email" in data and "email" in str(ex).lower():
            data.pop("email", None)
            res = sba().table("orders").insert(data).execute()
        else:
            raise
    return (res.data or [{}])[0]


@st.cache_data(ttl=5, show_spinner=False)
def list_orders(status: str | None = None, limit: int = 300) -> list:
    q = sba().table("orders").select("*")
    if status and status != "all":
        q = q.eq("status", status)
    return q.order("created_at", desc=True).limit(limit).execute().data or []


def update_order_status(oid: str, status: str):
    sba().table("orders").update({"status": status}).eq("id", oid).execute()
    bust()


# ------------------------------------------------------------------ live chat
def send_message(session_id: str, sender: str, message: str,
                 name: str = "", whatsapp: str = ""):
    sba().table("chat_messages").insert({
        "session_id": session_id, "sender": sender, "message": message,
        "name": name, "whatsapp": whatsapp,
        "is_read": sender == "admin",
    }).execute()


def get_thread(session_id: str, limit: int = 200) -> list:
    return (sba().table("chat_messages").select("*")
            .eq("session_id", session_id)
            .order("created_at").limit(limit).execute().data or [])


def list_threads(limit: int = 800) -> list:
    rows = (sba().table("chat_messages").select("*")
            .order("created_at", desc=True).limit(limit).execute().data or [])
    threads: dict[str, dict] = {}
    for r in rows:                                    # newest -> oldest
        t = threads.setdefault(r["session_id"], {
            "session_id": r["session_id"], "name": "", "whatsapp": "",
            "last": r["message"], "last_at": r["created_at"], "unread": 0,
        })
        if r["sender"] == "user":
            t["name"] = t["name"] or (r.get("name") or "Guest")
            t["whatsapp"] = t["whatsapp"] or (r.get("whatsapp") or "")
            if not r.get("is_read"):
                t["unread"] += 1
    return sorted(threads.values(), key=lambda x: x["last_at"], reverse=True)


def mark_read(session_id: str):
    (sba().table("chat_messages").update({"is_read": True})
     .eq("session_id", session_id).eq("sender", "user")
     .eq("is_read", False).execute())


def unread_count() -> int:
    r = (sba().table("chat_messages").select("id", count="exact")
         .eq("sender", "user").eq("is_read", False).execute())
    return r.count or 0
