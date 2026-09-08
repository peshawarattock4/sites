"""UI components — CSS-only auto slider, product cards, chat bubbles, helpers."""
import html
import re
import urllib.parse

import streamlit as st

GRADS = [("#1e1b4b", "#4338ca"),
         ("#0f172a", "#e11d48"),
         ("#312e81", "#6d28d9")]

def e(s) -> str:
    return html.escape(str(s or ""))

def money(v, cur="Rs") -> str:
    try:
        v = float(v or 0)
    except:
        v = 0.0
    return f"{cur} {v:,.0f}" if abs(v - round(v)) < 0.01 else f"{cur} {v:,.2f}"

def norm_wa(num: str) -> str:
    d = re.sub(r"\D", "", num or "")
    if d.startswith("00"): d = d[2:]
    if d.startswith("0"): d = "92" + d[1:]
    elif len(d) == 10: d = "92" + d
    return d

def wa_link(num: str, text: str = "") -> str:
    return f"https://wa.me/{norm_wa(num)}?text={urllib.parse.quote(text)}"

def announcement(text: str):
    if text:
        t = e(text)
        st.markdown(f"<div class='ann'><span>{t} &nbsp;&nbsp;•&nbsp;&nbsp; {t}</span></div>", unsafe_allow_html=True)

def section(title: str, note: str = ""):
    st.markdown(f"<div class='sec'><b>{e(title)}</b><hr><em>{e(note)}</em></div>", unsafe_allow_html=True)

def empty(msg: str):
    st.markdown(f"<div class='empty'>{e(msg)}</div>", unsafe_allow_html=True)

def wa_float(num: str, shop: str):
    if not num: return
    msg = f"Assalam-o-Alaikum! Mujhe {shop} ke products ke baare mein poochna hai."
    st.markdown(f"<a class='wa' href='{wa_link(num, msg)}' target='_blank'>💬 WhatsApp</a>", unsafe_allow_html=True)

def build_slides(products: list, custom_banners: list, cur="Rs") -> list:
    slides = []
    for b in (custom_banners or []):
        slides.append({
            "kicker": "SPECIAL",
            "title": b.get("title") or "Special Offer",
            "sub": b.get("subtitle") or "",
            "img": b.get("image_url") or "",
            "from": b.get("bg_from") or "#1e1b4b",
            "to": b.get("bg_to") or "#4338ca",
            "text_color": b.get("text_color") or "#ffffff",
            "price": "", "old": "", "off": "",
        })
    for p in (products or []):
        if not isinstance(p, dict): continue
        on_sale = bool(p.get("on_sale"))
        if on_sale:
            kicker, off = "MEGA SALE", f"{p.get('discount_pct', 0)}% OFF"
        elif p.get("offer_text"):
            kicker, off = "LIMITED OFFER", p.get("offer_text")
        else:
            kicker, off = "FEATURED", ""
        g = GRADS[len(slides) % len(GRADS)]
        
        fp = p.get("final_price") if p.get("final_price") is not None else p.get("price", 0)
        pr_val = money(fp, cur)
        old_val = money(p.get("price"), cur) if on_sale and p.get("price") else ""
        
        slides.append({
            "kicker": kicker,
            "title": p.get("title") or "Product",
            "sub": p.get("offer_text") or (p.get("description") or "")[:96],
            "img": p.get("cover") or (p.get("images")[0] if p.get("images") else ""),
            "from": g[0], "to": g[1],
            "text_color": "#ffffff",
            "price": pr_val,
            "old": old_val,
            "off": off,
        })
    return slides[:8]

def _slide_html(s: dict) -> str:
    parts = []
    if s.get("price"):
        parts.append(f"<span>{e(s['price'])}</span>")
    if s.get("old"):
        parts.append(f"<span class='hero-old'>{e(s['old'])}</span>")
    if s.get("off"):
        parts.append(f"<span class='hero-off'>{e(s['off'])}</span>")
    price = f"<div class='hero-price'>{''.join(parts)}</div>" if parts else ""
    img = f"<div class='hero-img' style=\"background-image:url('{e(s['img'])}')\"></div>" if s.get("img") else ""
    tc = e(s.get("text_color", "#ffffff"))
    return (
        f"<div class='hero-slide' style=\"background:linear-gradient(120deg,{e(s['from'])},{e(s['to'])})\">"
        f"<div class='hero-txt'>"
        f"<span class='hero-kicker' style='color:{tc}; border-color:{tc}'>{e(s['kicker'])}</span>"
        f"<div class='hero-h' style='color:{tc}'>{e(s['title'])}</div>"
        f"<div class='hero-sub' style='color:{tc}; opacity:0.9'>{e(s['sub'])}</div>"
        f"{price}</div>{img}</div>"
    )

def hero_slider(slides: list, secs: int = 5):
    n = len(slides)
    if n == 0: return
    dur = n * secs
    step = 100 / n
    kf = [f"{i * step:.3f}%,{i * step + step * 0.80:.3f}%{{transform:translateX(-{i * step:.4f}%)}}" for i in range(n)]
    kf.append("100%{transform:translateX(0%)}")
    dot_kf = f"0%,{step * 0.9:.3f}%{{background:#fff;width:24px}}{step:.3f}%,100%{{background:rgba(255,255,255,.55);width:8px}}"
    cards = "".join(_slide_html(s) for s in slides)
    dots = "".join(f"<i style='animation:hdot {dur}s infinite;animation-delay:{i * secs}s'></i>" for i in range(n))
    st.markdown(
        f"<style>@keyframes hslide{{{''.join(kf)}}}@keyframes hdot{{{dot_kf}}}.hero-track{{animation:hslide {dur}s infinite}}</style>"
        f"<div class='hero' style='--n:{n}'><div class='hero-track'>{cards}</div><div class='hero-dots'>{dots}</div></div>",
        unsafe_allow_html=True)

def product_card(p: dict, cur="Rs") -> str:
    badges = ""
    if p.get("on_sale"):
        badges += f"<span class='pbadge'>-{p.get('discount_pct', 0)}%</span>"
    if p.get("badge"):
        badges += f"<span class='pbadge alt'>{e(p['badge'])}</span>"
    img = f"background-image:url('{e(p.get('cover', ''))}')" if p.get("cover") else ""
    old = f"<span class='pold'>{money(p.get('price'), cur)}</span>" if p.get("on_sale") else ""
    offer = f"<div class='poffer'>🎁 {e(p['offer_text'])}</div>" if p.get("offer_text") else ""
    stk = int(p.get("stock") or 0)
    stock = "<div class='pstock'>⚠️ Out of stock</div>" if stk <= 0 else (f"<div class='pstock'>🔥 Only {stk} left</div>" if stk <= 5 else "")
    fp = p.get("final_price") if p.get("final_price") is not None else p.get("price", 0)
    return (
        f"<div class='pcard'>"
        f"<div class='pimg' style=\"{img}\">{badges}</div>"
        f"<div class='pbody'>"
        f"<div class='pcat'>{e(p.get('category_icon', ''))} {e(p.get('category_name', ''))}</div>"
        f"<div class='ptitle'>{e(p.get('title', ''))}</div>"
        f"<div><span class='pnew'>{money(fp, cur)}</span>{old}</div>"
        f"{offer}{stock}</div></div>"
    )

def chat_html(msgs: list) -> str:
    if not msgs:
        return "<div class='chatbox'><div class='empty' style='border:none;padding:26px'>👋 Assalam-o-Alaikum! Koi bhi sawal poochein — hum foran reply karenge.</div></div>"
    rows = ""
    for m in msgs:
        cls = "u" if m.get("sender") == "user" else "a"
        who = "You" if m.get("sender") == "user" else "Support"
        t = str(m.get("created_at") or "")[11:16]
        rows += f"<div class='bub {cls}'>{e(m.get('message',''))}<small>{who} • {t}</small></div><div style='clear:both'></div>"
    return f"<div class='chatbox'>{rows}</div>"
