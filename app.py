import datetime as dt
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

EMAIL_REQUIRED = False
CHAT_ALERT_GAP = 300

ss = st.session_state
ss.setdefault("view", "home")
ss.setdefault("cart", {})
ss.setdefault("cat", None)
ss.setdefault("q", "")
ss.setdefault("sbox", "")
ss.setdefault("pid", None)
ss.setdefault("img_i", 0)
ss.setdefault("sid", uuid.uuid4().hex[:14])
ss.setdefault("cname", "")
ss.setdefault("cwa", "")
ss.setdefault("order", None)
ss.setdefault("wa_ping", 0.0)
ss.setdefault("deep_done", False)
ss.setdefault("tk_phone", "")
ss.setdefault("tk_no", "")
ss.setdefault("tk_done", False)
ss.setdefault("tk_hits", 0)

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
            pass

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
                    "line_total": p["final_price"] * int(qty),
                    "cost": float(p.get("cost_price") or 0),
                    "expense": float(p.get("expense") or 0)})
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
    now = time.time()
    if now - float(ss.wa_ping or 0) < CHAT_ALERT_GAP:
        return
    ss.wa_ping = now
    try:
        notify.notify_new_chat(ss.cname, ss.cwa, text, ss.sid, S["shop_name"])
    except Exception:
        pass

HERO_CSS = """
<style>
.heroband{position:relative;overflow:hidden;border-radius:22px;
  padding:34px 22px 26px;margin:4px 0 16px;
  background:linear-gradient(120deg,#1e1b4b,#312e81,#4338ca,#6d28d9,#4338ca,#1e1b4b);
  background-size:340% 340%;animation:hbg 22s ease infinite;
  box-shadow:0 20px 46px -20px rgba(49,46,129,.85)}
@keyframes hbg{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.heroband:before,.heroband:after{content:"";position:absolute;border-radius:50%;filter:blur(48px);opacity:.45;pointer-events:none}
.heroband:before{width:280px;height:280px;top:-130px;left:-70px;background:radial-gradient(circle,#a78bfa,transparent 70%);animation:hfl1 16s ease-in-out infinite}
.heroband:after{width:330px;height:330px;bottom:-170px;right:-90px;background:radial-gradient(circle,#38bdf8,transparent 70%);animation:hfl2 19s ease-in-out infinite}
@keyframes hfl1{0%,100%{transform:translate(0,0)}50%{transform:translate(42px,28px)}}
@keyframes hfl2{0%,100%{transform:translate(0,0)}50%{transform:translate(-48px,-24px)}}
.hin{position:relative;z-index:2;text-align:center}
.hname{margin:0;color:#fff;font-weight:900;line-height:1.03;letter-spacing:-.025em;font-size:clamp(2rem,6.4vw,4.3rem);text-shadow:0 8px 30px rgba(0,0,0,.32)}
.hw{display:inline-block;opacity:0;animation:hwin .85s cubic-bezier(.2,.9,.25,1) both}
@keyframes hwin{0%{opacity:0;transform:translateY(30px) scale(.85) rotate(-4deg);filter:blur(8px)}60%{opacity:1}100%{opacity:1;transform:none;filter:none}}
.htag{margin:9px 0 0;color:#e0e7ff;font-weight:600;font-size:clamp(.86rem,1.9vw,1.06rem);opacity:0;animation:hfade .9s ease .5s both}
@keyframes hfade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.hrot{position:relative;height:40px;margin:14px 0 2px}
.hrot>span{position:absolute;left:0;right:0;top:0;opacity:0}
.hrot b{display:inline-block;font-weight:800;color:#fff;font-size:clamp(.82rem,2vw,1rem);background:rgba(255,255,255,.17);border:1px solid rgba(255,255,255,.3);padding:7px 17px;border-radius:999px}
.hbar{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:10px;opacity:0;animation:hfade .9s ease .75s both}
.hbar i{font-style:normal;font-size:.76rem;font-weight:700;color:#1e1b4b;background:#fff;padding:5px 12px;border-radius:999px;white-space:nowrap}
@media (max-width:640px){.heroband{padding:26px 14px 20px;border-radius:18px}.hrot{height:36px}}
</style>
"""

def hero_head(cats):
    words = [w for w in str(S["shop_name"] or "Shop").split() if w] or ["Shop"]
    ws = "".join(f"<span class='hw' style='animation-delay:{round(0.15*i,2)}s'>{e(w)}</span> " for i, w in enumerate(words))
    labels = [(str(c.get("icon") or "🛍️") + " " + str(c.get("name") or "")).strip() for c in (cats or []) if str(c.get("name") or "").strip()][:8] or ["🛍️ Naye products", "🔥 Sale & Offers", "🚚 Cash on Delivery"]
    n, per = len(labels), 2.4
    f = 100.0 / n
    kf = f"<style>@keyframes rotcyc{{0%{{opacity:0;transform:translateY(12px)}}{round(f*.12,3)}%{{opacity:1;transform:none}}{round(f*.86,3)}%{{opacity:1;transform:none}}{round(f,3)}%{{opacity:0;transform:translateY(-12px)}}100%{{opacity:0;transform:translateY(-12px)}}}}.hrot>span{{animation:rotcyc {round(n*per,2)}s linear infinite}}</style>"
    rot = "".join(f"<span style='animation-delay:{round(per*i,2)}s'><b>{e(lab)}</b></span>" for i, lab in enumerate(labels))
    pills = ["🇵🇰 Poore Pakistan mein delivery", "💵 Cash on Delivery"]
    if FREE_OVER: pills.append("🚚 " + money(FREE_OVER, CUR) + " se upar free delivery")
    elif DELIV: pills.append("🚚 Delivery " + money(DELIV, CUR))
    bar = "".join(f"<i>{e(x)}</i>" for x in pills)
    tag = str(SHOP.get("tagline", "") or "").strip()
    st.markdown(HERO_CSS + kf + f"<div class='heroband'><div class='hin'><h1 class='hname'>{ws}</h1>" + (f"<p class='htag'>{e(tag)}</p>" if tag else "") + f"<div class='hrot'>{rot}</div><div class='hbar'>{bar}</div></div></div>", unsafe_allow_html=True)

def header():
    announcement(S.get("announcement", ""))
    cats = db.get_categories()
    hero_head(cats)
    c1, c2, c3, c4 = st.columns([4.3, 1.35, 1.0, 1.0], vertical_alignment="center")
    with c1: st.text_input("s", key="sbox", label_visibility="collapsed", placeholder="🔍  Product search karein…", on_change=lambda: (ss.update(q=ss.sbox, view="home", pid=None)))
    with c2: 
        if st.button("📦 Track order", use_container_width=True): go("track")
    with c3: 
        if st.button(f"🛒 {sum(int(v) for v in ss.cart.values())}", use_container_width=True): go("cart")
    with c4: 
        if st.button("💬 Chat", use_container_width=True): go("chat")
    
    labels = ["🏠 All"] + [f"{c.get('icon') or '🛍️'} {c['name']}" for c in cats]
    ids = [None] + [c["id"] for c in cats]
    for r in range(0, len(labels), 6):
        cols = st.columns(6)
        for col, lab, cid in zip(cols, labels[r:r + 6], ids[r:r + 6]):
            if col.button(lab, key=f"cat_{cid}_{r}", use_container_width=True, type="primary" if ss.cat == cid else "secondary"):
                go("home", cat=cid, pid=None)
    st.divider()

FOOT_CSS = "<style>.ftr{margin:38px 0 0;padding:24px 14px 64px;border-top:1px solid #e2e8f0;text-align:center}.ftr .f1{font-weight:800;color:#1e293b;font-size:1rem}.ftr .f2{color:#475569;font-size:.92rem;margin-top:7px}.ftr .f3{color:#94a3b8;font-size:.82rem;margin-top:11px}.fhrt{display:inline-block;color:#e11d48;animation:fbeat 1.5s ease-in-out infinite}@keyframes fbeat{0%,100%{transform:scale(1)}45%{transform:scale(1.28)}}</style>"
def footer_bar(): st.markdown(FOOT_CSS + f"<div class='ftr'><div class='f1'>🚚 We deliver only across Pakistan</div><div class='f2'>Made with <span class='fhrt'>❤️</span> for our customers</div><div class='f3'>© {dt.date.today().year} {e(S['shop_name'])} — All Rights Reserved.</div></div>", unsafe_allow_html=True)

def grid(products, kp="g", cols=4):
    if not products:
        empty("😕 Koi product nahi mila.")
        return
    for i in range(0, len(products), cols):
        cs = st.columns(cols, gap="medium")
        for c, p in zip(cs, products[i:i + cols]):
            with c:
                st.markdown(product_card(p, CUR), unsafe_allow_html=True)
                b1, b2 = st.columns([1, 1])
                if b1.button("View", key=f"{kp}v{p['id']}", use_container_width=True): go("product", pid=p["id"], img_i=0)
                if b2.button("＋ Cart", key=f"{kp}a{p['id']}", use_container_width=True, type="primary"): add_to_cart(p); st.rerun()

def view_home():
    sale = db.get_products(only_sale=True, limit=8)
    feat = db.get_products(only_featured=True, limit=8)
    offers = sale + [p for p in feat if p["id"] not in {x["id"] for x in sale}]
    hero_slider(build_slides(offers[:6], db.get_banners(), CUR), secs=5)

    if ss.q or ss.cat:
        res = db.get_products(search=ss.q, category_id=ss.cat)
        section(f"🔎 Search results", f"{len(res)} products")
        grid(res, "res")
        st.button("← Clear filter", on_click=lambda: ss.update(q="", cat=None, sbox="", view="home", pid=None))
        return

    if sale: section("🔥 Sale & Offers", "limited time"); grid(sale[:4], "sl")
    if feat: section("⭐ Featured", "hand picked"); grid(feat[:4], "ft")
    allp = db.get_products(limit=60)
    section("🆕 All Products", f"{len(allp)} items"); grid(allp, "all")

def view_product():
    p = db.get_product(ss.pid)
    if not p: empty("Product available nahi hai."); return
    if st.button("← Back"): go("home")
    L, R = st.columns([1.05, 1], gap="large")
    with L:
        imgs = p["images"] or [""]
        i = min(ss.img_i, len(imgs) - 1)
        st.markdown(f"<div class='dmain' style=\"background-image:url('{e(imgs[i])}')\"></div>", unsafe_allow_html=True)
        if len(imgs) > 1:
            tc = st.columns(len(imgs))
            for k, (col, u) in enumerate(zip(tc, imgs)):
                if col.button(f"{k+1}", key=f"th{k}", use_container_width=True, type="primary" if k == i else "secondary"): ss.img_i = k; st.rerun()
    with R:
        st.markdown(f"<div class='pcat'>{e(p['category_icon'])} {e(p['category_name'])}</div>### {e(p['title'])}", unsafe_allow_html=True)
        old = f"<span class='pold'>{money(p['price'],CUR)}</span><span class='hero-off' style='background:#fee2e2;color:#b91c1c'>-{p['discount_pct']}%</span>" if p["on_sale"] else ""
        st.markdown(f"<div style='margin:2px 0 10px'><span class='pnew' style='font-size:1.6rem'>{money(p['final_price'],CUR)}</span>{old}</div>", unsafe_allow_html=True)
        if p.get("offer_text"): st.success(f"🎁 {p['offer_text']}")
        stock = int(p.get("stock") or 0)
        st.caption(f"{'✅ In stock — ' + str(stock) + ' available' if stock else '❌ Out of stock'}")
        if p["highlights"]:
            st.markdown("**Highlights**")
            for h in p["highlights"]: st.markdown(f"<div class='hl'>✔️ {e(h)}</div>", unsafe_allow_html=True)
        q1, q2 = st.columns([1, 2])
        qty = q1.number_input("Qty", 1, max(stock, 1), 1, disabled=stock == 0)
        if q2.button("🛒 Add to Cart", type="primary", use_container_width=True, disabled=stock == 0): add_to_cart(p, int(qty)); st.rerun()
        if S.get("owner_whatsapp"):
            link = wa_link(S["owner_whatsapp"], f"Mujhe ye product chahiye: {p['title']} ({money(p['final_price'], CUR)})")
            st.markdown(f"<a class='wa' style='position:static;display:inline-flex;margin-top:10px' href='{link}' target='_blank'>💬 WhatsApp par order karein</a>", unsafe_allow_html=True)

    if p.get("description"):
        section("📝 Description")
        st.write(p["description"])
        
    # ===== NEW SMART VIDEO PLAYER =====
    if p.get("video_url"):
        section("🎥 Product Video")
        v_url = p["video_url"].strip()
        # YouTube ID nikalne ki koshish (Shorts ho ya normal link)
        yt_match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})", v_url)
        
        if yt_match:
            vid = yt_match.group(1)
            embed_url = f"https://www.youtube.com/embed/{vid}?rel=0"
            st.markdown(f'''
            <iframe width="100%" height="450" src="{embed_url}" 
            frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
            allowfullscreen style="border-radius:12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);"></iframe>
            ''', unsafe_allow_html=True)
        else:
            try:
                st.video(v_url) # Agar koi aur format ho (mp4) to Streamlit ka apna player
            except:
                st.error("Video format support nahi kar raha.")
    # ==================================

    rel = [x for x in db.get_products(category_id=p.get("category_id"), limit=5) if x["id"] != p["id"]][:4]
    if rel: section("🔗 Related products"); grid(rel, "rel")

def view_cart():
    section("🛒 Your Cart")
    items = cart_items()
    if not items:
        empty("Cart khali hai.")
        if st.button("← Shop now", type="primary"): go("home")
        return
    for it in items:
        c = st.columns([0.7, 3, 1.2, 1.4, 0.8], vertical_alignment="center")
        c[0].markdown(f"<div class='pimg' style=\"padding-top:100%;border-radius:10px;background-image:url('{e(it['image'])}')\"></div>", unsafe_allow_html=True)
        c[1].markdown(f"**{e(it['title'])}**  \n{money(it['price'],CUR)}")
        nq = c[2].number_input("q", 1, 99, it["qty"], key=f"q{it['product_id']}", label_visibility="collapsed")
        if nq != it["qty"]: ss.cart[it["product_id"]] = int(nq); st.rerun()
        c[3].markdown(f"**{money(it['line_total'],CUR)}**")
        if c[4].button("🗑", key=f"d{it['product_id']}"): ss.cart.pop(it["product_id"], None); st.rerun()
    sub, fee, tot = totals(items)
    st.markdown(f"<div class='kv'><span>Subtotal</span><b>{money(sub,CUR)}</b></div><div class='kv'><span>Delivery</span><b>{'FREE' if fee==0 else money(fee,CUR)}</b></div><div class='kv'><span>Total</span><span class='tot'>{money(tot,CUR)}</span></div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    if a.button("← Continue shopping", use_container_width=True): go("home")
    if b.button("✅ Proceed to Checkout", type="primary", use_container_width=True): go("checkout")

def view_checkout():
    section("📦 Checkout", "* wale saare fields zaroori hain")
    items = cart_items()
    if not items: empty("Cart khali hai."); return
    sub, fee, tot = totals(items)
    with st.form("co", clear_on_submit=False):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full Name *", placeholder="Muhammad Ali")
        city = c2.text_input("City *", placeholder="Lahore")
        phone = c1.text_input("Phone Number *", placeholder="03001234567")
        wa = c2.text_input("WhatsApp Number *", placeholder="03001234567")
        mail = st.text_input("Email " + ("*" if EMAIL_REQUIRED else "(optional)"), placeholder="aapka@gmail.com")
        addr = st.text_area("Complete Delivery Address *", height=90, placeholder="House #, Street, Area, Landmark…")
        note = st.text_input("Order note (optional)")
        st.markdown(f"<div class='kv'><span>{len(items)} items</span><b>{money(sub,CUR)}</b></div><div class='kv'><span>Delivery</span><b>{'FREE' if fee==0 else money(fee,CUR)}</b></div><div class='kv'><span>Payable (COD)</span><span class='tot'>{money(tot,CUR)}</span></div>", unsafe_allow_html=True)
        ok = st.form_submit_button("🚀 Confirm Order", type="primary", use_container_width=True)

    if not ok:
        if st.button("← Back to cart"): go("cart")
        return

    errs = []
    if len(name.strip()) < 3: errs.append("Poora naam likhein (min 3 characters).")
    if not (10 <= len(re.sub(r"\D", "", phone)) <= 13): errs.append("Phone number sahi nahi hai.")
    if not (10 <= len(re.sub(r"\D", "", wa)) <= 13): errs.append("WhatsApp number sahi nahi hai.")
    if len(addr.strip()) < 12: errs.append("Address mukammal likhein (min 12 characters).")
    if len(city.strip()) < 2: errs.append("City likhein.")
    mail_v = mail.strip().lower()
    if errs:
        for x in errs: st.error(x)
        return

    payload = {"customer_name": name.strip(), "phone": phone.strip(), "whatsapp": wa.strip(), "email": mail_v or None, "address": addr.strip(), "city": city.strip(), "note": note.strip(), "items": items, "subtotal": sub, "delivery_fee": fee, "total": tot, "status": "new"}
    with st.spinner("Order save ho raha hai…"):
        try: row = db.create_order(payload)
        except: row = db.create_order({k: v for k, v in payload.items() if k != "email"})
        payload["order_no"] = row.get("order_no", "—")
        try: sent = notify.notify_new_order(payload, items, CUR, S["shop_name"], sub, fee)
        except Exception as ex: sent = {"error": (False, str(ex))}

    ss.order = {"no": payload["order_no"], "name": name, "total": tot, "items": items, "email": mail_v, "sent": sent, "phone": phone.strip()}
    ss.cart = {}
    go("thanks")

def view_thanks():
    o = ss.order or {}
    st.balloons()
    section("🎉 Order Confirmed!")
    st.success(f"Shukriya **{e(o.get('name',''))}**! Aap ka order number **#{o.get('no')}** hai. Hum jald WhatsApp par confirm karenge.")
    if S.get("owner_whatsapp"):
        lines = "\n".join(f"• {i['title']} x{i['qty']}" for i in o.get("items", []))
        msg = f"Assalam-o-Alaikum! Order #{o.get('no')}\n{lines}\nTotal: {money(o.get('total',0),CUR)}\nName: {o.get('name')}"
        st.markdown(f"<a class='wa' style='position:static;display:inline-flex' href='{wa_link(S['owner_whatsapp'], msg)}' target='_blank'>💬 Order details WhatsApp par bhejein</a>", unsafe_allow_html=True)
    if st.button("🏠 Home", type="primary", use_container_width=True): go("home", order=None)

def view_track():
    section("📦 Order Tracking")
    # code omitted for brevity
    
def view_chat():
    section("💬 Live Chat")
    # code omitted for brevity

header()
{"home": view_home, "product": view_product, "cart": view_cart, "checkout": view_checkout, "thanks": view_thanks, "chat": view_chat, "track": view_track}.get(ss.view, view_home)()
footer_bar()
if ss.view != "chat": wa_float(S.get("owner_whatsapp", ""), S["shop_name"])
