import hashlib
import hmac
import re

import streamlit as st

st.set_page_config(page_title="Admin Portal", page_icon="🔐", layout="wide",
                   initial_sidebar_state="collapsed")

import db
from styles import inject_css
from ui import money, wa_link, chat_html, section, empty, e

inject_css()
CUR = st.secrets.get("shop", {}).get("currency", "Rs")
ss = st.session_state
ss.setdefault("admin_ok", False)
ss.setdefault("tries", 0)
ss.setdefault("thread", None)


# ================================================================== LOGIN
def login_gate() -> bool:
    if ss.admin_ok:
        return True

    cfg = st.secrets.get("admin", {})
    want_u = cfg.get("username", "")
    want_h = cfg.get("password_sha256", "")

    st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
    _, m, _ = st.columns([1, 1.25, 1])
    with m:
        st.markdown("<div class='brand' style='justify-content:center'>"
                    "<div class='brand-logo'>🔐</div>"
                    "<div class='brand-name'>Admin Portal</div></div><br>",
                    unsafe_allow_html=True)

        # Secrets set na hon to saaf error — warna login bewajah fail hota rehta hai
        if not want_u or not want_h:
            st.error("Admin credentials set nahi hain. Streamlit Cloud par "
                     "**Manage app → Settings → Secrets** mein ye daalein:")
            st.code('[admin]\nusername = "admin"\n'
                    'password_sha256 = "<sha256 hash>"', language="toml")
            st.caption("Hash banane ke liye apne PC par ye chalayein:")
            st.code('python -c "import hashlib;'
                    "print(hashlib.sha256('MeraStrongPass123!'.encode()).hexdigest())\"",
                    language="bash")
            return False

        if ss.tries >= 5:
            st.error("Bohat zyada ghalat koshishein. Thori dair baad page reload karein.")
            return False

        with st.form("lg"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                got_h = hashlib.sha256(p.encode()).hexdigest()
                ok_u = hmac.compare_digest(u.strip(), want_u)
                ok_p = hmac.compare_digest(got_h, want_h)
                if ok_u and ok_p:
                    ss.admin_ok = True
                    ss.tries = 0
                    st.rerun()
                else:
                    ss.tries += 1
                    st.error(f"Ghalat credentials. ({5 - ss.tries} koshishein baqi)")
    return False


if not login_gate():
    st.stop()

# ================================================================== SHELL
S = db.get_settings()
h1, h2 = st.columns([5, 1], vertical_alignment="center")
h1.markdown(f"<div class='brand'><div class='brand-logo'>🛠️</div><div>"
            f"<div class='brand-name'>{e(S['shop_name'])} — Admin</div>"
            f"<div class='brand-tag'>Jo bhi add/edit karenge, site par turant live</div>"
            f"</div></div>", unsafe_allow_html=True)
if h2.button("Logout", use_container_width=True):
    ss.admin_ok = False
    st.rerun()
st.divider()

cats = db.get_categories(active_only=False)
CAT_MAP = {c["name"]: c["id"] for c in cats}
tabs = st.tabs(["📊 Dashboard", "📦 Products", "🗂️ Categories", "🖼️ Banners",
                "🧾 Orders", "💬 Live Messages", "⚙️ Settings"])

# ================================================================== DASHBOARD
with tabs[0]:
    allp = db.get_products(limit=500, active_only=False)
    orders = db.list_orders()
    k = st.columns(4)
    k[0].metric("Products", len(allp))
    k[1].metric("Categories", len(cats))
    k[2].metric("Orders", len(orders),
                f"{len([o for o in orders if o['status'] == 'new'])} new")
    k[3].metric("Unread messages", db.unread_count())
    section("🔥 Sale par products")
    sale = [p for p in allp if p["on_sale"]]
    if sale:
        st.dataframe([{"Title": p["title"], "Price": p["price"],
                       "Sale": p["sale_price"], "Off %": p["discount_pct"],
                       "Stock": p["stock"]} for p in sale],
                     use_container_width=True, hide_index=True)
    else:
        empty("Abhi kisi product par sale nahi. Sale price add karein — "
              "banner automatic slide karega.")

# ================================================================== PRODUCTS
with tabs[1]:
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        section("➕ Naya product add karein")
        with st.form("np", clear_on_submit=True):
            t = st.text_input("Title *")
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Category *", ["—"] + list(CAT_MAP))
            badge = c2.text_input("Badge (NEW / HOT)")
            p1, p2, p3 = st.columns(3)
            price = p1.number_input("Price *", 0.0, step=50.0)
            sale_p = p2.number_input("Sale price (0 = no sale)", 0.0, step=50.0)
            stock = p3.number_input("Stock", 0, step=1, value=10)
            offer = st.text_input("Offer text (banner par dikhega)",
                                  placeholder="Buy 1 Get 1 Free")
            desc = st.text_area("Description", height=110)
            hl = st.text_area("Highlights — har line ek point", height=90,
                              placeholder="100% original\nFree delivery\n7 din return")
            st.markdown("**Images — max 5**")
            files = st.file_uploader(
                "Upload", accept_multiple_files=True,
                type=["png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"],
                label_visibility="collapsed")
            urls = st.text_area("…ya image URLs (har line ek URL)", height=70)
            f1, f2 = st.columns(2)
            feat = f1.checkbox("Featured", value=False)
            act = f2.checkbox("Active (site par live)", value=True)
            if st.form_submit_button("💾 Save & Publish", type="primary",
                                     use_container_width=True):
                if len(t.strip()) < 3 or cat == "—" or price <= 0:
                    st.error("Title, Category aur Price zaroori hain.")
                else:
                    imgs = []
                    for f in (files or [])[:5]:
                        try:
                            imgs.append(db.upload_image(f))
                        except Exception as ex:
                            st.warning(f"{f.name} upload fail: {ex}")
                    imgs += [u.strip() for u in urls.splitlines() if u.strip()]
                    db.save_product({
                        "title": t.strip(), "description": desc.strip(),
                        "highlights": [h.strip() for h in hl.splitlines() if h.strip()],
                        "images": imgs[:5], "price": float(price),
                        "sale_price": float(sale_p) if sale_p > 0 else None,
                        "stock": int(stock), "category_id": CAT_MAP[cat],
                        "offer_text": offer.strip() or None,
                        "badge": badge.strip() or None,
                        "is_featured": feat, "is_active": act,
                    })
                    st.success("✅ Product live ho gaya!")
                    st.rerun()

    with right:
        section("✏️ Existing products")
        plist = db.get_products(limit=300, active_only=False)
        if not plist:
            empty("Koi product nahi.")
        else:
            pick = st.selectbox(
                "Select", plist,
                format_func=lambda p: f"{p['title']} — {money(p['final_price'], CUR)}"
                                      f"{'' if p['is_active'] else '  (hidden)'}")
            with st.form("ep"):
                t = st.text_input("Title", pick["title"])
                names = list(CAT_MAP)
                idx = names.index(pick["category_name"]) if pick["category_name"] in names else 0
                cat = st.selectbox("Category", names, index=idx) if names else None
                e1, e2, e3 = st.columns(3)
                price = e1.number_input("Price", 0.0, value=float(pick["price"]), step=50.0)
                sale_p = e2.number_input("Sale price", 0.0,
                                         value=float(pick["sale_price"] or 0), step=50.0)
                stock = e3.number_input("Stock", 0, value=int(pick["stock"] or 0), step=1)
                offer = st.text_input("Offer text", pick.get("offer_text") or "")
                desc = st.text_area("Description", pick.get("description") or "", height=90)
                hl = st.text_area("Highlights", "\n".join(pick["highlights"]), height=80)
                extra = st.file_uploader(
                    "Nayi images add karein", accept_multiple_files=True,
                    type=["png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"])
                keep = st.multiselect("Mojooda images rakhein", pick["images"],
                                      default=pick["images"])
                g1, g2 = st.columns(2)
                feat = g1.checkbox("Featured", value=bool(pick["is_featured"]))
                act = g2.checkbox("Active", value=bool(pick["is_active"]))
                u1, u2 = st.columns(2)
                upd = u1.form_submit_button("💾 Update", type="primary",
                                            use_container_width=True)
                dele = u2.form_submit_button("🗑 Delete", use_container_width=True)
            if upd:
                imgs = list(keep)
                for f in (extra or []):
                    if len(imgs) >= 5:
                        break
                    try:
                        imgs.append(db.upload_image(f))
                    except Exception as ex:
                        st.warning(f"{f.name}: {ex}")
                db.save_product({
                    "title": t.strip(), "description": desc.strip(),
                    "highlights": [h.strip() for h in hl.splitlines() if h.strip()],
                    "images": imgs[:5], "price": float(price),
                    "sale_price": float(sale_p) if sale_p > 0 else None,
                    "stock": int(stock),
                    "category_id": CAT_MAP.get(cat) if cat else None,
                    "offer_text": offer.strip() or None,
                    "is_featured": feat, "is_active": act,
                }, pick["id"])
                st.success("Update ho gaya.")
                st.rerun()
            if dele:
                db.delete_product(pick["id"])
                st.warning("Delete ho gaya.")
                st.rerun()

# ================================================================== CATEGORIES
with tabs[2]:
    a, b = st.columns([1, 1.3], gap="large")
    with a:
        section("➕ Category add")
        with st.form("nc", clear_on_submit=True):
            n = st.text_input("Category name *")
            ic = st.text_input("Icon (emoji)", "🛍️")
            so = st.number_input("Sort order", 0, step=1)
            if st.form_submit_button("💾 Add", type="primary", use_container_width=True):
                if len(n.strip()) < 2:
                    st.error("Naam likhein.")
                else:
                    db.save_category({"name": n.strip(), "icon": ic.strip() or "🛍️",
                                      "sort_order": int(so), "is_active": True})
                    st.success("Category live — user ko turant nazar aayegi.")
                    st.rerun()
    with b:
        section("🗂️ Mojooda categories")
        if not cats:
            empty("Koi category nahi.")
        for c in cats:
            r = st.columns([2.6, 1.1, 0.8], vertical_alignment="center")
            r[0].markdown(f"**{c.get('icon', '')} {e(c['name'])}**")
            new_act = r[1].toggle("Live", value=bool(c["is_active"]), key=f"tg{c['id']}")
            if new_act != bool(c["is_active"]):
                db.save_category({"is_active": new_act}, c["id"])
                st.rerun()
            if r[2].button("🗑", key=f"dc{c['id']}"):
                db.delete_category(c["id"])
                st.rerun()

# ================================================================== BANNERS
with tabs[3]:
    st.info("Sale/Offer banners **automatic** ban jaate hain un products se jin par "
            "sale price ya offer text hai. Neeche sirf extra custom banner add karein.")
    a, b = st.columns([1, 1.2], gap="large")
    with a:
        with st.form("nb", clear_on_submit=True):
            t = st.text_input("Banner title")
            s = st.text_input("Subtitle")
            f = st.file_uploader("Banner image", type=["png", "jpg", "jpeg", "webp"])
            c1, c2 = st.columns(2)
            g1 = c1.color_picker("Gradient from", "#1e1b4b")
            g2 = c2.color_picker("Gradient to", "#4338ca")
            if st.form_submit_button("💾 Add banner", type="primary",
                                     use_container_width=True):
                url = db.upload_image(f, "banners") if f else None
                db.save_banner({"title": t.strip(), "subtitle": s.strip(),
                                "image_url": url, "bg_from": g1, "bg_to": g2,
                                "is_active": True})
                st.success("Banner live.")
                st.rerun()
    with b:
        for bn in db.get_banners(active_only=False):
            r = st.columns([3, 0.8], vertical_alignment="center")
            r[0].markdown(f"**{e(bn.get('title'))}** — {e(bn.get('subtitle'))}")
            if r[1].button("🗑", key=f"db{bn['id']}"):
                db.delete_banner(bn["id"])
                st.rerun()

# ================================================================== ORDERS
with tabs[4]:
    STATUSES = ["new", "confirmed", "shipped", "delivered", "cancelled"]
    f = st.selectbox("Filter", ["all"] + STATUSES)
    orders = db.list_orders(f)
    if not orders:
        empty("Koi order nahi.")
    for o in orders:
        with st.expander(f"#{o['order_no']} • {o['customer_name']} • "
                         f"{money(o['total'], CUR)} • {o['status'].upper()} • "
                         f"{(o['created_at'] or '')[:16]}"):
            c1, c2 = st.columns([1.3, 1])
            with c1:
                st.markdown(f"**📞 Phone:** {e(o['phone'])}  \n"
                            f"**💬 WhatsApp:** {e(o['whatsapp'])}  \n"
                            f"**🏙️ City:** {e(o.get('city'))}  \n"
                            f"**📍 Address:** {e(o['address'])}  \n"
                            f"**📝 Note:** {e(o.get('note') or '—')}")
                st.dataframe([{"Item": i["title"], "Qty": i["qty"],
                               "Price": i["price"], "Total": i["line_total"]}
                              for i in (o["items"] or [])],
                             use_container_width=True, hide_index=True)
            with c2:
                stt = st.selectbox("Status", STATUSES,
                                   index=STATUSES.index(o["status"]), key=f"s{o['id']}")
                if st.button("Update status", key=f"u{o['id']}", use_container_width=True):
                    db.update_order_status(o["id"], stt)
                    st.rerun()
                msg = (f"Assalam-o-Alaikum {o['customer_name']}! Aap ka order "
                       f"#{o['order_no']} ({money(o['total'], CUR)}) confirm ho gaya hai. "
                       f"Shukriya!")
                st.markdown(f"<a class='wa' style='position:static;display:inline-flex' "
                            f"href='{wa_link(o['whatsapp'], msg)}' target='_blank'>"
                            f"💬 Customer ko WhatsApp</a>", unsafe_allow_html=True)

# ================================================================== LIVE CHAT
with tabs[5]:
    section("💬 Live customer messages", "har 5 second auto-refresh")

    @st.fragment(run_every=5)
    def inbox():
        threads = db.list_threads()
        if not threads:
            empty("Abhi koi message nahi.")
            return
        left, right = st.columns([1, 1.7], gap="large")
        with left:
            for t in threads:
                badge = f" 🔴{t['unread']}" if t["unread"] else ""
                if st.button(f"{t['name'] or 'Guest'}{badge}\n{t['last'][:34]}",
                             key=f"th{t['session_id']}", use_container_width=True):
                    ss.thread = t["session_id"]
                    db.mark_read(t["session_id"])
        with right:
            sid = ss.thread or threads[0]["session_id"]
            cur = next((x for x in threads if x["session_id"] == sid), threads[0])
            st.markdown(f"**👤 {e(cur['name'] or 'Guest')}** — {e(cur['whatsapp'])}")
            if cur["whatsapp"]:
                st.markdown(f"<a class='wa' style='position:static;display:inline-flex' "
                            f"href='{wa_link(cur['whatsapp'], 'Assalam-o-Alaikum!')}' "
                            f"target='_blank'>💬 WhatsApp</a>", unsafe_allow_html=True)
            st.markdown(chat_html(db.get_thread(sid)), unsafe_allow_html=True)
            with st.form(f"rp{sid}", clear_on_submit=True):
                r = st.text_input("Reply")
                if st.form_submit_button("Send", type="primary"):
                    if r.strip():
                        db.send_message(sid, "admin", r.strip())
                        db.mark_read(sid)
                        st.rerun()

    inbox()

# ================================================================== SETTINGS
with tabs[6]:
    section("⚙️ Shop settings")
    with st.form("stg"):
        sn = st.text_input("Shop name", S["shop_name"])
        ow = st.text_input("Owner WhatsApp (92XXXXXXXXXX)", S["owner_whatsapp"])
        c1, c2 = st.columns(2)
        df = c1.number_input("Delivery fee", 0.0,
                             value=float(S.get("delivery_fee") or 0), step=50.0)
        fo = c2.number_input("Free delivery over", 0.0,
                             value=float(S.get("free_over") or 0), step=500.0)
        an = st.text_area("Announcement (top scrolling bar)",
                          S.get("announcement", ""), height=80)
        if st.form_submit_button("💾 Save settings", type="primary",
                                 use_container_width=True):
            if not (10 <= len(re.sub(r"\D", "", ow)) <= 13):
                st.error("WhatsApp number sahi nahi.")
            else:
                for k, v in {"shop_name": sn, "owner_whatsapp": ow,
                             "delivery_fee": df, "free_over": fo,
                             "announcement": an}.items():
                    db.save_setting(k, v)
                st.success("Save ho gaya — site par live.")
                st.rerun()
