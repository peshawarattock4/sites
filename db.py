import uuid
import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def sba() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets.get("SUPABASE_SERVICE_KEY") or st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

def get_settings():
    default_name = st.secrets.get("shop", {}).get("name", "My Store")
    try:
        res = sba().table("settings").select("*").limit(1).execute()
        if res.data and len(res.data) > 0:
            row = res.data[0]
            # Agar database mein shop_name nahi hai lekin name hai to use kar lo
            if not row.get("shop_name"):
                row["shop_name"] = row.get("name") or default_name
            return row
    except Exception:
        pass
    return {"shop_name": default_name, "announcement": "", "delivery_fee": 0, "free_over": 0}

def get_categories():
    try:
        res = sba().table("categories").select("*").execute()
        return res.data or []
    except Exception:
        return []

def get_products(only_sale=False, only_featured=False, search=None, category_id=None, limit=None):
    try:
        query = sba().table("products").select("*, categories(name, icon)")
        if only_sale:
            query = query.eq("on_sale", True)
        if only_featured:
            query = query.eq("is_featured", True)
        if category_id:
            query = query.eq("category_id", category_id)
        if search:
            query = query.ilike("title", f"%{search}%")
        if limit:
            query = query.limit(limit)
        
        res = query.order("created_at", desc=True).execute()
        items = []
        for p in (res.data or []):
            cat = p.get("categories") or {}
            p["category_name"] = cat.get("name", "")
            p["category_icon"] = cat.get("icon", "")
            p["cover"] = p["images"][0] if p.get("images") else ""
            items.append(p)
        return items
    except Exception:
        return []

def get_product(pid):
    try:
        res = sba().table("products").select("*, categories(name, icon)").eq("id", pid).single().execute()
        p = res.data
        if p:
            cat = p.get("categories") or {}
            p["category_name"] = cat.get("name", "")
            p["category_icon"] = cat.get("icon", "")
            p["cover"] = p["images"][0] if p.get("images") else ""
        return p
    except Exception:
        return None

def get_banners(active_only=True):
    try:
        q = sba().table("banners").select("*")
        if active_only:
            q = q.eq("is_active", True)
        res = q.execute()
        return res.data or []
    except Exception:
        return []

def save_banner(data):
    try:
        return sba().table("banners").insert(data).execute()
    except Exception as e:
        st.error(f"Banner save error: {e}")
        return None

def delete_banner(bid):
    try:
        return sba().table("banners").delete().eq("id", bid).execute()
    except Exception:
        return None

def create_order(payload):
    try:
        res = sba().table("orders").insert(payload).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return {"order_no": "1001"}

def search_orders(query: str):
    try:
        res = sba().table("orders").select("*").or_(f"order_no.eq.{query},phone.ilike.%{query}%,whatsapp.ilike.%{query}%").order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        try:
            res = sba().table("orders").select("*").ilike("phone", f"%{query}%").order("created_at", desc=True).execute()
            return res.data or []
        except Exception:
            return []

def get_messages(sid):
    try:
        res = sba().table("messages").select("*").eq("session_id", sid).order("created_at").execute()
        return res.data or []
    except Exception:
        return []

def send_message(sid, name, wa, sender, msg):
    try:
        sba().table("messages").insert({
            "session_id": sid,
            "customer_name": name,
            "customer_whatsapp": wa,
            "sender": sender,
            "message": msg
        }).execute()
    except Exception:
        pass

def upload_image(file, bucket="products"):
    try:
        file_bytes = file.getvalue()
        file_name = f"{uuid.uuid4().hex}.webp"
        sba().storage.from_(bucket).upload(file_name, file_bytes, {"content-type": file.type})
        return sba().storage.from_(bucket).get_public_url(file_name)
    except Exception:
        return None
