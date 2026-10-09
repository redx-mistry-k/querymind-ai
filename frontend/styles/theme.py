THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --qm-accent:#7c6cff; --qm-blue:#42a5f5; --qm-card:#171a24; --qm-border:#2a2f40; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(circle at 85% 0%, #1c2040 0, #0d0f16 34%, #0b0d13 100%); }
[data-testid="stSidebar"] { background: #0f1119; border-right: 1px solid var(--qm-border); }
[data-testid="stSidebar"] img { margin: 0 auto; }
.block-container { max-width: 1320px; padding-top: 2rem; padding-bottom: 4rem; }
h1, h2, h3 { letter-spacing: -0.035em; }
.qm-brand { font-size: 1.45rem; font-weight: 750; letter-spacing:-.04em; margin: .2rem 0 0; }
.qm-brand span { color: #8f83ff; }
.qm-subtle { color:#9199ae; font-size:.88rem; }
.qm-hero { padding: 1.7rem 1.8rem; border:1px solid var(--qm-border); border-radius:20px;
 background:linear-gradient(135deg,rgba(124,108,255,.16),rgba(23,26,36,.92) 45%,rgba(66,165,245,.08)); margin-bottom:1.4rem; }
.qm-kicker { color:#9c92ff; font-size:.73rem; font-weight:700; text-transform:uppercase; letter-spacing:.16em; }
.qm-hero h1 { margin:.35rem 0 .15rem; font-size:2.25rem; }
.qm-card { background:rgba(23,26,36,.92); border:1px solid var(--qm-border); border-radius:16px; padding:1.15rem 1.25rem; min-height:112px; }
.qm-card-label { color:#8f97aa; font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; }
.qm-card-value { color:#f3f5fb; font-size:1.65rem; font-weight:700; margin-top:.3rem; }
.qm-status { display:inline-flex; align-items:center; gap:.45rem; border:1px solid #2d6f59; background:#12271f;
 color:#70ddb2; padding:.3rem .65rem; border-radius:999px; font-size:.78rem; }
.qm-notice { border-left:3px solid #7c6cff; padding:.75rem 1rem; background:rgba(124,108,255,.08); color:#adb4c6; border-radius:0 10px 10px 0; }
.stButton > button { border-radius:10px; font-weight:600; border-color:#383e51; }
.stButton > button[kind="primary"] { background:linear-gradient(90deg,#6958ed,#527fea); border:0; }
[data-testid="stMetric"] { background:rgba(23,26,36,.9); border:1px solid var(--qm-border); padding:1rem; border-radius:14px; }
[data-testid="stDataFrame"] { border:1px solid var(--qm-border); border-radius:12px; overflow:hidden; }
.stTextArea textarea, .stTextInput input, .stSelectbox > div > div { border-radius:10px; }
code { font-size:.82rem !important; }
hr { border-color:#262b3a !important; }
</style>
"""
