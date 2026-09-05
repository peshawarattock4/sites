import csv
import datetime as dt
import hashlib
import hmac
import io
import re

import streamlit as st

st.set_page_config(page_title="Admin Portal", page_icon="🔐", layout="wide",
                   initial_sidebar_state="collapsed")

import db
import notify
import social
from styles import inject_css
from ui import money, wa_link, chat_html, section, empty, e

inject_css()
CUR = st.secrets.get("shop", {}).get("currency", "Rs")
ss = st.session_state
ss.setdefault("admin_ok", False)
ss.setdefault("admin_who", "")
ss.setdefault("tries", 0)
ss.setdefault("thread", None)
ss.setdefault("flash", "")
ss.setdefault("img_blob", None)


# ================================================================== LOGIN
def _auth() -> dict:
    try:
        return dict(st.secrets.get("auth", {}) or {})
    except Exception:
        return {}


def _google_section():
    """[auth.google] table agar mojood hai to wo, warna None.
    (st.secrets nested tables plain `dict` nahi hote, is liye duck-typing.)"""
    g = _auth().get("google")
    try:
        if g is not None and hasattr(g, "get") and g.get("client_id"):
            return dict(g)
    except Exception:
        pass
    return None


def google_ready() -> bool:
    """[auth] block sahi bhara hua hai?"""
    a = _auth()
    if not (a.get("redirect_uri") and a.get("cookie_secret")):
        return False
    g = _google_section() or a
    return bool(g.get("client_id") and g.get("client_secret"))


def _claim(u, key, default=None):
    """Google token ka field — missing ho to crash na ho."""
    try:
        v = getattr(u, key)
    except Exception:
        return default
    return default if v is None else v


def allowed_emails() -> set:
    """Sirf ye Gmail/Google accounts admin portal khol sakte hain."""
    cfg = st.secrets.get("admin", {})
    v = cfg.get("allowed_emails", [])
    if isinstance(v, str):
        v = v.replace(";", ",").split(",")
    return {str(x).strip().lower() for x in (v or []) if str(x).strip()}


def google_user():
    """Signed-in Google user, warna None (auth set na ho to bhi None)."""
    try:
        u = st.user
        return u if bool(getattr(u, "is_logged_in", False)) else None
    except Exception:
        return None


def sign_out():
    ss.admin_ok = False
    ss.admin_who = ""
    if google_user() is not None:
        try:
            st.logout()
            return
        except Exception:
            pass
    st.rerun()


def login_gate() -> bool:
    if ss.admin_ok:
        return True

    cfg = st.secrets.get("admin", {})
    want_u = cfg.get("username", "")
    want_h = cfg.get("password_sha256", "")
    allow = allowed_emails()

    st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
    _, m, _ = st.columns([1, 1.25, 1])
    with m:
        st.markdown("<div class='brand' style='justify-content:center'>"
                    "<div class='brand-logo'>🔐</div>"
                    "<div class='brand-name'>Admin Portal</div></div><br>",
                    unsafe_allow_html=True)

        # ---------------------------------------- A) Google / Gmail se sign-in
        gu = google_user()
        if gu is not None:
            em = str(_claim(gu, "email", "") or "").strip().lower()
            verified = _claim(gu, "email_verified", True)
            if not allow:
                # Allow-list khali = kisi ko andar na aane dein, warna har Gmail
                # wala admin portal khol lega.
                st.error("Google sign-in ho gaya, magar allow-list khali hai. "
                         "Secrets mein ye add karein, phir dobara try karein:")
                st.code('[admin]\nallowed_emails = ["' + (em or "aap@gmail.com") + '"]',
                        language="toml")
            elif em in allow and verified is not False:
                ss.admin_ok = True
                ss.admin_who = em
                ss.tries = 0
                st.rerun()
            else:
                st.error("**" + em + "** is admin portal ke liye allowed nahi hai.")
            if st.button("Sign out / doosra account", use_container_width=True):
                sign_out()
            return False

        if google_ready():
            if st.button("🔓  Google / Gmail se sign in", type="primary",
                         use_container_width=True):
                if _google_section() is not None:
                    st.login("google")          # [auth.google] wala form
                else:
                    st.login()                  # sab kuch seedha [auth] mein
            st.caption("Sign-in ke baad Google aap ko site ke **home page** par wapas "
                       "bhejta hai — wahan se dobara `/admin` khol lein, seedha andar "
                       "aa jayenge.")
            st.markdown("<div style='text-align:center;color:#94a3b8;margin:8px 0'>"
                        "— ya —</div>", unsafe_allow_html=True)

        # ---------------------------------------- B) Username + password
        box = st.expander("🔑 Password se login") if google_ready() else st.container()
        with box:
            if not want_u or not want_h:
                if google_ready():
                    st.caption("Password login set nahi hai — sirf Google sign-in chalega.")
                else:
                    st.error("Admin credentials set nahi hain. Streamlit Cloud par "
                             "**Manage app → Settings → Secrets** mein ye daalein:")
                    st.code('[admin]\nusername = "admin"\n'
                            'password_sha256 = "<sha256 hash>"', language="toml")
                    st.caption("Hash banane ke liye apne PC par ye chalayein:")
                    st.code('python -c "import hashlib;'
                            "print(hashlib.sha256('MeraStrongPass123!'.encode()).hexdigest())\"",
                            language="bash")
            elif ss.tries >= 5:
                st.error("Bohat zyada ghalat koshishein. Thori dair baad page reload karein.")
            else:
                with st.form("lg"):
                    u = st.text_input("Username")
                    p = st.text_input("Password", type="password")
                    if st.form_submit_button("Login", type="primary",
                                             use_container_width=True):
                        got_h = hashlib.sha256(p.encode()).hexdigest()
                        ok_u = hmac.compare_digest(u.strip(), want_u)
                        ok_p = hmac.compare_digest(got_h, want_h)
                        if ok_u and ok_p:
                            ss.admin_ok = True
                            ss.admin_who = u.strip()
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
who = f"👤 {e(ss.admin_who)}  •  " if ss.admin_who else ""
h1.markdown(f"<div class='brand'><div class='brand-logo'>🛠️</div><div>"
            f"<div class='brand-name'>{e(S['shop_name'])} — Admin</div>"
            f"<div class='brand-tag'>{who}Jo bhi add/edit karenge, site par turant live"
            f"</div></div></div>", unsafe_allow_html=True)
if h2.button("Logout", use_container_width=True):
    sign_out()
st.divider()

if ss.flash:
    st.info(ss.flash)
    ss.flash = ""

cats = db.get_categories(active_only=False)
CAT_MAP = {c["name"]: c["id"] for c in cats}
tabs = st.tabs(["📊 Dashboard", "📦 Products", "🗂️ Categories", "🖼️ Banners",
                "🧾 Orders", "💰 Profit / Loss", "💬 Live Messages",
                "📣 Promote", "⚙️ Settings"])
STATUSES = ["new", "confirmed", "shipped", "delivered", "cancelled"]
# Profit ke liye default: cancelled orders nahi ginte
COUNTED = ("new", "confirmed", "shipped", "delivered")

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

    _t = dt.date.today()
    _mtd = db.profit_report(str(_t.replace(day=1)), str(_t) + "T23:59:59", COUNTED)
    _T = _mtd["totals"]
    section("💰 Is mahine ka hisaab", _t.strftime("%B %Y") + " — cancelled orders ke baghair")
    j = st.columns(4)
    j[0].metric("Orders", _T["orders"])
    j[1].metric("Revenue", money(_T["revenue"], CUR))
    j[2].metric("Cost", money(_T["cost"], CUR))
    j[3].metric("Profit", money(_T["profit"], CUR), str(_T["margin"]) + "% margin")
    st.caption("Poori tafseel **💰 Profit / Loss** tab mein.")

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
            b1, b2 = st.columns(2)
            cost = b1.number_input("Purchase price (kharid) — sirf admin", 0.0,
                                   step=50.0,
                                   help="Ye customer ko kahin nahi dikhta. Profit "
                                        "isi se calculate hota hai.")
            exp = b2.number_input("Expense per piece (packing/ads) — sirf admin",
                                  0.0, step=10.0,
                                  help="Har piece par aane wala extra kharcha.")
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
                        "cost_price": float(cost), "expense": float(exp),
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
                k1, k2 = st.columns(2)
                cost = k1.number_input("Purchase price (kharid)", 0.0,
                                       value=float(pick.get("cost_price") or 0),
                                       step=50.0)
                exp = k2.number_input("Expense per piece", 0.0,
                                      value=float(pick.get("expense") or 0), step=10.0)
                st.caption("Is waqt ek piece par profit: **"
                           + money(pick.get("unit_profit") or 0, CUR) + "**  ("
                           + str(pick.get("margin_pct") or 0) + "% margin)  •  "
                           "purchase price 0 ho to profit report ghalat aayegi")
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
                    "cost_price": float(cost), "expense": float(exp),
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
    f = st.selectbox("Filter", ["all"] + STATUSES)
    cost_map = {p["id"]: p for p in db.get_products(limit=1000, active_only=False)}
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
                            f"**📧 Email:** {e(o.get('email') or '—')}  \n"
                            f"**🏙️ City:** {e(o.get('city'))}  \n"
                            f"**📍 Address:** {e(o['address'])}  \n"
                            f"**📝 Note:** {e(o.get('note') or '—')}")
                st.dataframe([{"Item": i["title"], "Qty": i["qty"],
                               "Price": i["price"], "Total": i["line_total"]}
                              for i in (o["items"] or [])],
                             use_container_width=True, hide_index=True)
                pr = db.order_profit(o, cost_map)
                st.markdown("<div class='kv'><span>💵 Revenue (items)</span><b>"
                            + money(pr["revenue"], CUR) + "</b></div>"
                            "<div class='kv'><span>📦 Cost (kharid + expense)</span><b>"
                            + money(pr["cost"], CUR) + "</b></div>"
                            "<div class='kv'><span>📈 Profit</span><span class='tot'>"
                            + money(pr["profit"], CUR) + "</span></div>",
                            unsafe_allow_html=True)
                if pr["unknown"]:
                    st.caption("⚠️ Purchase price set nahi: "
                               + ", ".join(sorted(pr["unknown"])[:6]))
                ev = db.get_order_events(o["id"])
                if ev:
                    st.caption("📜 " + "  |  ".join(
                        str(x.get("created_at") or "")[:16].replace("T", " ")
                        + " " + str(x.get("status") or "").upper()
                        + ((" — " + str(x.get("note"))) if (x.get("note") or "") else "")
                        for x in ev))
            with c2:
                stt = st.selectbox("Status", STATUSES,
                                   index=STATUSES.index(o["status"]), key=f"s{o['id']}")
                crr = st.text_input("Courier (TCS / Leopards / M&P …)",
                                    o.get("courier") or "", key=f"c{o['id']}")
                trk = st.text_input("Tracking number (courier ka)",
                                    o.get("tracking_no") or "", key=f"t{o['id']}")
                nte = st.text_input("Note — customer ko tracking page par dikhega",
                                    "", key=f"n{o['id']}",
                                    placeholder="Kal shaam tak deliver ho jayega")
                has_mail = bool(o.get("email"))
                mail_it = st.checkbox("Customer ko status email bhejein",
                                      value=has_mail, disabled=not has_mail,
                                      key=f"m{o['id']}")
                if st.button("Update status", key=f"u{o['id']}", use_container_width=True):
                    db.update_order_status(o["id"], stt, nte, crr, trk)
                    ss.flash = ("✅ Status update ho gaya — customer ko Track order "
                                "page par turant nazar aa jayega.")
                    if mail_it and has_mail:
                        ok, info = notify.notify_order_status(o, stt, CUR, S["shop_name"])
                        ss.flash += (" 📧 Email bhej di." if ok
                                     else " ⚠️ Email fail: " + str(info))
                    st.rerun()
                if has_mail and st.button("📧 Confirmation email dobara bhejein",
                                          key=f"re{o['id']}", use_container_width=True):
                    ok, info = notify.customer_confirmation(
                        o, o.get("items") or [], CUR, S["shop_name"],
                        o.get("subtotal"), o.get("delivery_fee"))
                    ss.flash = ("📧 Customer ko email bhej di." if ok
                                else "⚠️ Email fail: " + str(info))
                    st.rerun()
                msg = (f"Assalam-o-Alaikum {o['customer_name']}! Aap ka order "
                       f"#{o['order_no']} ({money(o['total'], CUR)}) confirm ho gaya hai. "
                       f"Shukriya!")
                st.markdown(f"<a class='wa' style='position:static;display:inline-flex' "
                            f"href='{wa_link(o['whatsapp'], msg)}' target='_blank'>"
                            f"💬 Customer ko WhatsApp</a>", unsafe_allow_html=True)

# ================================================================== PROFIT
with tabs[5]:
    section("💰 Profit / Loss", "Purchase price + expense se khud calculate hota hai")
    today = dt.date.today()
    f1, f2, f3 = st.columns([1, 1, 2.2])
    d1 = f1.date_input("Se", today.replace(day=1), key="pf_from")
    d2 = f2.date_input("Tak", today, key="pf_to")
    picked = f3.multiselect("Kon se orders ginne hain", STATUSES,
                            default=list(COUNTED), key="pf_st",
                            help="Sirf asal bikri ka profit dekhna ho to bas "
                                 "'delivered' rakhein.")
    rep = db.profit_report(str(d1), str(d2) + "T23:59:59", tuple(picked))
    T = rep["totals"]

    m = st.columns(5)
    m[0].metric("Orders", T["orders"])
    m[1].metric("Revenue (items)", money(T["revenue"], CUR))
    m[2].metric("Cost", money(T["cost"], CUR))
    m[3].metric("Profit", money(T["profit"], CUR), str(T["margin"]) + "% margin")
    m[4].metric("Delivery collected", money(T["delivery"], CUR))
    if T["orders"] and T["profit"] < 0:
        st.error("⚠️ Is period mein **loss** ho raha hai — sale price cost se kam hai.")
    st.caption("Delivery fee profit mein nahi gini gayi kyunki wo courier ko chali "
               "jaati hai. Revenue sirf products ka hai.")
    if rep["no_cost"]:
        st.warning("In products ki **purchase price set nahi** hai, is liye profit "
                   "asal se zyada dikh raha hai — Products tab mein jaa kar bhar "
                   "dein: " + ", ".join(rep["no_cost"][:12])
                   + (" …" if len(rep["no_cost"]) > 12 else ""))

    if not rep["months"]:
        empty("Is period mein koi order nahi mila.")
    else:
        section("🗓️ Month by month")
        st.dataframe(
            [{"Month": x["month"], "Orders": x["orders"],
              "Revenue": round(x["revenue"]), "Cost": round(x["cost"]),
              "Profit": round(x["profit"]),
              "Margin %": (int(round(x["profit"] / x["revenue"] * 100))
                           if x["revenue"] else 0)} for x in rep["months"]],
            use_container_width=True, hide_index=True)

        section("📦 Product by product", "sab se zyada profit sab se upar")
        st.dataframe(
            [{"Product": x["title"], "Qty sold": int(x["qty"]),
              "Revenue": round(x["revenue"]), "Cost": round(x["cost"]),
              "Profit": round(x["profit"]),
              "Margin %": (int(round(x["profit"] / x["revenue"] * 100))
                           if x["revenue"] else 0)} for x in rep["products"]],
            use_container_width=True, hide_index=True)

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Product", "Qty sold", "Revenue", "Cost", "Profit"])
        for x in rep["products"]:
            w.writerow([x["title"], int(x["qty"]), round(x["revenue"], 2),
                        round(x["cost"], 2), round(x["profit"], 2)])
        st.download_button("⬇️ Excel/CSV download karein", buf.getvalue(),
                           file_name="profit_" + str(d1) + "_" + str(d2) + ".csv",
                           mime="text/csv", use_container_width=True)

    with st.expander("ℹ️ Profit kaise nikalta hai?"):
        st.markdown(
            "- **Revenue** = order mein product ka price × qty (delivery fee alag)\n"
            "- **Cost** = (purchase price + expense per piece) × qty\n"
            "- **Profit** = Revenue − Cost\n"
            "- Order karte waqt product ki cost order ke andar **save** ho jaati "
            "hai, is liye baad mein purchase price badalne se purani reports "
            "nahi badalti\n"
            "- Jo purane orders migration se pehle ke hain, un mein snapshot nahi "
            "hota — un ke liye product ki **aaj wali** cost use hoti hai")


# ================================================================== LIVE CHAT
with tabs[6]:
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

# ================================================================== PROMOTE
with tabs[7]:
    section("📣 Facebook par promote karein",
            "Link paste karne par product ki image khud aa jaye")
    st.caption(social.status())
    if not social.site_url():
        st.warning("`[share] site_url` set nahi hai — share link ban nahi sakta. "
                   "Settings tab ka template dekh kar Secrets mein daal dein.")

    promo_list = db.get_products(limit=300, active_only=False)
    if not promo_list:
        empty("Pehle koi product add karein.")
    else:
        sp = st.selectbox(
            "Product chunein", promo_list, key="promo_pick",
            format_func=lambda p: f"{p['title']} — {money(p['final_price'], CUR)}"
                                  f"{'' if p['is_active'] else '  (hidden)'}")
        link = social.share_url(sp["id"])
        pcol, tcol = st.columns([1, 1.4], gap="large")

        with pcol:
            if sp["cover"]:
                st.image(sp["cover"], use_container_width=True)
            else:
                empty("Is product ki koi image nahi — Facebook par preview khali aayega.")
            if sp["cover"] and st.button("🖼️ Image download karein",
                                         use_container_width=True):
                blob, msg = social.fetch_image(sp["cover"])
                if blob:
                    ss.img_blob = (sp["id"], blob)
                else:
                    st.error(msg)
            if ss.img_blob and ss.img_blob[0] == sp["id"]:
                st.download_button("⬇️ Save karein", ss.img_blob[1],
                                   file_name=f"{sp['id']}.jpg", mime="image/jpeg",
                                   use_container_width=True)
            st.caption("Manual tareeqa: image save karein → Facebook par **photo post** "
                       "banayein → caption paste kar dein. Photo posts ko link posts se "
                       "zyada reach milti hai.")

        with tcol:
            st.markdown("**Share link — Facebook/WhatsApp par yahi paste karein**")
            st.code(link or "site_url set nahi hai", language="text")
            if not social.og_ready():
                st.info("Ye seedha site ka link hai — Facebook is par product ki image "
                        "nahi dikha sakta. Image wala preview chalu karne ke liye "
                        "Supabase Edge Function `og` deploy karein (Settings tab → "
                        "“Share preview kaise deploy karein”).")
            cap = st.text_area("Post caption (edit kar sakte hain)",
                               social.caption(sp, CUR, S["shop_name"], link),
                               height=270, key=f"cap_{sp['id']}")
            s1, s2 = st.columns(2)
            s1.link_button("📘 Facebook par share", social.fb_share_dialog(link),
                           use_container_width=True, disabled=not link)
            s2.link_button("💬 WhatsApp par bhejein", social.wa_share_link(cap),
                           use_container_width=True)

            st.divider()
            st.markdown("**Seedha apne Facebook Page par post karein**")
            mode = st.radio(
                "Post ki qism", ["album", "photo", "link"], horizontal=True,
                key="promo_mode",
                format_func=lambda m: {"album": "📸 Saari images (album)",
                                       "photo": "🖼️ Ek photo",
                                       "link": "🔗 Link post"}[m])
            if st.button("📤 Facebook Page par post karein", type="primary",
                         use_container_width=True, disabled=not social.fb_ready()):
                with st.spinner("Facebook par bhej rahe hain…"):
                    ok, info = social.fb_post_product(sp, CUR, S["shop_name"],
                                                      mode, cap, link)
                (st.success if ok else st.error)(info)
            if not social.fb_ready():
                st.caption("Auto-post band hai — `[facebook] page_id` aur "
                           "`page_access_token` Secrets mein daalein (Settings tab).")
            if link:
                st.link_button("🔄 Facebook ka purana preview refresh karein",
                               social.fb_debugger(link), use_container_width=True)

# ================================================================== SETTINGS
with tabs[8]:
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

    st.divider()
    section("🔔 Notifications", "Gmail alerts + owner WhatsApp alert")
    st.caption(notify.status())
    n1, n2 = st.columns([1.7, 1], vertical_alignment="bottom")
    test_to = n1.text_input("Test email is address par bhejein",
                            notify.email_cfg()["owner"] or "")
    if n2.button("🔔 Test bhejein", type="primary", use_container_width=True):
        with st.spinner("Bhej rahe hain…"):
            res = notify.send_test(test_to, S["shop_name"])
        for kind, (ok, info) in res.items():
            (st.success if ok else st.error)(f"{kind}: {info}")

    with st.expander("📋 Secrets template — Manage app → Settings → Secrets"):
        st.code('[email]\n'
                'enabled      = true\n'
                'host         = "smtp.gmail.com"\n'
                'port         = 587\n'
                'sender       = "aapkastore@gmail.com"\n'
                'app_password = "abcd efgh ijkl mnop"   # Gmail App Password\n'
                'sender_name  = "My Store"\n'
                'owner_email  = "aapkastore@gmail.com"\n'
                '\n'
                '[whatsapp]\n'
                'enabled          = true\n'
                'provider         = "callmebot"\n'
                'owner_phone      = "03001234567"\n'
                'callmebot_apikey = "123456"\n', language="toml")
        st.caption("**Gmail App Password:** Google Account → Security → 2-Step "
                   "Verification ON karein → App passwords → naya banayein. "
                   "Normal Gmail password SMTP par kaam nahi karta.")
        st.caption("**CallMeBot API key:** callmebot.com/blog/free-api-whatsapp-messages "
                   "khol kar wahan diya hua bot number apne contacts mein save karein, "
                   "us par WhatsApp se likhein: “I allow callmebot to send me messages”. "
                   "Jawab mein API key aa jayegi.")

    st.divider()
    section("📣 Facebook / Share", "Link preview + Page par auto-post")
    st.caption(social.status())
    if social.fb_ready() and st.button("🔍 Facebook token test karein",
                                       use_container_width=True):
        ok, info = social.fb_page_info()
        (st.success if ok else st.error)(info)

    with st.expander("📋 Secrets template — [share] aur [facebook]"):
        st.code('[share]\n'
                'site_url = "https://mystorepk.streamlit.app"\n'
                '# Edge Function deploy hone ke baad ye line add karein:\n'
                '# og_base = "https://<project-ref>.supabase.co/functions/v1/og"\n'
                '\n'
                '[facebook]\n'
                'enabled           = true\n'
                'page_id           = "1234567890"\n'
                'page_access_token = "EAA...lamba...token"\n'
                '# graph_version   = "v23.0"   # "unsupported version" error par badlein\n',
                language="toml")
        st.caption("**Page ID:** apne Facebook Page → About → sab se niche Page ID. "
                   "**Token:** developers.facebook.com → apni app → Tools → "
                   "Graph API Explorer → apna Page chunein → permissions "
                   "`pages_manage_posts` aur `pages_read_engagement` → Generate. "
                   "Ye token 1-2 ghante chalta hai; lamba token banane ke liye "
                   "Access Token Debug Tool → **Extend Access Token**.")
        st.caption("Apne hi Page par post karne ke liye Meta ka app review zaroori "
                   "nahi — Standard Access apne owned Page par kaam kar jaata hai.")

    with st.expander("🚀 Share preview (image wala link) kaise deploy karein"):
        st.markdown(
            "1. Supabase → **Edge Functions** → *Deploy a new function* → **Via Editor**\n"
            "2. Naam rakhein `og` → repo ki file `supabase/functions/og/index.ts` ka "
            "poora code paste karein → **Deploy**\n"
            "3. Usi function ke **Settings** mein **Verify JWT = OFF** karein — warna "
            "Facebook ka crawler 401 khayega aur preview khali rahega\n"
            "4. Edge Functions → **Secrets** mein `SITE_URL = " +
            (social.site_url() or "https://mystorepk.streamlit.app") +
            "` daalein (chahein to `SHOP_NAME` aur `CURRENCY` bhi)\n"
            "5. Test karein: `https://<project-ref>.supabase.co/functions/v1/og"
            "?p=<product-id>&debug=1`\n"
            "6. Sahi chale to Streamlit Secrets mein `[share] og_base = "
            "\"https://<project-ref>.supabase.co/functions/v1/og\"` add kar dein")
        st.caption("Function sirf active product ka naam, price aur pehli image "
                   "dikhata hai — koi secret expose nahi hota.")
