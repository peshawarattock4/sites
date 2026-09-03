"""UI components — CSS-only auto slider, product cards, chat bubbles, helpers."""
import html
import re
import urllib.parse

import streamlit as st

GRADS = [("#0f172a", "#e11d48"), ("#1e1b4b", "#7c3aed"), ("#064e3b", "#16a34a"),
         ("#7c2d12", "#f59e0b"), ("#0c4a6e", "#0ea5e9")]


# ------------------------------------------------------------------ helpers
def e(s) -> str:
    """HTML escape — injection se bachne ke liye har user text isse guzarta hai."""
    return html.escape(str(s or ""))


def money(v, cur="Rs") -> str:
    v = float(v or 0)
    return f"{cur} {v:,.0f}" if abs(v - round(v)) < 0.01 else f"{cur} {v:,.2f}"


def norm_wa(num: str) -> str:
    """03001234567 -> 923001234567"""
    d = re.sub(r"\D", "", num or "")
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("0"):
        d = "92" + d[1:]
    elif len(d) == 10:
        d = "92" + d
    return d


def wa_link(num: str, text: str = "") -> str:
    return f"https://wa.me/{norm_wa(num)}?text={urllib.parse.quote(text)}"


# ------------------------------------------------------------------ blocks
def announcement(text: str):
    if text:
        t = e(text)
        st.markdown(
            f"<div class='ann'><span>{t} &nbsp;&nbsp;•&nbsp;&nbsp; {t}</span></div>",
            unsafe_allow_html=True)


def section(title: str, note: str = ""):
    st.markdown(f"<div class='sec'><b>{e(title)}</b><hr><em>{e(note)}</em></div>",
                unsafe_allow_html=True)


def empty(msg: str):
    st.markdown(f"<div class='empty'>{e(msg)}</div>", unsafe_allow_html=True)


def wa_float(num: str, shop: str):
    if not num:
        return
    msg = f"Assalam-o-Alaikum! Mujhe {shop} ke products ke baare mein poochna hai."
    st.markdown(f"<a class='wa' href='{wa_link(num, msg)}' target='_blank'>💬 WhatsApp</a>",
                unsafe_allow_html=True)


# ------------------------------------------------------------------ auto slider
def build_slides(products: list, custom_banners: list, cur="Rs") -> list:
    """Sale/offer products se automatic slides + admin ke custom banners."""
    slides = []
    for b in custom_banners:
        slides.append({
            "kicker": "SPECIAL",
            "title": b.get("title") or "Special Offer",
            "sub": b.get("subtitle") or "",
            "img": b.get("image_url") or "",
            "from": b.get("bg_from") or "#0f172a",
            "to": b.get("bg_to") or "#e11d48",
            "price": "", "old": "", "off": "",
        })
    for p in products:
        if p.get("on_sale"):
            kicker, off = "MEGA SALE", f"{p['discount_pct']}% OFF"
        elif p.get("offer_text"):
            kicker, off = "LIMITED OFFER", p["offer_text"]
        else:
            kicker, off = "FEATURED", ""
        g = GRADS[len(slides) % len(GRADS)]
        slides.append({
            "kicker": kicker,
            "title": p["title"],
            "sub": p.get("offer_text") or (p.get("description") or "")[:96],
            "img": p.get("cover") or "",
            "from": g[0], "to": g[1],
            "price": money(p["final_price"], cur),
            "old": money(p["price"], cur) if p.get("on_sale") else "",
            "off": off,
        })
    return slides[:8]


def _slide_html(s: dict) -> str:
    parts = []
    if s["price"]:
        parts.append(f"<span>{e(s['price'])}</span>")
    if s["old"]:
        parts.append(f"<span class='hero-old'>{e(s['old'])}</span>")
    if s["off"]:
        parts.append(f"<span class='hero-off'>{e(s['off'])}</span>")
    price = f"<div class='hero-price'>{''.join(parts)}</div>" if parts else ""
    img = (f"<div class='hero-img' style=\"background-image:url('{e(s['img'])}')\"></div>"
           if s["img"] else "")
    return (
        f"<div class='hero-slide' style=\"background:linear-gradient(120deg,"
        f"{e(s['from'])},{e(s['to'])})\">"
        f"<div class='hero-txt'>"
        f"<span class='hero-kicker'>{e(s['kicker'])}</span>"
        f"<div class='hero-h'>{e(s['title'])}</div>"
        f"<div class='hero-sub'>{e(s['sub'])}</div>"
        f"{price}</div>{img}</div>"
    )


def hero_slider(slides: list, secs: int = 5):
    """Pure CSS auto-sliding banner — koi JS nahi, koi Streamlit rerun nahi."""
    n = len(slides)
    if n == 0:
        return
    dur = n * secs
    step = 100 / n
    kf = [f"{i * step:.3f}%,{i * step + step * 0.80:.3f}%"
          f"{{transform:translateX(-{i * step:.4f}%)}}" for i in range(n)]
    kf.append("100%{transform:translateX(0%)}")
    dot_kf = (f"0%,{step * 0.9:.3f}%{{background:#fff;width:24px}}"
              f"{step:.3f}%,100%{{background:rgba(255,255,255,.55);width:8px}}")
    cards = "".join(_slide_html(s) for s in slides)
    dots = "".join(f"<i style='animation:hdot {dur}s infinite;"
                   f"animation-delay:{i * secs}s'></i>" for i in range(n))
    st.markdown(
        f"<style>"
        f"@keyframes hslide{{{''.join(kf)}}}"
        f"@keyframes hdot{{{dot_kf}}}"
        f".hero-track{{animation:hslide {dur}s infinite}}"
        f"</style>"
        f"<div class='hero' style='--n:{n}'>"
        f"<div class='hero-track'>{cards}</div>"
        f"<div class='hero-dots'>{dots}</div>"
        f"</div>",
        unsafe_allow_html=True)


# ------------------------------------------------------------------ product card
def product_card(p: dict, cur="Rs") -> str:
    badges = ""
    if p.get("on_sale"):
        badges += f"<span class='pbadge'>-{p['discount_pct']}%</span>"
    if p.get("badge"):
        badges += f"<span class='pbadge alt'>{e(p['badge'])}</span>"
    img = f"background-image:url('{e(p['cover'])}')" if p.get("cover") else ""
    old = f"<span class='pold'>{money(p['price'], cur)}</span>" if p.get("on_sale") else ""
    offer = f"<div class='poffer'>🎁 {e(p['offer_text'])}</div>" if p.get("offer_text") else ""
    stk = int(p.get("stock") or 0)
    if stk <= 0:
        stock = "<div class='pstock'>⚠️ Out of stock</div>"
    elif stk <= 5:
        stock = f"<div class='pstock'>🔥 Only {stk} left</div>"
    else:
        stock = ""
    return (
        f"<div class='pcard'>"
        f"<div class='pimg' style=\"{img}\">{badges}</div>"
        f"<div class='pbody'>"
        f"<div class='pcat'>{e(p.get('category_icon'))} {e(p.get('category_name'))}</div>"
        f"<div class='ptitle'>{e(p['title'])}</div>"
        f"<div><span class='pnew'>{money(p['final_price'], cur)}</span>{old}</div>"
        f"{offer}{stock}</div></div>"
    )


# ------------------------------------------------------------------ chat
def chat_html(msgs: list) -> str:
    if not msgs:
        return ("<div class='chatbox'><div class='empty' "
                "style='border:none;padding:26px'>👋 Assalam-o-Alaikum! Koi bhi "
                "sawal poochein — hum foran reply karenge.</div></div>")
    rows = ""
    for m in msgs:
        cls = "u" if m["sender"] == "user" else "a"
        who = "You" if m["sender"] == "user" else "Support"
        t = (m.get("created_at") or "")[11:16]
        rows += (f"<div class='bub {cls}'>{e(m['message'])}"
                 f"<small>{who} • {t}</small></div>"
                 f"<div style='clear:both'></div>")
    return f"<div class='chatbox'>{rows}</div>"
