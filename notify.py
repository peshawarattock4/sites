"""notify.py — Order & chat notifications.

Do cheezein karta hai:
  1. EMAIL  (Gmail SMTP)  : naye order par owner ko alert + customer ko confirmation
  2. WHATSAPP (owner ko)  : naya order ya naya live-chat message aane par instant alert

Koi extra library nahi chahiye — sab Python standard library se (smtplib + urllib).
Har function FAIL-SOFT hai: notification fail ho jaye to order kabhi block nahi hota,
sirf (False, "reason") return hota hai.

Secrets ki misaal .streamlit/secrets.toml mein di gayi hai.
"""
import re
import smtplib
import ssl
import threading
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

import streamlit as st

from ui import e, money, norm_wa

TIMEOUT = 20


# ================================================================== config
def _sec(section: str) -> dict:
    try:
        return dict(st.secrets.get(section, {}) or {})
    except Exception:
        return {}


def email_cfg() -> dict:
    c = _sec("email")
    sender = str(c.get("sender") or "").strip()
    return {
        "enabled": bool(c.get("enabled", True)),
        "host": str(c.get("host") or "smtp.gmail.com").strip(),
        "port": int(c.get("port") or 587),
        "sender": sender,
        "password": str(c.get("app_password") or "").strip().replace(" ", ""),
        "name": str(c.get("sender_name") or _sec("shop").get("name") or "Shop"),
        "owner": str(c.get("owner_email") or sender).strip(),
    }


def email_ready() -> bool:
    c = email_cfg()
    return bool(c["enabled"] and c["sender"] and c["password"])


def wa_cfg() -> dict:
    c = _sec("whatsapp")
    return {
        "enabled": bool(c.get("enabled", True)),
        "provider": str(c.get("provider") or "").strip().lower(),
        "phone": norm_wa(str(c.get("owner_phone") or "")),
        "apikey": str(c.get("callmebot_apikey") or "").strip(),
        "instance": str(c.get("ultramsg_instance") or "").strip(),
        "token": str(c.get("ultramsg_token") or "").strip(),
    }


def wa_ready() -> bool:
    c = wa_cfg()
    if not (c["enabled"] and c["phone"]):
        return False
    if c["provider"] == "callmebot":
        return bool(c["apikey"])
    if c["provider"] == "ultramsg":
        return bool(c["instance"] and c["token"])
    return False


def status() -> str:
    """Admin panel mein dikhane ke liye chhota summary."""
    return ("📧 Email: " + ("✅ ready" if email_ready() else "❌ set nahi") +
            "   •   💬 WhatsApp alert: " +
            ("✅ ready (" + wa_cfg()["provider"] + ")" if wa_ready() else "❌ set nahi"))


# ================================================================== low level
def _bg(fn, *args):
    """Background thread — sirf plain dict/str pass karein, `st` ko touch na karein."""
    def run():
        try:
            fn(*args)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _text_of(html_body: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_body)
    t = re.sub(r"(?i)<br\s*/?>|</(p|tr|div|h1|h2|h3)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _smtp_send(c: dict, to: str, subject: str, body_html: str, body_text: str):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((c["name"], c["sender"]))
    msg["To"] = to
    msg["Reply-To"] = c["owner"] or c["sender"]
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")
    ctx = ssl.create_default_context()
    if int(c["port"]) == 465:
        with smtplib.SMTP_SSL(c["host"], 465, context=ctx, timeout=TIMEOUT) as s:
            s.login(c["sender"], c["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(c["host"], int(c["port"]), timeout=TIMEOUT) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(c["sender"], c["password"])
            s.send_message(msg)


def send_email(to: str, subject: str, body_html: str, background: bool = False):
    """(ok, message) return karta hai. Exception kabhi bahar nahi jaata."""
    if not email_ready():
        return False, "[email] secrets set nahi hain"
    to = str(to or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", to):
        return False, "email address sahi nahi: " + to
    c = email_cfg()
    body_text = _text_of(body_html)
    if background:
        _bg(_smtp_send, c, to, subject, body_html, body_text)
        return True, "queued"
    try:
        _smtp_send(c, to, subject, body_html, body_text)
        return True, "sent"
    except smtplib.SMTPAuthenticationError:
        return False, ("Gmail ne login reject kiya — app_password ghalat hai. "
                       "Normal Gmail password kaam nahi karta, 16-digit "
                       "App Password chahiye (2-step verification on hona zaroori).")
    except Exception as ex:
        return False, type(ex).__name__ + ": " + str(ex)


def _http_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "shop-notify/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return int(getattr(r, "status", 200) or 200), r.read()[:300].decode("utf-8", "ignore")


def _http_post(url: str, form: dict):
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "shop-notify/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return int(getattr(r, "status", 200) or 200), r.read()[:300].decode("utf-8", "ignore")


def _wa_send(c: dict, text: str):
    if c["provider"] == "callmebot":
        q = urllib.parse.urlencode({"phone": "+" + c["phone"], "text": text,
                                    "apikey": c["apikey"]})
        return _http_get("https://api.callmebot.com/whatsapp.php?" + q)
    if c["provider"] == "ultramsg":
        return _http_post("https://api.ultramsg.com/" + c["instance"] + "/messages/chat",
                          {"token": c["token"], "to": "+" + c["phone"], "body": text})
    raise RuntimeError("WhatsApp provider set nahi hai")


def wa_alert(text: str, background: bool = False):
    """Owner ko WhatsApp alert. (ok, message) return karta hai."""
    if not wa_ready():
        return False, "[whatsapp] secrets set nahi hain"
    c = wa_cfg()
    if background:
        _bg(_wa_send, c, text)
        return True, "queued"
    try:
        code, resp = _wa_send(c, text)
        return (200 <= code < 300), "HTTP " + str(code) + " " + resp.strip()[:160]
    except Exception as ex:
        return False, type(ex).__name__ + ": " + str(ex)


# ================================================================== templates
BRAND = "#4338ca"
SALE = "#e11d48"


def _shell(title: str, lead: str, inner: str, shop: str) -> str:
    return (
        "<div style=\"margin:0;padding:24px 12px;background:#f7f8fb;"
        "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "color:#0f172a\">"
        "<div style='max-width:560px;margin:0 auto;background:#fff;border-radius:16px;"
        "overflow:hidden;border:1px solid #e8ebf1'>"
        "<div style=\"padding:20px 24px;background:linear-gradient(135deg,#1e1b4b," + BRAND + ")\">"
        "<div style='color:#fff;font-size:13px;letter-spacing:.06em;opacity:.85'>" + e(shop).upper() + "</div>"
        "<div style='color:#fff;font-size:21px;font-weight:800;margin-top:2px'>" + e(title) + "</div>"
        "</div>"
        "<div style='padding:22px 24px'>"
        "<p style='margin:0 0 14px;font-size:15px;line-height:1.6'>" + lead + "</p>"
        + inner +
        "</div>"
        "<div style='padding:14px 24px;background:#f7f8fb;border-top:1px solid #e8ebf1;"
        "font-size:12px;color:#64748b'>Ye email " + e(shop) + " ne automatic bheji hai.</div>"
        "</div></div>")


def _kv(label: str, value: str) -> str:
    return ("<tr><td style='padding:5px 0;color:#64748b;font-size:13px;width:36%'>" + e(label) +
            "</td><td style='padding:5px 0;font-size:14px;font-weight:600'>" + e(value) + "</td></tr>")


def _items_table(items: list, cur: str, total, sub=None, fee=None) -> str:
    rows = []
    for i in (items or []):
        rows.append(
            "<tr>"
            "<td style='padding:9px 0;border-bottom:1px solid #eef1f6;font-size:14px'>" +
            e(str(i.get("title", ""))) + "</td>"
            "<td style='padding:9px 6px;border-bottom:1px solid #eef1f6;font-size:14px;"
            "text-align:center;color:#64748b'>x" + str(int(i.get("qty") or 1)) + "</td>"
            "<td style='padding:9px 0;border-bottom:1px solid #eef1f6;font-size:14px;"
            "text-align:right;font-weight:600'>" + money(i.get("line_total") or 0, cur) + "</td>"
            "</tr>")
    foot = ""
    if sub is not None:
        foot += ("<tr><td colspan='2' style='padding:7px 0;color:#64748b;font-size:13px'>Subtotal</td>"
                 "<td style='padding:7px 0;text-align:right;font-size:13px'>" + money(sub, cur) + "</td></tr>")
    if fee is not None:
        foot += ("<tr><td colspan='2' style='padding:0 0 7px;color:#64748b;font-size:13px'>Delivery</td>"
                 "<td style='padding:0 0 7px;text-align:right;font-size:13px'>" +
                 ("FREE" if float(fee or 0) == 0 else money(fee, cur)) + "</td></tr>")
    foot += ("<tr><td colspan='2' style='padding:10px 0 0;border-top:2px solid #0f172a;"
             "font-weight:800;font-size:15px'>Total (COD)</td>"
             "<td style='padding:10px 0 0;border-top:2px solid #0f172a;text-align:right;"
             "font-weight:800;font-size:17px;color:" + SALE + "'>" + money(total, cur) + "</td></tr>")
    return ("<table style='width:100%;border-collapse:collapse;margin:6px 0 4px'>" +
            "".join(rows) + foot + "</table>")


def order_text(order: dict, items: list, cur: str) -> str:
    """WhatsApp / plain-text version."""
    lines = ["🛒 NAYA ORDER  #" + str(order.get("order_no") or "—"), ""]
    for i in (items or []):
        lines.append("• " + str(i.get("title", "")) + " x" + str(int(i.get("qty") or 1)) +
                     " = " + money(i.get("line_total") or 0, cur))
    lines += [
        "",
        "Total: " + money(order.get("total") or 0, cur) + "  (COD)",
        "Naam: " + str(order.get("customer_name") or ""),
        "Phone: " + str(order.get("phone") or ""),
        "WhatsApp: " + str(order.get("whatsapp") or ""),
        "Email: " + str(order.get("email") or "—"),
        "Sheher: " + str(order.get("city") or ""),
        "Pata: " + str(order.get("address") or ""),
    ]
    if order.get("note"):
        lines.append("Note: " + str(order["note"]))
    return "\n".join(lines)


# ================================================================== public API
def notify_new_order(order: dict, items: list, cur: str = "Rs", shop: str = "Shop",
                     sub=None, fee=None, background: bool = False) -> dict:
    """Naye order par: owner ko email + WhatsApp, customer ko confirmation email.
    Return: {"owner_email": (ok,msg), "owner_wa": (ok,msg), "customer_email": (ok,msg)}"""
    out = {}
    no = str(order.get("order_no") or "—")
    total = order.get("total") or 0
    cust = str(order.get("customer_name") or "Customer")

    # ---------- 1. owner ko email alert
    det = ("<table style='width:100%;border-collapse:collapse'>" +
           _kv("Naam", cust) +
           _kv("Phone", str(order.get("phone") or "")) +
           _kv("WhatsApp", str(order.get("whatsapp") or "")) +
           _kv("Email", str(order.get("email") or "—")) +
           _kv("Sheher", str(order.get("city") or "")) +
           _kv("Pata", str(order.get("address") or "")) +
           _kv("Note", str(order.get("note") or "—")) +
           "</table>")
    owner_html = _shell(
        "Naya Order #" + no,
        "Ek naya order aaya hai. Total <b>" + money(total, cur) + "</b> (Cash on Delivery).",
        _items_table(items, cur, total, sub, fee) +
        "<div style='margin:16px 0 6px;font-weight:700;font-size:14px'>Customer details</div>" + det,
        shop)
    c = email_cfg()
    if c["owner"]:
        out["owner_email"] = send_email(c["owner"], "🛒 Naya order #" + no + " — " +
                                        money(total, cur), owner_html, background)
    else:
        out["owner_email"] = (False, "[email] owner_email set nahi")

    # ---------- 2. owner ko WhatsApp alert
    out["owner_wa"] = wa_alert(order_text(order, items, cur), background=True)

    # ---------- 3. customer ko confirmation
    out["customer_email"] = customer_confirmation(order, items, cur, shop, sub, fee,
                                                  background)
    return out


def customer_confirmation(order: dict, items: list, cur: str = "Rs", shop: str = "Shop",
                          sub=None, fee=None, background: bool = False) -> tuple:
    """Customer ko order confirmation email. Admin ka 'dobara bhejein' button bhi isi ko
    use karta hai, is liye owner ko dobara alert nahi jaata."""
    to = str(order.get("email") or "").strip()
    if not to:
        return False, "customer ne email nahi diya"
    no = str(order.get("order_no") or "—")
    cust = str(order.get("customer_name") or "Customer")
    total = order.get("total") or 0
    body = _shell(
        "Order Confirm — #" + no,
        "Assalam-o-Alaikum <b>" + e(cust) + "</b>! Aap ka order mil gaya hai. "
        "Hum jald WhatsApp par confirm karenge. Payment delivery par (COD).",
        _items_table(items, cur, total, sub, fee) +
        "<div style='margin:14px 0 0;padding:12px 14px;background:#f7f8fb;"
        "border-radius:12px;font-size:13px;color:#475569'>Order number "
        "<b>#" + no + "</b> — kisi bhi sawal ke liye isi email ka jawab dein.</div>",
        shop)
    return send_email(to, "✅ Aap ka order #" + no + " confirm ho gaya", body, background)


def notify_order_status(order: dict, new_status: str, cur: str = "Rs",
                        shop: str = "Shop") -> tuple:
    """Status badalne par customer ko email (agar email diya ho)."""
    to = str(order.get("email") or "").strip()
    if not to:
        return False, "customer ka email nahi hai"
    no = str(order.get("order_no") or "—")
    words = {
        "new": "Aap ka order register ho gaya hai.",
        "confirmed": "Aap ka order confirm ho gaya hai — hum tayyari kar rahe hain.",
        "shipped": "Aap ka order raaste mein hai! Jald aap tak pohnch jayega.",
        "delivered": "Aap ka order deliver ho gaya. Shukriya kharidari ka! 🎉",
        "cancelled": "Aap ka order cancel kar diya gaya hai.",
    }
    html_body = _shell(
        "Order #" + no + " — " + new_status.upper(),
        words.get(new_status, "Aap ke order ka status update hua hai: <b>" +
                  e(new_status) + "</b>"),
        _items_table(order.get("items") or [], cur, order.get("total") or 0),
        shop)
    return send_email(to, "📦 Order #" + no + " — " + new_status.upper(), html_body)


def notify_new_chat(name: str, whatsapp: str, message: str, session_id: str,
                    shop: str = "Shop", also_email: bool = False) -> dict:
    """Customer ka naya live-chat message — owner ko WhatsApp par instant alert.

    NOTE: ye sirf OUTBOUND alert hai. Customer ka jawab admin portal ke
    'Live Messages' tab mein aata hai, WhatsApp par nahi (wajah niche likhi hai)."""
    txt = ("💬 " + shop + " — naya live chat message\n\n"
           "Naam: " + str(name or "Guest") + "\n"
           "WhatsApp: " + str(whatsapp or "—") + "\n"
           "Ticket: " + str(session_id) + "\n\n"
           "\"" + str(message or "")[:400] + "\"\n\n"
           "Jawab dein: admin portal → Live Messages")
    out = {"owner_wa": wa_alert(txt, background=True)}
    if also_email:
        c = email_cfg()
        if c["owner"]:
            body = _shell("Naya live-chat message",
                          "<b>" + e(str(name or "Guest")) + "</b> (" +
                          e(str(whatsapp or "—")) + ") ne likha:",
                          "<div style='padding:12px 14px;background:#f7f8fb;border-radius:12px;"
                          "font-size:14px'>" + e(str(message or "")) + "</div>"
                          "<div style='margin-top:12px;font-size:12px;color:#64748b'>Ticket " +
                          e(str(session_id)) + "</div>", shop)
            out["owner_email"] = send_email(c["owner"], "💬 Naya chat message — " +
                                            str(name or "Guest"), body, background=True)
    return out


def send_test(to_email: str = "", shop: str = "Shop") -> dict:
    """Admin Settings tab ka 'Test' button isko chalata hai."""
    out = {}
    c = email_cfg()
    to = (to_email or c["owner"]).strip()
    body = _shell("Test email ✅",
                  "Agar ye email aap tak pohnch gayi hai to SMTP settings bilkul sahi hain.",
                  "<div style='font-size:13px;color:#64748b'>Host: " + e(c["host"]) +
                  ":" + str(c["port"]) + " • Sender: " + e(c["sender"]) + "</div>", shop)
    out["email"] = send_email(to, "✅ " + shop + " — test email", body)
    out["whatsapp"] = wa_alert("✅ " + shop + " — test WhatsApp alert. "
                               "Sab kuch sahi kaam kar raha hai.")
    return out
