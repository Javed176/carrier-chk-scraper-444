"""
app.py — FMCSA SAFER MC Number Range Scraper
"""

import io
import os
import sys
import time
from typing import List
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from db_manager import db
except ImportError:
    class DummyDB:
        def authenticate_and_login(self, u, p): return True, "OK", {"username": u, "is_admin": True, "session_duration_hours": 3.0, "session_token": "dummy"}
        def verify_active_session(self, u, s): return True
        def log_activity(self, u, a, d=""): pass
        def get_activity_logs(self, limit=200): return pd.DataFrame()
        def get_all_users(self): return []
        def create_user(self, *a, **k): return False, "db_manager.py missing."
        def update_user_config(self, *a, **k): return False, "db_manager.py missing."
    db = DummyDB()

try:
    from scraper import scrape_mc
except ImportError:
    def scrape_mc(mc): return {"MC Number": f"MC-{mc:07d}", "Carrier Name": "Error: scraper.py missing", "_found": False}

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FMCSA MC Scraper",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State Initialization ──────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = []
if "scraping" not in st.session_state:
    st.session_state.scraping = False
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "current_mc" not in st.session_state:
    st.session_state.current_mc = 1066434
if "start_mc_input" not in st.session_state:
    st.session_state["start_mc_input"] = 1066434
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None
if "login_time" not in st.session_state:
    st.session_state.login_time = 0.0


# ── Force Logout Helper ───────────────────────────────────────────────────────
def force_logout(reason: str = "Logged out."):
    if st.session_state.get("authenticated") and st.session_state.get("user_info"):
        username = st.session_state.user_info.get("username", "unknown")
        db.log_activity(username, "LOGOUT", f"Session terminated: {reason}")
    st.session_state["authenticated"] = False
    st.session_state["user_info"] = None
    st.session_state["login_time"] = 0.0
    st.session_state["logout_reason"] = reason
    st.rerun()


# ── Login Screen ──────────────────────────────────────────────────────────────
def _render_login_screen() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <style>
        .login-card {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(139,92,246,0.35);
            border-radius: 20px;
            padding: 44px 48px;
            width: 100%;
            max-width: 440px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
            text-align: center;
            margin: 40px auto;
        }
        .login-icon  { font-size: 48px; margin-bottom: 8px; }
        .login-title { font-size: 24px; font-weight: 700; color: #f0f0f0; margin-bottom: 4px; }
        .login-sub   { font-size: 13px; color: #718096; margin-bottom: 24px; }
        .login-error {
            background: rgba(239,68,68,0.12);
            border: 1px solid rgba(239,68,68,0.35);
            border-radius: 8px;
            color: #fc8181;
            font-size: 13px;
            padding: 10px 14px;
            margin-top: 14px;
        }
        div[data-testid="stTextInput"] input {
            background: rgba(255,255,255,0.07) !important;
            border: 1px solid rgba(139,92,246,0.4) !important;
            border-radius: 10px !important;
            color: #f0f0f0 !important;
            font-size: 15px !important;
            padding: 12px 16px !important;
        }
        div[data-testid="stButton"] > button {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
            border: none !important; border-radius: 10px !important;
            color: white !important; font-weight: 700 !important;
            font-size: 15px !important; padding: 12px 0 !important;
            width: 100% !important;
            box-shadow: 0 4px 20px rgba(99,102,241,0.45) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.8, 1])
    with center:
        st.markdown(
            '<div class="login-card">'
            '<div class="login-icon">🔒</div>'
            '<div class="login-title">FMCSA Scraper Access</div>'
            '<div class="login-sub">Enter your admin-provided credentials to sign in</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        if st.session_state.get("logout_reason"):
            st.warning(st.session_state["logout_reason"])

        username = st.text_input("Username / Email", key="login_username", placeholder="Username")
        password = st.text_input("Password", type="password", key="login_password", placeholder="Password")
        login_btn = st.button("🔓 Sign In", key="login_btn")

        if login_btn:
            if not username or not password:
                st.markdown(
                    '<div class="login-error">⚠️ Please enter both username and password.</div>',
                    unsafe_allow_html=True,
                )
            else:
                success, msg, uinfo = db.authenticate_and_login(username, password)
                if success and uinfo:
                    st.session_state["authenticated"] = True
                    st.session_state["user_info"] = uinfo
                    st.session_state["login_time"] = time.time()
                    st.session_state["logout_reason"] = None
                    st.rerun()
                else:
                    st.markdown(
                        f'<div class="login-error">❌ {msg}</div>',
                        unsafe_allow_html=True,
                    )
    return False


if not _render_login_screen():
    st.stop()

# ── Session Lockout & Expiration Checks ───────────────────────────────────────
user_info = st.session_state.get("user_info", {})
username = user_info.get("username", "User")
session_token = user_info.get("session_token", "")
session_duration_h = float(user_info.get("session_duration_hours", 3.0))

if not db.verify_active_session(username, session_token):
    force_logout("Session terminated: Account logged in from another tab or device.")

elapsed_sec = time.time() - st.session_state.get("login_time", time.time())
max_sec = session_duration_h * 3600.0
remaining_sec = max(0.0, max_sec - elapsed_sec)

if elapsed_sec >= max_sec:
    db.log_activity(username, "SESSION_TIMEOUT", f"Auto-locked after {session_duration_h} hours")
    force_logout(f"Session expired automatically after {session_duration_h:g} hours.")

# ── Global CSS Styling ────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .stApp {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        min-height: 100vh;
    }

    #MainMenu, footer, header { visibility: hidden; }

    .header-banner {
        background: linear-gradient(90deg, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.10) 100%);
        border: 1px solid rgba(139,92,246,0.3);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .header-title {
        font-size: 28px;
        font-weight: 700;
        color: #f0f0f0;
        margin: 0;
    }

    .input-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 24px;
    }

    div[data-testid="stNumberInput"] input,
    div[data-testid="stTextInput"] input {
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(139,92,246,0.4) !important;
        border-radius: 8px !important;
        color: #f0f0f0 !important;
        font-family: 'Inter', sans-serif !important;
    }

    div[data-testid="stNumberInput"] label,
    div[data-testid="stTextInput"] label {
        color: #c0c0d0 !important;
        font-weight: 500 !important;
        font-size: 13px !important;
    }

    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        padding: 12px 24px !important;
        width: 100% !important;
        box-shadow: 0 4px 20px rgba(99,102,241,0.4) !important;
    }

    div[data-testid="stButton"] > button[kind="secondary"] {
        background: rgba(239,68,68,0.15) !important;
        border: 1px solid rgba(239,68,68,0.4) !important;
        border-radius: 10px !important;
        color: #fc8181 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 12px 20px !important;
        width: 100% !important;
    }

    div[data-testid="stTabs"] [role="tablist"] {
        background: rgba(255,255,255,0.04);
        border-radius: 12px;
        padding: 6px;
        gap: 4px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    div[data-testid="stTabs"] button[role="tab"] {
        border-radius: 8px !important;
        color: #a0aec0 !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        padding: 8px 18px !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background: rgba(99,102,241,0.25) !important;
        color: #c7d2fe !important;
        border-bottom: 2px solid #6366f1 !important;
    }

    .stat-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 18px 20px;
        text-align: center;
    }
    .stat-value { font-size: 28px; font-weight: 700; color: #c7d2fe; }
    .stat-label { font-size: 12px; color: #718096; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }

    .table-wrapper {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        overflow: hidden;
        margin-top: 16px;
    }
    .fmcsa-table { width: 100%; border-collapse: collapse; font-size: 13px; color: #e2e8f0; }
    .fmcsa-table thead tr { background: rgba(99,102,241,0.12); border-bottom: 1px solid rgba(99,102,241,0.3); }
    .fmcsa-table thead th { padding: 14px 16px; text-align: left; font-weight: 600; font-size: 12px; color: #a5b4fc; text-transform: uppercase; }
    .fmcsa-table tbody tr { border-bottom: 1px solid rgba(255,255,255,0.04); }
    .fmcsa-table tbody td { padding: 13px 16px; vertical-align: middle; }
    .mc-cell { font-family: monospace; font-weight: 600; color: #a5b4fc; }
    .name-cell { font-weight: 600; color: #f0f0f0; }
    .entity-badge { padding: 3px 10px; border-radius: 20px; font-size: 11px; background: rgba(99,102,241,0.2); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.3); }
    .status-active { color: #68d391; font-weight: 600; }
    .status-inactive { color: #f6ad55; font-weight: 600; }
    .status-oos { color: #fc8181; font-weight: 600; }
    .status-dot-green { width:8px;height:8px;border-radius:50%;background:#48bb78;display:inline-block;margin-right:4px;}
    .status-dot-orange { width:8px;height:8px;border-radius:50%;background:#ed8936;display:inline-block;margin-right:4px;}
    .status-dot-red { width:8px;height:8px;border-radius:50%;background:#fc8181;display:inline-block;margin-right:4px;}

    .export-btn-wrap { margin-top: 24px; text-align: center; }
    .stDownloadButton > button {
        background: linear-gradient(135deg, #7c3aed 0%, #ec4899 100%) !important;
        border: none !important; border-radius: 14px !important; color: white !important;
        font-weight: 700 !important; font-size: 16px !important; padding: 16px 48px !important; width: 60% !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar Account & Admin Controls ──────────────────────────────────────────
with st.sidebar:
    st.markdown("### 👤 User Account")
    is_admin = user_info.get("is_admin", False)
    role_badge = "👑 Super Admin" if is_admin else "👤 Standard User"
    st.markdown(f"**User**: `{username}`")
    st.markdown(f"**Role**: `{role_badge}`")

    rem_min = int(remaining_sec // 60)
    st.caption(f"⏳ Session Expires in: **{rem_min} mins**")

    if st.button("🚪 Log Out", key="logout_btn"):
        force_logout("User clicked log out.")

    st.divider()

    if is_admin:
        st.markdown("### 🛡️ Admin Controls")
        admin_mode = st.radio(
            "Admin Actions",
            ["Dashboard", "👥 Manage Users", "⚙️ Rate & Session Limits", "📊 Activity Audit Logs"],
            key="admin_mode_select",
        )

        if admin_mode == "👥 Manage Users":
            st.subheader("Create New User")
            new_u = st.text_input("New Username", key="new_u_input")
            new_p = st.text_input("New Password", type="password", key="new_p_input")
            new_role = st.selectbox("Role", ["Standard User", "Super Admin"], key="new_role_input")
            if st.button("Create Account", key="create_user_btn"):
                is_adm = (new_role == "Super Admin")
                succ, msg = db.create_user(username, new_u, new_p, is_admin=is_adm)
                if succ:
                    st.success(msg)
                else:
                    st.error(msg)

        elif admin_mode == "⚙️ Rate & Session Limits":
            st.subheader("Configure Per-User Speed & Duration")
            all_users = db.get_all_users()
            u_names = [u["username"] for u in all_users]
            if not u_names:
                u_names = [username]
            if username not in u_names:
                u_names.append(username)

            sel_u = st.selectbox("Select User", u_names, key="sel_user_config")
            sel_u_data = next((u for u in all_users if u["username"] == sel_u), {})

            curr_delay = int(sel_u_data.get("delay_ms", user_info.get("delay_ms", 500)))
            curr_dur = float(sel_u_data.get("session_duration_hours", user_info.get("session_duration_hours", 3.0)))

            new_delay = st.number_input("Request Delay (ms)", min_value=0, max_value=10000, value=curr_delay, step=100, key="new_delay_in")
            new_dur = st.number_input("Session Timeout (hours)", min_value=0.5, max_value=72.0, value=curr_dur, step=0.5, key="new_dur_in")

            if st.button("Save User Config", key="save_u_cfg"):
                succ, msg = db.update_user_config(username, sel_u, new_delay, new_dur)
                if sel_u == username:
                    st.session_state["user_info"]["session_duration_hours"] = float(new_dur)
                    st.session_state["user_info"]["delay_ms"] = int(new_delay)
                st.success(f"Updated config for '{sel_u}' successfully.")
                st.rerun()

        elif admin_mode == "📊 Activity Audit Logs":
            st.subheader("Latest Activity Logs (Max 200)")
            logs_df = db.get_activity_logs(limit=200)
            st.dataframe(logs_df, use_container_width=True)


# ── Render Helper HTML Functions ──────────────────────────────────────────────
def status_badge(status: str) -> str:
    s = status.upper()
    if "NOT FOUND" in s or "NOTFOUND" in s:
        return f'<span style="color:#718096;font-style:italic;">Not Found</span>'
    elif "INACTIVE" in s:
        return f'<span class="status-inactive"><span class="status-dot-orange"></span>INACTIVE</span>'
    elif "ACTIVE" in s:
        return f'<span class="status-active"><span class="status-dot-green"></span>ACTIVE</span>'
    elif "OUT" in s or "OOS" in s:
        return f'<span class="status-oos"><span class="status-dot-red"></span>OUT-OF-SERVICE</span>'
    return f'<span style="color:#a0aec0;">{status}</span>'


def mc_cell_html(mc_str: str) -> str:
    if mc_str.startswith("BROKER "):
        parts = mc_str.split(" ", 1)
        return f'<span style="color:#fbbf24;font-weight:700;">{parts[0]}</span> <span class="mc-cell">{parts[1]}</span>'
    return f'<span class="mc-cell">{mc_str}</span>'


def email_cell_html(email: str) -> str:
    if email == "—" or not email:
        return '<span style="color:#4a5568;font-style:italic;font-size:12px;">—</span>'
    return f'<span style="color:#76e4f7;font-size:12px;">{email}</span>'


def render_table(rows: List[dict]) -> str:
    if not rows:
        return '<p style="color:#4a5568;text-align:center;padding:32px;">No data to display.</p>'

    header_cols = [
        "MC Number", "Carrier Name", "Entity Type",
        "Operating Status", "Phone Number", "Email Address", "Location"
    ]
    html = '<div class="table-wrapper"><table class="fmcsa-table"><thead><tr>'
    for col in header_cols:
        html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"

    for row in rows:
        html += "<tr>"
        html += f'<td>{mc_cell_html(row.get("MC Number","—"))}</td>'
        html += f'<td class="name-cell">{row.get("Carrier Name","—")}</td>'
        et = row.get("Entity Type", "—")
        html += f'<td><span class="entity-badge">{et}</span></td>'
        html += f'<td>{status_badge(row.get("Operating Status","—"))}</td>'
        html += f'<td style="color:#cbd5e0;font-size:13px;">{row.get("Phone Number","—")}</td>'
        html += f'<td>{email_cell_html(row.get("Email Address","—"))}</td>'
        html += f'<td style="color:#e2e8f0;font-size:13px;">{row.get("Location","—")}</td>'
        html += "</tr>"

    html += "</tbody></table></div>"
    return html


def df_from_results(rows: List[dict]) -> pd.DataFrame:
    cols = ["MC Number", "Carrier Name", "Entity Type",
            "Operating Status", "Phone Number", "Email Address", "Location"]
    clean = [{c: r.get(c, "—") for c in cols} for r in rows]
    return pd.DataFrame(clean, columns=cols)


def csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD UI
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    """
    <div class="header-banner">
        <div style="font-size:40px;">🚛</div>
        <div>
            <p class="header-title">FMCSA MC Number Scraper</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="input-card">', unsafe_allow_html=True)
col1, col2, col3, col4 = st.columns([2.5, 1.5, 1.2, 1.4])

with col1:
    start_mc = st.number_input(
        "Start MC Number",
        min_value=1,
        max_value=9999999,
        value=int(st.session_state.get("start_mc_input", 1066434)),
        step=1,
        format="%d",
        key="start_mc_input",
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    scrape_btn = st.button("🔍 Start Scraping", type="primary", key="scrape_btn")

with col3:
    st.markdown("<br>", unsafe_allow_html=True)
    stop_btn = st.button("⛔ Stop", type="secondary", key="stop_btn")

with col4:
    st.markdown("<br>", unsafe_allow_html=True)
    clear_btn = st.button("🗑️ Clear History", key="clear_btn")

st.markdown("</div>", unsafe_allow_html=True)

if scrape_btn:
    st.session_state.stop_requested = False
    st.session_state.current_mc = int(start_mc)
    st.session_state.scraping = True

if stop_btn:
    st.session_state.stop_requested = True
    st.session_state.start_mc_val = int(st.session_state.current_mc)

if clear_btn:
    st.session_state.results = []
    st.session_state.scraping = False
    st.session_state.stop_requested = False
    db.log_activity(username, "CLEAR_HISTORY", "User cleared all scraped history")
    st.rerun()

if st.session_state.scraping:
    status_text = st.empty()
    live_table = st.empty()
    count = len(st.session_state.results)

    while not st.session_state.stop_requested:
        mc = st.session_state.current_mc

        status_text.markdown(
            f'<p style="color:#a0aec0;font-size:13px;text-align:center;">🔄 Fetching <b style="color:#c7d2fe;">MC-{mc:07d}</b> &nbsp;·&nbsp; <b style="color:#68d391;">{count}</b> scraped so far</p>',
            unsafe_allow_html=True,
        )

        result = scrape_mc(mc)
        st.session_state.results.append(result)
        st.session_state.current_mc += 1
        count += 1

        preview = st.session_state.results[-10:]
        live_table.markdown(render_table(preview), unsafe_allow_html=True)

        user_delay = int(user_info.get("delay_ms", 500)) / 1000.0
        if user_delay > 0:
            time.sleep(user_delay)

    st.session_state["start_mc_input"] = int(st.session_state.current_mc)
    db.log_activity(username, "HARVEST_MC", f"Scraped batch up to MC-{st.session_state.current_mc:07d} ({count} total)")

    status_text.markdown(
        f'<p style="color:#68d391;font-size:13px;text-align:center;">⛔ Stopped at <b>MC-{st.session_state.current_mc:07d}</b> &nbsp;·&nbsp; <b>{count}</b> total scraped</p>',
        unsafe_allow_html=True,
    )
    st.session_state.scraping = False
    st.rerun()

results = st.session_state.results
# Filter out BROKERS and NOT FOUND records from Carriers Found & Active Carriers metric counts
found = [
    r for r in results 
    if r.get("_found", False) 
    and "BROKER" not in r.get("MC Number", "").upper() 
    and "BROKER" not in r.get("Entity Type", "").upper()
]
active = [
    r for r in found 
    if "ACTIVE" in r.get("Operating Status", "").upper() 
    and "IN" not in r.get("Operating Status", "").upper() 
    and "NOT" not in r.get("Operating Status", "").upper()
]
with_email = [r for r in active if r.get("Email Address", "—") not in ("—", "", None)]

if results:
    sc1, sc2, sc3, sc4 = st.columns(4)
    stats = [
        (len(results), "Total Scraped", "#c7d2fe"),
        (len(found), "Carriers Found", "#68d391"),
        (len(active), "Active Carriers", "#48bb78"),
        (len(with_email), "With Email", "#76e4f7"),
    ]
    for col, (val, label, color) in zip([sc1, sc2, sc3, sc4], stats):
        with col:
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-value" style="color:{color};">{val}</div>'
                f'<div class="stat-label">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs([
        "📋  Complete Master Log",
        "✅  Verified Leads (Active Only)",
        "📧  Raw Active Email List",
    ])

    with tab1:
        st.markdown(render_table(found if found else results), unsafe_allow_html=True)
        df_all = df_from_results(found if found else results)
        st.markdown('<div class="export-btn-wrap">', unsafe_allow_html=True)
        st.download_button(
            label="📥  Export Master Sheet to CSV",
            data=csv_bytes(df_all),
            file_name="fmcsa_master_log.csv",
            mime="text/csv",
            key="dl_master",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        if active:
            st.markdown(render_table(active), unsafe_allow_html=True)
            df_active = df_from_results(active)
            st.markdown('<div class="export-btn-wrap">', unsafe_allow_html=True)
            st.download_button(
                label="📥  Export Active Leads to CSV",
                data=csv_bytes(df_active),
                file_name="fmcsa_verified_leads.csv",
                mime="text/csv",
                key="dl_active",
            )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="color:#4a5568;text-align:center;padding:48px;font-size:15px;">'
                '🚫 No active carriers found yet. Run the scraper first.</p>',
                unsafe_allow_html=True,
            )

    with tab3:
        if with_email:
            st.markdown(
                '<div class="table-wrapper" style="padding:0;">'
                + "".join(
                    f'<div style="padding:10px 16px;border-bottom:1px solid rgba(255,255,255,0.05);display:flex;justify-content:space-between;align-items:center;">'
                    f'<div>'
                    f'<div style="color:#76e4f7;font-size:14px;">{r["Email Address"]}</div>'
                    f'<div style="color:#e2e8f0;font-size:12px;">{r["Carrier Name"]} &nbsp;·&nbsp; {r["MC Number"]} &nbsp;·&nbsp; {r["Location"]}</div>'
                    f'</div>'
                    f'<div style="color:#718096;font-size:11px;">{r["Phone Number"]}</div>'
                    f'</div>'
                    for r in with_email
                )
                + "</div>",
                unsafe_allow_html=True,
            )
            df_email = df_from_results(with_email)
            st.markdown('<div class="export-btn-wrap">', unsafe_allow_html=True)
            st.download_button(
                label="📥  Export Email List to CSV",
                data=csv_bytes(df_email),
                file_name="fmcsa_email_list.csv",
                mime="text/csv",
                key="dl_email",
            )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="color:#4a5568;text-align:center;padding:48px;font-size:15px;">'
                '📧 No emails found yet. Active carriers without emails won\'t appear here.</p>',
                unsafe_allow_html=True,
            )

else:
    st.markdown(
        """
        <div style="text-align:center;padding:72px 32px;">
            <div style="font-size:64px;margin-bottom:16px;">🚛</div>
            <h3 style="color:#e2e8f0;font-size:20px;margin-bottom:8px;">Ready to Scrape</h3>
            <p style="color:#718096;font-size:14px;max-width:400px;margin:0 auto;">
                Enter a start MC number above, then click <strong style="color:#a5b4fc;">Start Scraping</strong>.<br>
                Results appear in real-time as each carrier is fetched.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
