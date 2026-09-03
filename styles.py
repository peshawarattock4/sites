import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600&display=swap');

:root{
  --ink:#0f172a; --muted:#64748b; --line:#e8ebf1; --bg:#f7f8fb;
  --brand:#e11d48; --brand2:#7c3aed; --ok:#16a34a;
  --r:16px; --shadow:0 8px 26px rgba(15,23,42,.07);
}
.stApp{background:var(--bg);}
html,body,[class*="css"]{font-family:'Inter',system-ui,sans-serif;}
#MainMenu, footer, header{visibility:hidden;}
.block-container{max-width:1200px;padding-top:.6rem;padding-bottom:7rem;}
h1,h2,h3{font-family:'Plus Jakarta Sans',sans-serif;color:var(--ink);}

/* ---------- announcement marquee ---------- */
.ann{background:linear-gradient(90deg,#0f172a,#312e81,#0f172a);color:#fff;
     border-radius:99px;padding:8px 0;overflow:hidden;font-size:.82rem;
     font-weight:500;margin-bottom:14px;}
.ann span{display:inline-block;white-space:nowrap;padding-left:100%;
     animation:mv 22s linear infinite;}
@keyframes mv{0%{transform:translateX(0)}100%{transform:translateX(-100%)}}

/* ---------- brand ---------- */
.brand{display:flex;align-items:center;gap:10px;}
.brand-logo{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;font-size:20px;}
.brand-name{font-family:'Plus Jakarta Sans';font-weight:800;font-size:1.28rem;
  line-height:1.1;color:var(--ink);}
.brand-tag{font-size:.72rem;color:var(--muted);}

/* ---------- HERO auto slider ---------- */
.hero{position:relative;overflow:hidden;border-radius:22px;box-shadow:var(--shadow);
      margin:6px 0 18px;}
.hero-track{display:flex;width:calc(var(--n) * 100%);}
.hero-slide{width:calc(100% / var(--n));min-height:238px;display:flex;
   align-items:center;justify-content:space-between;gap:16px;padding:26px 30px;color:#fff;}
.hero-txt{flex:1;min-width:0;}
.hero-kicker{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);
   padding:4px 12px;border-radius:99px;font-size:.7rem;font-weight:700;letter-spacing:.08em;
   text-transform:uppercase;margin-bottom:10px;}
.hero-h{font-family:'Plus Jakarta Sans';font-weight:800;font-size:1.85rem;line-height:1.2;
   margin:0 0 6px;text-shadow:0 2px 12px rgba(0,0,0,.25);}
.hero-sub{font-size:.9rem;opacity:.92;margin-bottom:12px;}
.hero-price{font-weight:800;font-size:1.35rem;}
.hero-old{opacity:.7;text-decoration:line-through;font-weight:500;font-size:.95rem;margin-left:8px;}
.hero-off{background:#fff;color:var(--brand);font-weight:800;border-radius:99px;
   padding:4px 12px;font-size:.8rem;margin-left:10px;}
.hero-img{width:210px;height:186px;border-radius:18px;background-size:cover;
   background-position:center;box-shadow:0 12px 30px rgba(0,0,0,.28);flex:none;}
.hero-dots{position:absolute;bottom:12px;left:50%;transform:translateX(-50%);
   display:flex;gap:7px;z-index:5;}
.hero-dots i{width:8px;height:8px;border-radius:99px;background:rgba(255,255,255,.55);display:block;}
@media(max-width:760px){.hero-img{display:none}.hero-h{font-size:1.35rem}.hero-slide{min-height:200px}}

/* ---------- section title ---------- */
.sec{display:flex;align-items:center;gap:10px;margin:22px 0 12px;}
.sec b{font-family:'Plus Jakarta Sans';font-size:1.12rem;color:var(--ink);}
.sec hr{flex:1;border:none;border-top:1px dashed var(--line);}
.sec em{font-style:normal;font-size:.76rem;color:var(--muted);}

/* ---------- product card ---------- */
.pcard{background:#fff;border:1px solid var(--line);border-radius:var(--r);overflow:hidden;
   transition:.22s;height:100%;}
.pcard:hover{transform:translateY(-4px);box-shadow:var(--shadow);border-color:#dcdfe8;}
.pimg{position:relative;width:100%;padding-top:88%;background:#eef1f6 center/cover no-repeat;}
.pbadge{position:absolute;top:9px;left:9px;background:var(--brand);color:#fff;font-size:.68rem;
   font-weight:800;padding:3px 9px;border-radius:99px;letter-spacing:.03em;}
.pbadge.alt{background:#0f172a;left:auto;right:9px;}
.pbody{padding:11px 12px 13px;}
.pcat{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;}
.ptitle{font-family:'Plus Jakarta Sans';font-weight:700;font-size:.92rem;color:var(--ink);
   margin:3px 0 7px;height:2.5em;overflow:hidden;line-height:1.25;}
.pnew{font-weight:800;color:var(--ink);font-size:1rem;}
.pold{color:var(--muted);text-decoration:line-through;font-size:.8rem;margin-left:6px;}
.poffer{margin-top:6px;font-size:.7rem;color:var(--ok);font-weight:700;}
.pstock{font-size:.68rem;color:#b45309;font-weight:600;margin-top:4px;}

/* ---------- chips / pills ---------- */
.stButton>button{border-radius:11px;font-weight:600;font-size:.84rem;border:1px solid var(--line);}
.stButton>button:hover{border-color:var(--brand);color:var(--brand);}

/* ---------- detail ---------- */
.dmain{width:100%;padding-top:74%;border-radius:18px;background:#eef1f6 center/cover no-repeat;
   border:1px solid var(--line);}
.hl{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:6px 0;
   font-size:.87rem;}
.kv{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px dashed var(--line);
   font-size:.9rem;}
.tot{font-weight:800;font-size:1.15rem;color:var(--brand);}

/* ---------- chat ---------- */
.chatbox{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;
   max-height:430px;overflow-y:auto;}
.bub{max-width:78%;padding:9px 13px;border-radius:15px;margin:6px 0;font-size:.88rem;
   line-height:1.4;word-wrap:break-word;}
.bub.u{background:linear-gradient(135deg,var(--brand),#f43f5e);color:#fff;margin-left:auto;
   border-bottom-right-radius:4px;}
.bub.a{background:#f1f5f9;color:var(--ink);border-bottom-left-radius:4px;}
.bub small{display:block;opacity:.7;font-size:.66rem;margin-top:3px;}

/* ---------- floating whatsapp ---------- */
.wa{position:fixed;right:20px;bottom:88px;z-index:9999;background:#25D366;color:#fff!important;
   text-decoration:none!important;font-weight:700;font-size:.86rem;padding:11px 17px;
   border-radius:99px;box-shadow:0 8px 22px rgba(37,211,102,.45);display:flex;gap:8px;
   align-items:center;}
.wa:hover{transform:scale(1.05);}

.empty{text-align:center;padding:46px 12px;color:var(--muted);background:#fff;
   border:1px dashed var(--line);border-radius:16px;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)
