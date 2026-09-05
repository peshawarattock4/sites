"""Facebook / sharing helpers — sirf Python stdlib (urllib), koi extra package nahi.

Do kaam karta hai:
 1) Har product ka share link + tayyar caption (manual post ke liye).
 2) Facebook Page par seedha auto-post (album / photo / link) Graph API se.

Domain ki zaroorat NAHI — link `https://<site>/?p=<id>` chalta hai. Facebook par
product ki *image* wala preview chahiye to `[share] og_base` (Supabase Edge
Function `og`) set karein, kyunki Streamlit har URL par wohi ek HTML deta hai.
"""
import json
import re
import urllib.parse as up
import urllib.request as ur

import streamlit as st

GRAPH = "https://graph.facebook.com"
DEF_VER = "v23.0"
TIMEOUT = 25
UA = {"User-Agent": "Mozilla/5.0 (compatible; ShopBot/1.0)"}


# ------------------------------------------------------------------ config
def _cfg(name: str) -> dict:
    try:
        return dict(st.secrets.get(name, {}) or {})
    except Exception:
        return {}


def share_cfg() -> dict:
    return _cfg("share")


def fb_cfg() -> dict:
    return _cfg("facebook")


def site_url() -> str:
    return str(share_cfg().get("site_url") or "").strip().rstrip("/")


def og_base() -> str:
    return str(share_cfg().get("og_base") or "").strip().rstrip("/")


def og_ready() -> bool:
    """Image wala preview (Edge Function) set hai?"""
    return bool(og_base())


def fb_ready() -> bool:
    """Page par auto-post ke liye sab kuch mojood hai?"""
    c = fb_cfg()
    return bool(c.get("enabled", True) and c.get("page_id")
                and c.get("page_access_token"))


def status() -> str:
    su = site_url()
    c = fb_cfg()
    bits = ["🔗 Site URL: " + (su or "set nahi"),
            "🖼️ Image preview (og): " + ("chalu ✅" if og_ready() else "band"),
            "📘 Auto-post: " + ("chalu ✅ (page " + str(c.get("page_id")) + ")"
                                if fb_ready() else "band")]
    return "  •  ".join(bits)


# ------------------------------------------------------------------ links
def share_url(pid: str) -> str:
    """Product ka public link. og_base ho to wahi (image preview ke sath),
    warna seedha site ka link."""
    base = og_base() or site_url()
    if not base or not pid:
        return ""
    return base + "?p=" + up.quote(str(pid))


def fb_share_dialog(link: str) -> str:
    if not link:
        return "https://www.facebook.com"
    return "https://www.facebook.com/sharer/sharer.php?u=" + up.quote(link, safe="")


def fb_debugger(link: str) -> str:
    """Facebook ka purana/khali preview cache saaf karne ke liye."""
    return "https://developers.facebook.com/tools/debug/?q=" + up.quote(link, safe="")


def wa_share_link(text: str) -> str:
    return "https://wa.me/?text=" + up.quote(str(text or "")[:1800])


# ------------------------------------------------------------------ caption
def _money(v, cur: str = "Rs") -> str:
    try:
        n = float(v or 0)
    except Exception:
        n = 0.0
    return cur + " " + format(int(round(n)), ",")


def _tag(txt: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9]", "", str(txt or ""))


def caption(p: dict, cur: str = "Rs", shop: str = "", link: str = "") -> str:
    """Facebook/WhatsApp post ka tayyar caption — admin isay edit bhi kar sakta hai."""
    lines = ["🛍️ " + str(p.get("title") or "").strip(), ""]
    if p.get("on_sale"):
        lines.append("🔥 SALE: " + _money(p.get("final_price"), cur)
                     + "   (pehle " + _money(p.get("price"), cur) + " — "
                     + str(p.get("discount_pct") or 0) + "% OFF)")
    else:
        lines.append("💰 Price: " + _money(p.get("final_price"), cur))
    if str(p.get("offer_text") or "").strip():
        lines.append("🎁 " + str(p["offer_text"]).strip())

    hls = [str(h).strip() for h in (p.get("highlights") or []) if str(h).strip()][:4]
    if hls:
        lines.append("")
        for h in hls:
            lines.append("✔️ " + h)

    desc = str(p.get("description") or "").strip()
    if desc:
        lines += ["", desc[:220] + ("…" if len(desc) > 220 else "")]

    lines += ["", "🚚 Cash on Delivery — poore Pakistan mein",
              "📩 Order ke liye inbox karein ya neeche link par ja kar order karein 👇"]
    if link:
        lines.append(link)

    tags = ["#OnlineShopping", "#Pakistan", "#CashOnDelivery"]
    if str(p.get("category_name") or "").strip():
        tags.insert(0, _tag(p["category_name"]))
    if str(shop or "").strip():
        tags.insert(0, _tag(shop))
    lines += ["", " ".join(t for t in tags if len(t) > 1)]
    return "\n".join(lines)


# ------------------------------------------------------------------ image
def fetch_image(url: str):
    """Image bytes le aata hai taake admin usay download kar ke Facebook par
    photo post bana sakay. Return: (bytes|None, message)."""
    u = str(url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return None, "Image ka URL sahi nahi hai."
    try:
        with ur.urlopen(ur.Request(u, headers=UA), timeout=TIMEOUT) as r:
            blob = r.read()
    except Exception as ex:
        return None, "Image download nahi hui: " + str(ex)
    if not blob:
        return None, "Image khali aayi."
    return blob, "OK"


# ------------------------------------------------------------------ graph api
def _err(ex: Exception) -> str:
    """Graph API ka asli error message nikalta hai (HTTPError ke body se)."""
    raw = ""
    try:
        raw = ex.read().decode("utf-8", "replace")
    except Exception:
        return str(ex)
    try:
        return str((json.loads(raw).get("error") or {}).get("message") or raw)
    except Exception:
        return raw or str(ex)


def _bases() -> list:
    v = str(fb_cfg().get("graph_version") or DEF_VER).strip().strip("/")
    return [GRAPH + "/" + v, GRAPH]      # version reject ho to unversioned retry


def _call(path: str, params: dict):
    """Graph API POST. Token POST **body** mein jaata hai (URL/logs mein na aaye).
    Return: (ok, dict|error-string)."""
    data = dict(params or {})
    data["access_token"] = str(fb_cfg().get("page_access_token") or "").strip()
    body = up.urlencode(data).encode()
    last = "Unknown error"
    for b in _bases():
        req = ur.Request(b + "/" + str(path).lstrip("/"), data=body, headers=UA)
        try:
            with ur.urlopen(req, timeout=TIMEOUT) as r:
                return True, json.loads(r.read().decode() or "{}")
        except Exception as ex:
            last = _err(ex)
            if "version" not in last.lower():
                return False, last
    return False, last


def _get(path: str, params: dict):
    d = dict(params or {})
    d["access_token"] = str(fb_cfg().get("page_access_token") or "").strip()
    last = "Unknown error"
    for b in _bases():
        url = b + "/" + str(path).lstrip("/") + "?" + up.urlencode(d)
        try:
            with ur.urlopen(ur.Request(url, headers=UA), timeout=TIMEOUT) as r:
                return True, json.loads(r.read().decode() or "{}")
        except Exception as ex:
            last = _err(ex)
            if "version" not in last.lower():
                return False, last
    return False, last


def fb_page_info():
    """Token sahi hai ya nahi — Settings tab ka test button."""
    if not fb_ready():
        return False, "[facebook] page_id / page_access_token set nahi hai."
    ok, res = _get(str(fb_cfg().get("page_id")), {"fields": "name,id"})
    if not ok:
        return False, "Token test fail: " + str(res)
    return True, ("✅ Page mil gaya: " + str(res.get("name") or "?")
                  + "  (id " + str(res.get("id") or "?") + ")")


def _imgs(p: dict) -> list:
    return [str(u).strip() for u in (p.get("images") or [])
            if str(u or "").strip().lower().startswith("http")][:5]


def fb_post_product(p: dict, cur: str = "Rs", shop: str = "",
                    mode: str = "album", cap: str = "", link: str = ""):
    """Product ko Page par post karta hai. Return: (ok, message).

    mode = "album" (saari images), "photo" (pehli image), "link" (link post).
    Album ke liye pehle har image `published=false` upload hoti hai, phir un ke
    ids ek hi feed post mein `attached_media` ban jaate hain.
    """
    if not fb_ready():
        return False, "Facebook auto-post band hai — [facebook] secrets daalein."
    pid = str(fb_cfg().get("page_id") or "").strip()
    msg = str(cap or "").strip() or caption(p, cur, shop, link)

    if mode == "link":
        if not link:
            return False, "Share link nahi bana — [share] site_url set karein."
        ok, res = _call(pid + "/feed", {"message": msg, "link": link})
        if not ok:
            return False, "Link post fail: " + str(res)
        return True, "✅ Link post ho gaya  (id " + str(res.get("id") or "?") + ")"

    imgs = _imgs(p)
    if not imgs:
        return False, ("Is product ki koi image URL nahi mili — 'Link post' "
                       "try karein ya product mein image add karein.")

    if mode == "photo":
        ok, res = _call(pid + "/photos", {"url": imgs[0], "caption": msg})
        if not ok:
            return False, "Photo post fail: " + str(res)
        return True, ("✅ Photo post ho gaya  (id "
                      + str(res.get("post_id") or res.get("id") or "?") + ")")

    fbids, errs = [], []
    for u in imgs:
        ok, res = _call(pid + "/photos", {"url": u, "published": "false"})
        if ok and res.get("id"):
            fbids.append(str(res["id"]))
        else:
            errs.append(str(res))
    if not fbids:
        return False, "Koi image upload nahi hui: " + ("; ".join(errs[:2]) or "?")

    params = {"message": msg}
    for i, fid in enumerate(fbids):
        params["attached_media[" + str(i) + "]"] = json.dumps({"media_fbid": fid})
    ok, res = _call(pid + "/feed", params)
    if not ok:
        return False, "Album post fail: " + str(res)
    tail = ("   ⚠️ " + str(len(errs)) + " image upload nahi hui") if errs else ""
    return True, ("✅ Album post ho gaya — " + str(len(fbids)) + " images  (id "
                  + str(res.get("id") or "?") + ")" + tail)
