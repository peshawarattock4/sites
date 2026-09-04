import re
import time
import uuid
import streamlit as st

SHOP = st.secrets.get("shop", {})
st.set_page_config(page_title=SHOP.get("name", "Shop"), page_icon="🛍️",
                   layout="wide", initial_sidebar_state="collapsed")

import db
import notify
from styles import inject_css
from ui import (announcement, section, empty, hero_slider, build_slides,
                product_card, money, wa_link, wa_float, chat_html, e)

inject_css()
S = db.get_settings()
CUR = SHOP.get("currency", "Rs")
DELIV = float(S.get("delivery_fee") or 0)
FREE_OVER = float(S.get("free_over") or 0)

# Checkout par email zaroori banana ho to ise True kar dein — bas itna hi kaafi hai.
EMAIL_REQUIRED = False
# Ek hi chat session mein owner ko dobara WhatsApp alert kitni dair baad jaye (seconds)
CHAT_ALERT_GAP = 300

ss = st.session_state
ss.setdefault("view", "home")
ss.setdefault("cart", {})
ss.setdefault("cat", None)
ss.setdefault("q", "")
ss.setdefault("pid", None)
ss.setdefault("img_i", 0)
ss.setdefault("sid", uuid.uuid4().hex[:14])
ss.setdefault("cname", "")
ss.setdefault("cwa", "")
ss.setdefault("order", None)
ss.setdefault("wa_ping", 0.0)
ss.setdefault("deep_done", False)


# ------------------------------------------------------------------ deep link
# Facebook / WhatsApp se aane wala link:  https://<site>/?p=<product-id>
# Sirf PARHTE hain, URL likhte nahi — is liye koi rerun loop nahi banta.
if not ss.deep_done:
    ss.deep_done = True
    try:
        _pid = str(st.query_params.get("p") or "").strip()
    except Exception:
        _pid = ""
    if _pid:
        try:
            if db.get_product(_pid):
                ss.view, ss.pid = "product", _pid
        except Exception:
            pass                       # ghalat/purana id — chup-chaap home page


# ------------------------------------------------------------------ helpers
def go(view, **kw):
    ss.view = view
    for k, v in kw.items():
        ss[k] = v
    st.rerun()


def cart_items():
    out = []
    for pid, qty in list(ss.cart.items()):
        p = db.get_product(pid)
        if not p:
            ss.cart.pop(pid, None)
            continue
        out.append({"product_id": pid, "title": p["title"], "price": p["final_price"],
                    "qty": int(qty), "image": p["cover"],
                    "line_total": p["final_price"] * int(qty)})
    return out


def totals(items):
    sub = sum(i["line_total"] for i in items)
    fee = 0.0 if (FREE_OVER and sub >= FREE_OVER) or sub == 0 else DELIV
    return sub, fee, sub + fee


def add_to_cart(p, qty=1):
    if int(p.get("stock") or 0) <= 0:
        st.toast("😔 Ye product out of stock hai", icon="⚠️")
        return
    ss.cart[p["id"]] = min(int(ss.cart.get(p["id"], 0)) + qty, int(p["stock"]))
    st.toast(f"✅ Cart mein add ho gaya: {p['title'][:28]}", icon="🛒")


def ping_owner(text: str):
    """Naye chat message par owner ko WhatsApp alert — background, throttled."""
    now = time.time()
    if now - float(ss.wa_ping or 0) < CHAT_ALERT_GAP:
        return
    ss.wa_ping = now
    try:
        notify.notify_new_chat(ss.cname, ss.cwa, text, ss.sid, S["shop_name"])
    except Exception:
        pass


# ------------------------------------------------------------------ header
def header():
    announcement(S.get("announcement", ""))
    c1, c2, c3, c4 = st.columns([3.4, 4.6, 1.1, 1.1], vertical_alignment="center")
    with c1:
        st.markdown(
            f"<div class='brand'><div class='brand-logo'>🛍️</div><div>"
            f"<div class='brand-name'>{e(S['shop_name'])}</div>"
            f"<div class='brand-tag'>{e(SHOP.get('tagline',''))}</div></div></div>",
            unsafe_allow_html=True)
    with c2:
        st.text_input("s", value=ss.q, key="sbox", label_visibility="collapsed",
                      placeholder="🔍  Product search karein… (naam, category, offer)",
                      on_change=lambda: (ss.update(q=ss.sbox, view="home", pid=None)))
    with c3:
        n = sum(int(v) for v in ss.cart.values())
        if st.button(f"🛒 {n}", use_container_width=True, key="hcart"):
            go("cart")
    with c4:
        if st.button("💬 Chat", use_container_width=True, key="hchat"):
            go("chat")

    cats = db.get_categories()
    labels = ["🏠 All"] + [f"{c.get('icon') or '🛍️'} {c['name']}" for c in cats]
    ids = [None] + [c["id"] for c in cats]
    per = 6
    for r in range(0, len(labels), per):
        cols = st.columns(per)
        for col, lab, cid in zip(cols, labels[r:r + per], ids[r:r + per]):
            active = (ss.cat == cid)
            if col.button(lab, key=f"cat_{cid}_{r}", use_container_width=True,
                          type="primary" if active else "secondary"):
                go("home", cat=cid, pid=None)
    st.divider()


# ------------------------------------------------------------------ grid
def grid(products, kp="g", cols=4):
    if not products:
        empty("😕 Koi product nahi mila. Doosra keyword ya category try karein.")
        return
    for i in range(0, len(products), cols):
        cs = st.columns(cols, gap="medium")
        for c, p in zip(cs, products[i:i + cols]):
            with c:
                st.markdown(product_card(p, CUR), unsafe_allow_html=True)
                b1, b2 = st.columns([1, 1])
                if b1.button("View", key=f"{kp}v{p['id']}", use_container_width=True):
                    go("product", pid=p["id"], img_i=0)
                if b2.button("＋ Cart", key=f"{kp}a{p['id']}", use_container_width=True,
                             type="primary"):
                    add_to_cart(p)
                    st.rerun()


# ------------------------------------------------------------------ views
def view_home():
    sale = db.get_products(only_sale=True, limit=8)
    feat = db.get_products(only_featured=True, limit=8)
    offers = sale + [p for p in feat if p["id"] not in {x["id"] for x in sale}]
    hero_slider(build_slides(offers[:6], db.get_banners(), CUR), secs=5)

    if ss.q or ss.cat:
        res = db.get_products(search=ss.q, category_id=ss.cat)
        label = f"“{ss.q}”" if ss.q else "Category"
        section(f"🔎 Search results — {label}", f"{len(res)} products")
        grid(res, "res")
        if st.button("← Clear filter"):
            go("home", q="", cat=None, sbox="")
        return

    if sale:
        section("🔥 Sale & Offers", "limited time")
        grid(sale[:4], "sl")
    if feat:
        section("⭐ Featured", "hand picked")
        grid(feat[:4], "ft")
    allp = db.get_products(limit=60)
    section("🆕 All Products", f"{len(allp)} items")
    grid(allp, "all")


def view_product():
    p = db.get_product(ss.pid)
    if not p:
        empty("Product available nahi hai.")
        return
    if st.button("← Back"):
        go("home")
    L, R = st.columns([1.05, 1], gap="large")
    with L:
        imgs = p["images"] or [""]
        i = min(ss.img_i, len(imgs) - 1)
        st.markdown(f"<div class='dmain' style=\"background-image:url('{e(imgs[i])}')\"></div>",
                    unsafe_allow_html=True)
        if len(imgs) > 1:
            tc = st.columns(len(imgs))
            for k, (col, u) in enumerate(zip(tc, imgs)):
                if col.button(f"{k+1}", key=f"th{k}", use_container_width=True,
                              type="primary" if k == i else "secondary"):
                    ss.img_i = k
                    st.rerun()
    with R:
        st.markdown(f"<div class='pcat'>{e(p['category_icon'])} {e(p['category_name'])}</div>",
                    unsafe_allow_html=True)
        st.markdown(f"### {e(p['title'])}")
        old = (f"<span class='pold'>{money(p['price'],CUR)}</span>"
               f"<span class='hero-off' style='background:#fee2e2;color:#b91c1c'>"
               f"-{p['discount_pct']}%</span>") if p["on_sale"] else ""
        st.markdown(f"<div style='margin:2px 0 10px'><span class='pnew' "
                    f"style='font-size:1.6rem'>{money(p['final_price'],CUR)}</span>{old}</div>",
                    unsafe_allow_html=True)
        if p.get("offer_text"):
            st.success(f"🎁 {p['offer_text']}")
        stock = int(p.get("stock") or 0)
        st.caption(f"{'✅ In stock — ' + str(stock) + ' available' if stock else '❌ Out of stock'}")
        if p["highlights"]:
            st.markdown("**Highlights**")
            for h in p["highlights"]:
                st.markdown(f"<div class='hl'>✔️ {e(h)}</div>", unsafe_allow_html=True)
        q1, q2 = st.columns([1, 2])
        qty = q1.number_input("Qty", 1, max(stock, 1), 1, disabled=stock == 0)
        if q2.button("🛒 Add to Cart", type="primary", use_container_width=True,
                     disabled=stock == 0):
            add_to_cart(p, int(qty))
            st.rerun()
        if S.get("owner_whatsapp"):
            ask = (f"Mujhe ye product chahiye: {p['title']} "
                   f"({money(p['final_price'], CUR)})")
            link = wa_link(S["owner_whatsapp"], ask)
            st.markdown(
                f"<a class='wa' style='position:static;display:inline-flex;margin-top:10px' "
                f"href='{link}' target='_blank'>"
                f"💬 WhatsApp par order karein</a>", unsafe_allow_html=True)

    if p.get("description"):
        section("📝 Description")
        st.write(p["description"])
    rel = [x for x in db.get_products(category_id=p.get("category_id"), limit=5)
           if x["id"] != p["id"]][:4]
    if rel:
        section("🔗 Related products")
        grid(rel, "rel")


def view_cart():
    section("🛒 Your Cart")
    items = cart_items()
    if not items:
        empty("Cart khali hai. Products browse karein aur add karein.")
        if st.button("← Shop now", type="primary"):
            go("home")
        return
    for it in items:
        c = st.columns([0.7, 3, 1.2, 1.4, 0.8], vertical_alignment="center")
        c[0].markdown(f"<div class='pimg' style=\"padding-top:100%;border-radius:10px;"
                      f"background-image:url('{e(it['image'])}')\"></div>", unsafe_allow_html=True)
        c[1].markdown(f"**{e(it['title'])}**  \n{money(it['price'],CUR)}")
        nq = c[2].number_input("q", 1, 99, it["qty"], key=f"q{it['product_id']}",
                               label_visibility="collapsed")
        if nq != it["qty"]:
            ss.cart[it["product_id"]] = int(nq)
            st.rerun()
        c[3].markdown(f"**{money(it['line_total'],CUR)}**")
        if c[4].button("🗑", key=f"d{it['product_id']}"):
            ss.cart.pop(it["product_id"], None)
            st.rerun()
    sub, fee, tot = totals(items)
    st.markdown(f"<div class='kv'><span>Subtotal</span><b>{money(sub,CUR)}</b></div>"
                f"<div class='kv'><span>Delivery</span><b>"
                f"{'FREE' if fee==0 else money(fee,CUR)}</b></div>"
                f"<div class='kv'><span>Total</span><span class='tot'>{money(tot,CUR)}</span></div>",
                unsafe_allow_html=True)
    a, b = st.columns(2)
    if a.button("← Continue shopping", use_container_width=True):
        go("home")
    if b.button("✅ Proceed to Checkout", type="primary", use_container_width=True):
        go("checkout")


def view_checkout():
    section("📦 Checkout", "* wale saare fields zaroori hain")
    items = cart_items()
    if not items:
        empty("Cart khali hai.")
        return
    sub, fee, tot = totals(items)
    with st.form("co", clear_on_submit=False):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full Name *", placeholder="Muhammad Ali")
        city = c2.text_input("City *", placeholder="Lahore")
        phone = c1.text_input("Phone Number *", placeholder="03001234567")
        wa = c2.text_input("WhatsApp Number *", placeholder="03001234567")
        mail = st.text_input("Email " + ("*" if EMAIL_REQUIRED else "(optional)"),
                             placeholder="aapka@gmail.com",
                             help="Order ki confirmation isi email par bhej denge.")
        addr = st.text_area("Complete Delivery Address *", height=90,
                            placeholder="House #, Street, Area, Landmark…")
        note = st.text_input("Order note (optional)")
        st.markdown(f"<div class='kv'><span>{len(items)} items</span>"
                    f"<b>{money(sub,CUR)}</b></div>"
                    f"<div class='kv'><span>Delivery</span>"
                    f"<b>{'FREE' if fee==0 else money(fee,CUR)}</b></div>"
                    f"<div class='kv'><span>Payable (COD)</span>"
                    f"<span class='tot'>{money(tot,CUR)}</span></div>",
                    unsafe_allow_html=True)
        ok = st.form_submit_button("🚀 Confirm Order", type="primary",
                                   use_container_width=True)

    if not ok:
        if st.button("← Back to cart"):
            go("cart")
        return

    errs = []
    if len(name.strip()) < 3:
        errs.append("Poora naam likhein (min 3 characters).")
    if not (10 <= len(re.sub(r"\D", "", phone)) <= 13):
        errs.append("Phone number sahi nahi hai.")
    if not (10 <= len(re.sub(r"\D", "", wa)) <= 13):
        errs.append("WhatsApp number sahi nahi hai.")
    if len(addr.strip()) < 12:
        errs.append("Address mukammal likhein (min 12 characters).")
    if len(city.strip()) < 2:
        errs.append("City likhein.")
    mail_v = mail.strip().lower()
    if EMAIL_REQUIRED and not mail_v:
        errs.append("Email address likhein.")
    if mail_v and not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", mail_v):
        errs.append("Email address sahi nahi lag raha.")
    if errs:
        for x in errs:
            st.error(x)
        return

    payload = {
        "customer_name": name.strip(), "phone": phone.strip(), "whatsapp": wa.strip(),
        "email": mail_v or None, "address": addr.strip(), "city": city.strip(),
        "note": note.strip(), "items": items, "subtotal": sub, "delivery_fee": fee,
        "total": tot, "status": "new",
    }
    with st.spinner("Order save ho raha hai…"):
        try:
            row = db.create_order(payload)
        except Exception as ex:
            # `email` column DB mein na ho to order phir bhi na rukay
            if "email" not in str(ex).lower():
                raise
            row = db.create_order({k: v for k, v in payload.items() if k != "email"})
            st.warning("Order save ho gaya, magar orders table mein `email` column "
                       "nahi mila — migration SQL chala lein.")
        payload["order_no"] = row.get("order_no", "—")
        try:
            sent = notify.notify_new_order(payload, items, CUR, S["shop_name"], sub, fee)
        except Exception as ex:                 # notification kabhi order na rokay
            sent = {"error": (False, str(ex))}

    ss.order = {"no": payload["order_no"], "name": name, "total": tot,
                "items": items, "email": mail_v, "sent": sent}
    ss.cart = {}
    go("thanks")


def view_thanks():
    o = ss.order or {}
    st.balloons()
    section("🎉 Order Confirmed!")
    st.success(f"Shukriya **{e(o.get('name',''))}**! Aap ka order number "
               f"**#{o.get('no')}** hai. Hum jald WhatsApp par confirm karenge.")
    sent = o.get("sent") or {}
    if o.get("email") and bool(sent.get("customer_email", (False, ""))[0]):
        st.info(f"📧 Confirmation email **{o['email']}** par bhej di gayi hai. "
                f"Inbox mein na miley to Spam / Promotions bhi dekh lein.")
    lines = "\n".join(f"• {i['title']} x{i['qty']} = {money(i['line_total'],CUR)}"
                      for i in o.get("items", []))
    msg = (f"Assalam-o-Alaikum! Order #{o.get('no')}\n{lines}\n"
           f"Total: {money(o.get('total',0),CUR)}\nName: {o.get('name')}")
    if S.get("owner_whatsapp"):
        st.markdown(f"<a class='wa' style='position:static;display:inline-flex' "
                    f"href='{wa_link(S['owner_whatsapp'], msg)}' target='_blank'>"
                    f"💬 Order details WhatsApp par bhejein</a>", unsafe_allow_html=True)
    if st.button("🏠 Home", type="primary"):
        go("home", order=None)


def view_chat():
    section("💬 Live Chat", "hum online hain")
    if not (ss.cname and ss.cwa):
        with st.form("cs"):
            n = st.text_input("Aap ka naam *")
            w = st.text_input("WhatsApp number *", placeholder="03001234567")
            if st.form_submit_button("Chat shuru karein", type="primary"):
                if len(n.strip()) < 3 or not (10 <= len(re.sub(r"\D", "", w)) <= 13):
                    st.error("Naam aur sahi WhatsApp number likhein.")
                else:
                    ss.cname, ss.cwa = n.strip(), w.strip()
                    first = "Assalam-o-Alaikum, mujhe madad chahiye."
                    db.send_message(ss.sid, "user", first, ss.cname, ss.cwa)
                    ping_owner(first)
                    st.rerun()
        return

    st.caption(f"👤 {ss.cname}  •  Ticket **{ss.sid}**  •  auto-refresh 5s"
               + ("  •  owner ko WhatsApp par alert ja chuka hai ✅"
                  if notify.wa_ready() else ""))

    @st.fragment(run_every=5)
    def stream():
        st.markdown(chat_html(db.get_thread(ss.sid)), unsafe_allow_html=True)

    stream()
    if txt := st.chat_input("Apna message likhein…"):
        db.send_message(ss.sid, "user", txt, ss.cname, ss.cwa)
        ping_owner(txt)
        st.rerun()


# ------------------------------------------------------------------ router
header()
{"home": view_home, "product": view_product, "cart": view_cart,
 "checkout": view_checkout, "thanks": view_thanks, "chat": view_chat
 }.get(ss.view, view_home)()

if ss.view != "chat":
    wa_float(S.get("owner_whatsapp", ""), S["shop_name"])
