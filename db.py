"""Supabase data layer — saara DB access yahan se hota hai."""
import re
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


# ------------------------------------------------- schema-tolerant write layer
# Agar koi migration na chali ho to PostgREST kehta hai:
#   PGRST204  "Could not find the 'courier' column of 'orders' in the schema cache"
# Aisi surat mein poora order/product fail karne ke bajaye sirf wo column
# nikaal kar dobara koshish karte hain — site chalti rehti hai.
_MISSING_COL = re.compile(r"'([A-Za-z_][A-Za-z0-9_]*)' column", re.I)


def _without_missing(data: dict, ex: Exception):
    m = _MISSING_COL.search(str(ex))
    if not m:
        return None
    col = m.group(1)
    if col not in data:
        return None
    d = dict(data)
    d.pop(col, None)
    return d or None


def _insert(table: str, data: dict, tries: int = 8):
    d = dict(data)
    for _ in range(tries):
        try:
            return sba().table(table).insert(d).execute()
        except Exception as ex:
            nd = _without_missing(d, ex)
            if nd is None:
                raise
            d = nd
    return sba().table(table).insert(d).execute()


def _update(table: str, data: dict, key: str, val, tries: int = 8):
    d = dict(data)
    for _ in range(tries):
        try:
            return sba().table(table).update(d).eq(key, val).execute()
        except Exception as ex:
            nd = _without_missing(d, ex)
            if nd is None:
                raise
            d = nd
    return sba().table(table).update(d).eq(key, val).execute()


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
    # ---- admin-only cost fields (migration_03) — customer ko kahin nahi dikhte
    p["cost_price"] = float(p.get("cost_price") or 0)   # kharid / purchase price
    p["expense"] = float(p.get("expense") or 0)         # packing, ads, misc per unit
    p["unit_cost"] = p["cost_price"] + p["expense"]
    p["unit_profit"] = p["final_price"] - p["unit_cost"]
    p["margin_pct"] = (int(round(p["unit_profit"] / p["final_price"] * 100))
                       if p["final_price"] else 0)
    return p


def save_product(payload: dict, pid: str | None = None):
    if pid:
        _update("products", payload, "id", pid)
    else:
        _insert("products", payload)
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
    isi tarah kaam karta hai.
    """
    data = {k: v for k, v in (payload or {}).items() if v is not None}
    row = (_insert("orders", data).data or [{}])[0]
    if row.get("id"):
        add_order_event(row["id"], row.get("status") or "new", "Order receive ho gaya")
    bust()
    return row


@st.cache_data(ttl=5, show_spinner=False)
def list_orders(status: str | None = None, limit: int = 300) -> list:
    q = sba().table("orders").select("*")
    if status and status != "all":
        q = q.eq("status", status)
    return q.order("created_at", desc=True).limit(limit).execute().data or []


def update_order_status(oid: str, status: str, note: str = "",
                        courier: str = "", tracking_no: str = ""):
    """Status + courier/tracking save karta hai aur tracking history mein ek
    event likh deta hai — customer ko yehi timeline nazar aati hai."""
    data = {"status": status,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if (note or "").strip():
        data["status_note"] = note.strip()
    if (courier or "").strip():
        data["courier"] = courier.strip()
    if (tracking_no or "").strip():
        data["tracking_no"] = tracking_no.strip()
    _update("orders", data, "id", oid)
    add_order_event(oid, status, note)
    bust()


# --------------------------------------------------------- tracking (customer)
def add_order_event(order_id: str, status: str, note: str = ""):
    """order_events table na bhi ho to order kabhi fail nahi hona chahiye."""
    try:
        _insert("order_events", {"order_id": order_id, "status": status,
                                 "note": (note or "").strip() or None})
    except Exception:
        pass


def get_order_events(order_id: str, limit: int = 40) -> list:
    try:
        return (sba().table("order_events").select("*")
                .eq("order_id", order_id)
                .order("created_at").limit(limit).execute().data or [])
    except Exception:
        return []


def find_orders(phone: str, order_no: str = "", limit: int = 20) -> list:
    """Customer apne mobile number se apne orders dekh sakta hai.

    Read **service key** se hota hai (server-side), is liye `orders` par koi
    public SELECT policy dene ki zaroorat nahi — kisi aur ka data leak nahi
    hota. Number ke aakhri 10 digits par match karte hain taake 0300…,
    +92300…, 92300… sab chal jayein.
    """
    tail = re.sub(r"\D", "", str(phone or ""))[-10:]
    if len(tail) < 10:
        return []
    no = re.sub(r"\D", "", str(order_no or ""))
    rows = []
    try:
        q = sba().table("orders").select("*")
        if no:
            try:
                q = q.eq("order_no", int(no))
            except ValueError:
                pass
        rows = (q.or_(f"phone.ilike.*{tail},whatsapp.ilike.*{tail}")
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception:
        rows = []
    if not rows:
        rows = _scan_orders(tail, no, limit)
    return rows


def _scan_orders(tail: str, no: str = "", limit: int = 20, scan: int = 1500) -> list:
    """Fallback: number dashes/spaces ke sath save hua ho to ilike match nahi
    karta — is liye recent orders utha kar sirf digits compare karte hain."""
    try:
        rows = (sba().table("orders").select("*")
                .order("created_at", desc=True).limit(scan).execute().data or [])
    except Exception:
        return []
    out = []
    for r in rows:
        if no and re.sub(r"\D", "", str(r.get("order_no") or "")).lstrip("0") \
                != no.lstrip("0"):
            continue
        for f in ("phone", "whatsapp"):
            if tail in re.sub(r"\D", "", str(r.get(f) or "")):
                out.append(r)
                break
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------- profit / loss (admin)
@st.cache_data(ttl=20, show_spinner=False)
def list_orders_range(start: str = "", end: str = "", statuses: tuple = (),
                      limit: int = 5000) -> list:
    q = sba().table("orders").select("*")
    if start:
        q = q.gte("created_at", start)
    if end:
        q = q.lte("created_at", end)
    if statuses:
        q = q.in_("status", list(statuses))
    return q.order("created_at", desc=True).limit(limit).execute().data or []


def order_profit(o: dict, cost_map: dict) -> dict:
    """Ek order ka revenue / cost / profit.

    Cost pehle order ke apne snapshot se (`items[].cost` + `items[].expense`,
    jo checkout ke waqt save hoti hai) — is liye baad mein purchase price badle
    to purani reports nahi badalti. Snapshot na ho to products table ki
    current cost use hoti hai.
    """
    rev = cst = 0.0
    lines, unknown = [], set()
    for it in (o.get("items") or []):
        qty = float(it.get("qty") or 0)
        line_rev = float(it.get("line_total") or 0)
        c, x = it.get("cost"), it.get("expense")
        if c is None or x is None:
            m = cost_map.get(it.get("product_id")) or {}
            c = m.get("cost_price", 0.0) if c is None else c
            x = m.get("expense", 0.0) if x is None else x
        unit = float(c or 0) + float(x or 0)
        if unit <= 0:
            unknown.add(str(it.get("title") or "?"))
        line_cost = unit * qty
        rev += line_rev
        cst += line_cost
        lines.append({"product_id": it.get("product_id"),
                      "title": str(it.get("title") or "?"), "qty": qty,
                      "revenue": line_rev, "cost": line_cost,
                      "profit": line_rev - line_cost})
    return {"revenue": rev, "cost": cst, "profit": rev - cst,
            "lines": lines, "unknown": unknown}


def profit_report(start: str = "", end: str = "", statuses: tuple = ()) -> dict:
    """Monthly aur per-product profit/loss. Delivery fee alag rakhi jaati hai
    (wo courier ko chali jaati hai, is liye profit mein nahi ginte)."""
    orders = list_orders_range(start, end, tuple(statuses))
    cmap = {p["id"]: p for p in get_products(limit=1000, active_only=False)}
    tot = {"orders": len(orders), "revenue": 0.0, "cost": 0.0, "profit": 0.0,
           "delivery": 0.0, "margin": 0}
    months, prods, no_cost = {}, {}, set()
    for o in orders:
        r = order_profit(o, cmap)
        tot["revenue"] += r["revenue"]
        tot["cost"] += r["cost"]
        tot["profit"] += r["profit"]
        tot["delivery"] += float(o.get("delivery_fee") or 0)
        no_cost |= r["unknown"]
        mk = str(o.get("created_at") or "")[:7] or "—"
        m = months.setdefault(mk, {"month": mk, "orders": 0, "revenue": 0.0,
                                   "cost": 0.0, "profit": 0.0})
        m["orders"] += 1
        for k in ("revenue", "cost", "profit"):
            m[k] += r[k]
        for ln in r["lines"]:
            key = ln["product_id"] or ln["title"]
            d = prods.setdefault(key, {"title": ln["title"], "qty": 0.0,
                                       "revenue": 0.0, "cost": 0.0, "profit": 0.0})
            d["qty"] += ln["qty"]
            for k in ("revenue", "cost", "profit"):
                d[k] += ln[k]
    if tot["revenue"]:
        tot["margin"] = int(round(tot["profit"] / tot["revenue"] * 100))
    return {"totals": tot,
            "months": sorted(months.values(), key=lambda x: x["month"], reverse=True),
            "products": sorted(prods.values(), key=lambda x: x["profit"], reverse=True),
            "no_cost": sorted(no_cost)}


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
