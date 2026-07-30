"""
app.py — FMCSA SAFER MC Number Range Scraper
A dark-themed Streamlit dashboard with Supabase RBAC, Session Locking & Admin Controls.
"""

import io
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Import scraper function
from scraper import scrape_mc

# ── Import Supabase Client ────────────────────────────────────────────────────
# Ensure st.secrets or environment variables contain SUPABASE_URL and SUPABASE_KEY
try:
    from supabase import create_client, Client
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    supabase = None

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FMCSA MC Scraper",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Root & body ──────────────────────────────────────────────────────── */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        min-height: 100vh;
    }

    /* ── Hide Streamlit default chrome ───────────────────────────────────── */
    #MainMenu, footer, header { visibility: hidden; }

    /* ── Header banner ───────────────────────────────────────────────────── */
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
    .header-sub {
        font-size: 13px;
        color: #a0aec0;
        margin: 4px 0 0 0;
    }

    /* ── Input card ──────────────────────────────────────────────────────── */
    .input-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 24px;
    }

    /* ── Streamlit number-input & button overrides ───────────────────────── */
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

    /* ── Primary scrape button ───────────────────────────────────────────── */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        padding: 12px 32px !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 20px rgba(99,102,241,0.4) !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 28px rgba(99,102,241,0.6) !important;
    }

    /* ── Stop button ─────────────────────────────────────────────────────── */
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: rgba(239,68,68,0.15) !important;
        border: 1px solid rgba(239,68,68,0.4) !important;
        border-radius: 10px !important;
        color: #fc8181 !important;
        font-weight: 600 !important;
        width: 100% !important;
    }

    /* ── Tab bar ─────────────────────────────────────────────────────────── */
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
        transition: all 0.2s ease !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background: rgba(99,102,241,0.25) !important;
        color: #c7d2fe !important;
        border-bottom: 2px solid #6366f1 !important;
    }

    /* ── Stats row ───────────────────────────────────────────────────────── */
    .stat-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 18px 20px;
        text-align: center;
    }
    .stat-value {
        font-size: 28px;
        font-weight: 700;
        color: #c7d2fe;
    }
    .stat-label {
        font-size: 12px;
        color: #718096;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 4px;
    }

    /* ── Table wrapper ───────────────────────────────────────────────────── */
    .table-wrapper {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        overflow: hidden;
        margin-top: 16px;
    }

    /* ── Custom HTML table ───────────────────────────────────────────────── */
    .fmcsa-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        color: #e2e8f0;
    }
    .fmcsa-table thead tr {
        background: rgba(99,102,241,0.12);
        border-bottom: 1px solid rgba(99,102,241,0.3);
    }
    .fmcsa-table thead th {
        padding: 14px 16px;
        text-align: left;
        font-weight: 600;
        font-size: 12px;
        color: #a5b4fc;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        white-space: nowrap;
    }
    .fmcsa-table tbody tr {
        border-bottom: 1px solid rgba(255,255,255,0.04);
        transition: background 0.15s;
    }
    .fmcsa-table tbody tr:hover {
        background: rgba(255,255,255,0.04);
    }
    .fmcsa-table tbody td {
        padding: 13px 16px;
        color: #e2e8f0;
        vertical-align: middle;
    }
    .mc-cell {
        font-family: 'Courier New', monospace;
        font-weight: 600;
        color: #a5b4fc;
        font-size: 13px;
    }
    .broker-prefix {
        color: #fbbf24;
        font-weight: 700;
    }
    .name-cell {
        font-weight: 600;
        color: #f0f0f0;
    }
    .entity-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        background: rgba(99,102,241,0.2);
        color: #a5b4fc;
        border: 1px solid rgba(99,102,241,0.3);
        text-transform: uppercase;
    }
    .status-active {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #68d391;
        font-weight: 600;
        font-size: 13px;
    }
    .status-inactive {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #f6ad55;
        font-weight: 600;
        font-size: 13px;
    }
    .status-oos {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #fc8181;
        font-weight: 600;
        font-size: 13px;
    }
    .status-dot-green  { width:8px;height:8px;border-radius:50%;background:#48bb78;display:inline-block;box-shadow:0 0 6px #48bb78; }
    .status-dot-orange { width:8px;height:8px;border-radius:50%;background:#ed8936;display:inline-block;box-shadow:0 0 6px #ed8936; }
    .status-dot-red    { width:8px;height:8px;border-radius:50%;background:#fc8181;display:inline-block;box-shadow:0 0 6px #fc8181; }
    .phone-cell { color: #cbd5e0; font-size: 13px; }
    .email-cell { color: #76e4f7; font-size: 12px; }
    .email-none { color: #4a5568; font-style: italic; font-size: 12px; }
    .location-cell { color: #e2e8f0; font-size: 13px; }

    /* ── Export button ───────────────────────────────────────────────────── */
    .export-btn-wrap {
        margin-top: 24px;
        text-align: center;
    }
    .stDownloadButton > button {
        background: linear-gradient(135deg, #7c3aed 0%, #ec4899 100%) !important;
        border: none !important;
        border-radius: 14px !important;
        color: white !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        padding: 16px 48px !important;
        width: 60% !important;
        letter-spacing: 0.3px !important;
        box-shadow: 0 6px 30px rgba(124,58,237,0.5) !important;
        transition: all 0.2s ease !important;
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 40px rgba(236,72,153,0.5) !important;
    }

    /* ── Progress bar ────────────────────────────────────────────────────── */
    div[data-testid="stProgress"] > div {
        background: rgba(99,102,241,0.2) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #6366f1, #8b5cf6) !important;
        border-radius: 8px !important;
    }

    /* ── Info / warning boxes ─────────────────────────────────────────────── */
    div[data-testid="stAlert"] {
        border-radius: 10px !important;
        border: 1px solid rgba(99,102,241,0.3) !important;
    }

    /* ── Email list ──────────────────────────────────────────────────────── */
    .email-list-item {
        padding: 10px 16px;
        border-bottom: 1px solid rgba(255,255,255,0.05);
        color: #76e4f7;
        font-size: 13px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .email-list-item:hover { background: rgba(255,255,255,0.03); }
    .email-list-name { color: #e2e8f0; font-weight: 500; font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session State Init ────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "session_token" not in st.session_state:
    st.session_state.session_token = None
if "login_time" not in st.session_state:
    st.session_state.login_time = None

if "results" not in st.session_state:
    st.session_state.results = []
if "scraping" not in st.session_state:
    st.session_state.scraping = False
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "current_mc" not in st.session_state:
    st.session_state.current_mc = 1

# ── Helper: Audit Logging ─────────────────────────────────────────────────────
def log_activity(action: str, details: str = ""):
    """Save critical actions to activity_logs table in Supabase."""
    if not supabase or not st.session_state.user_data:
        return
    try:
        user_email = st.session_state.user_data.get("email", "unknown")
        user_id = st.session_state.user_data.get("id")
        supabase.table("activity_logs").insert({
            "user_id": user_id,
            "email": user_email,
            "action": action,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception:
        pass

# ── Security & Session Management ─────────────────────────────────────────────
def verify_active_session() -> bool:
    """Check if the current session_token matches Supabase. If overwritten, terminate session."""
    if not supabase or not st.session_state.authenticated:
        return True
    try:
        user_id = st.session_state.user_data.get("id")
        res = supabase.table("users").select("active_session_id").eq("id", user_id).single().execute()
        if res.data and res.data.get("active_session_id") != st.session_state.session_token:
            force_logout("Terminated: Logged in from another device/browser.")
            return False
    except Exception:
        pass
    return True

def force_logout(reason: str = "Session expired."):
    """Force logout and clear state."""
    log_activity("FORCE_LOGOUT", reason)
    st.session_state.authenticated = False
    st.session_state.user_data = None
    st.session_state.session_token = None
    st.session_state.login_time = None
    st.session_state.scraping = False
    st.warning(reason)
    st.rerun()

def check_session_expiration():
    """Verify session duration against limit."""
    if not st.session_state.authenticated or not st.session_state.login_time:
        return
    duration_hours = st.session_state.user_data.get("session_duration_hours", 3)
    expiry_time = st.session_state.login_time + timedelta(hours=duration_hours)
    if datetime.utcnow() >= expiry_time:
        force_logout("Session expired automatically due to time limit.")

# ── Authentication UI ─────────────────────────────────────────────────────────
def render_login():
    """Render Login Form."""
    st.markdown(
        """
        <div style="max-width:400px;margin:80px auto;padding:32px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:16px;text-align:center;">
            <div style="font-size:48px;margin-bottom:12px;">🚛</div>
            <h2 style="color:#f0f0f0;margin-bottom:24px;">FMCSA Scraper Login</h2>
        </div>
        """,
        unsafe_allow_html=True
    )
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log In", type="primary")

        if submitted:
            if not supabase:
                st.error("Supabase connection not configured in st.secrets.")
                return
            try:
                # Basic Auth check against Supabase 'users' table
                res = supabase.table("users").select("*").eq("email", email).eq("password_hash", password).execute()
                if res.data and len(res.data) > 0:
                    user = res.data[0]
                    session_token = str(uuid.uuid4())
                    
                    # Store active session token
                    supabase.table("users").update({"active_session_id": session_token}).eq("id", user["id"]).execute()
                    
                    st.session_state.authenticated = True
                    st.session_state.user_data = user
                    st.session_state.session_token = session_token
                    st.session_state.login_time = datetime.utcnow()
                    
                    log_activity("LOGIN_SUCCESS", "User logged in successfully")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
            except Exception as e:
                st.error(f"Login error: {str(e)}")

# ── Admin Panel ───────────────────────────────────────────────────────────────
def render_admin_dashboard():
    """Render Admin Controls for Super Admins."""
    st.markdown("### 🛡️ Admin Controls")
    
    admin_tabs = st.tabs(["👥 User Lifecycle Management", "⚡ Speed & Session Controls", "📜 Activity Logs"])
    
    with admin_tabs[0]:
        st.markdown("#### Create New User")
        with st.form("create_user_form"):
            new_email = st.text_input("User Email")
            new_password = st.text_input("Password", type="password")
            is_admin = st.checkbox("Grant Super Admin Privileges")
            delay_ms = st.number_input("Custom Delay (ms)", value=1000, step=100)
            duration_hrs = st.number_input("Session Duration (Hours)", value=3, step=1)
            
            if st.form_submit_button("Create Account"):
                if new_email and new_password:
                    try:
                        supabase.table("users").insert({
                            "email": new_email,
                            "password_hash": new_password,
                            "is_admin": is_admin,
                            "delay_ms": delay_ms,
                            "session_duration_hours": duration_hrs
                        }).execute()
                        log_activity("ADMIN_CREATE_USER", f"Created user: {new_email}")
                        st.success(f"User {new_email} created successfully!")
                    except Exception as e:
                        st.error(f"Failed to create user: {str(e)}")

    with admin_tabs[1]:
        st.markdown("#### Global Speed Override & Rate Limits")
        try:
            cfg = supabase.table("system_config").select("*").eq("key", "global_speed_override").execute()
            override_active = cfg.data[0].get("value", False) if cfg.data else False
            
            new_override = st.toggle("Enable Global Speed Override", value=override_active)
            global_delay = st.number_input("Global Fixed Delay (ms)", value=2000, step=100)
            
            if st.button("Save Global Settings"):
                supabase.table("system_config").upsert({"key": "global_speed_override", "value": new_override, "delay_ms": global_delay}).execute()
                log_activity("ADMIN_UPDATE_SPEED_OVERRIDE", f"Override: {new_override}, Delay: {global_delay}ms")
                st.success("Global speed settings updated!")
        except Exception as e:
            st.error(f"Error loading system configuration: {str(e)}")

    with admin_tabs[2]:
        st.markdown("#### Centralized Audit Trail (Last 200 Actions)")
        try:
            logs = supabase.table("activity_logs").select("*").order("timestamp", desc=True).limit(200).execute()
            if logs.data:
                st.dataframe(pd.DataFrame(logs.data), use_container_width=True)
            else:
                st.info("No activity logs found.")
        except Exception as e:
            st.error(f"Error fetching logs: {str(e)}")

# ── App UI Helpers ────────────────────────────────────────────────────────────
def status_badge(status: str) -> str:
    s = status.upper()
    if "ACTIVE" in s and "IN" not in s:
        return f'<span class="status-active"><span class="status-dot-green"></span>ACTIVE</span>'
    elif "INACTIVE" in s:
        return f'<span class="status-inactive"><span class="status-dot-orange"></span>INACTIVE</span>'
    elif "OUT" in s or "OOS" in s:
        return f'<span class="status-oos"><span class="status-dot-red"></span>OUT-OF-SERVICE</span>'
    elif "NOT FOUND" in s:
        return f'<span style="color:#4a5568;font-style:italic;">Not Found</span>'
    return f'<span style="color:#a0aec0;">{status}</span>'


def mc_cell_html(mc_str: str) -> str:
    if mc_str.startswith("BROKER "):
        parts = mc_str.split(" ", 1)
        return f'<span class="broker-prefix">{parts[0]}</span> <span class="mc-cell">{parts[1]}</span>'
    return f'<span class="mc-cell">{mc_str}</span>'


def email_cell_html(email: str) -> str:
    if email == "—" or not email:
        return '<span class="email-none">—</span>'
    return f'<span class="email-cell">{email}</span>'


def render_table(rows: List[dict]) -> str:
    """Build the custom HTML table."""
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
        html += f'<td class="phone-cell">{row.get("Phone Number","—")}</td>'
        html += f'<td>{email_cell_html(row.get("Email Address","—"))}</td>'
        html += f'<td class="location-cell">{row.get("Location","—")}</td>'
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
# MAIN APP FLOW
# ══════════════════════════════════════════════════════════════════════════════

# 1. Gatekeeping: Require Authentication
if not st.session_state.authenticated:
    render_login()
    st.stop()

# 2. Security Verification Checks
if not verify_active_session():
    st.stop()
check_session_expiration()

# 3. Sidebar Controls & Expiration Timer
with st.sidebar:
    st.markdown(f"**Logged in as:** `{st.session_state.user_data.get('email')}`")
    
    # Real-time Auto-Locking Session Expiration Timer (JS Component)
    duration_hrs = st.session_state.user_data.get("session_duration_hours", 3)
    expiry_time_dt = st.session_state.login_time + timedelta(hours=duration_hrs)
    remaining_seconds = max(0, int((expiry_time_dt - datetime.utcnow()).total_seconds()))
    
    components.html(
        f"""
        <div style="color:#a5b4fc;font-size:13px;font-family:sans-serif;padding:8px;background:rgba(255,255,255,0.05);border-radius:8px;">
            ⏳ Session Expires In: <b id="timer">--:--</b>
        </div>
        <script>
            var seconds = {remaining_seconds};
            function updateTimer() {{
                var m = Math.floor(seconds / 60);
                var s = seconds % 60;
                document.getElementById('timer').innerText = 
                    (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                if (seconds <= 0) {{
                    window.parent.postMessage({{type: 'streamlit:force_logout'}}, '*');
                }} else {{
                    seconds--;
                }}
            }}
            setInterval(updateTimer, 1000);
            updateTimer();
        </script>
        """,
        height=50,
    )
    
    if st.button("Logout", type="secondary"):
        log_activity("MANUAL_LOGOUT", "User clicked logout")
        st.session_state.authenticated = False
        st.session_state.user_data = None
        st.session_state.session_token = None
        st.rerun()

    st.divider()

# 4. Check RBAC: Admin vs Scraper UI
is_admin_user = st.session_state.user_data.get("is_admin", False)
if is_admin_user:
    app_mode = st.sidebar.radio("Navigation", ["🚛 Scraper Dashboard", "🛡️ Admin Controls"])
else:
    app_mode = "🚛 Scraper Dashboard"

if app_mode == "🛡️ Admin Controls" and is_admin_user:
    render_admin_dashboard()
    st.stop()

# ── Scraper Header ────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="header-banner">
        <div style="font-size:40px;">🚛</div>
        <div>
            <p class="header-title">FMCSA MC Number Scraper</p>
            <p class="header-sub">Scrape carrier data from FMCSA SAFER · SMS Registration · Email Extraction</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Input card ────────────────────────────────────────────────────────────────
st.markdown('<div class="input-card">', unsafe_allow_html=True)
col1, col2, col3 = st.columns([3, 1.5, 1.5])

with col1:
    start_mc = st.number_input(
        "Start MC Number",
        min_value=1,
        max_value=9_999_999,
        value=1800000,
        step=1,
        format="%d",
        key="start_mc",
    )
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    scrape_btn = st.button("🔍 Start Scraping", type="primary", key="scrape_btn")
with col3:
    st.markdown("<br>", unsafe_allow_html=True)
    stop_btn = st.button("⛔ Stop", type="secondary", key="stop_btn")

st.markdown("</div>", unsafe_allow_html=True)

# ── Start / Stop triggers ─────────────────────────────────────────────────────
if scrape_btn:
    st.session_state.results = []
    st.session_state.stop_requested = False
    st.session_state.current_mc = int(start_mc)
    st.session_state.scraping = True
    log_activity("SCRAPE_STARTED", f"Started scraping from MC-{start_mc}")

if stop_btn:
    st.session_state.stop_requested = True
    log_activity("SCRAPE_STOPPED", f"Stopped at MC-{st.session_state.current_mc}")

# ── Scraping loop (runs until Stop is clicked) ────────────────────────────────
if st.session_state.scraping:
    if "current_mc" not in st.session_state:
        st.session_state.current_mc = int(start_mc)

    status_text = st.empty()
    live_table = st.empty()
    count = len(st.session_state.results)

    while not st.session_state.stop_requested:
        # Determine delay from Admin Override or User Profile Rate Limits
        delay_ms = st.session_state.user_data.get("delay_ms", 1000)
        if supabase:
            try:
                cfg = supabase.table("system_config").select("*").eq("key", "global_speed_override").execute()
                if cfg.data and cfg.data[0].get("value", False):
                    delay_ms = cfg.data[0].get("delay_ms", delay_ms)
            except Exception:
                pass

        mc = st.session_state.current_mc

        status_text.markdown(
            f'<p style="color:#a0aec0;font-size:13px;text-align:center;">🔄 Fetching <b style="color:#c7d2fe;">MC-{mc:07d}</b> &nbsp;·&nbsp; <b style="color:#68d391;">{count}</b> scraped so far</p>',
            unsafe_allow_html=True,
        )

        result = scrape_mc(mc)
        st.session_state.results.append(result)
        
        # Log harvest audit action
        log_activity("MC_HARVEST", f"Harvested MC-{mc}")

        st.session_state.current_mc += 1
        count += 1

        # Live preview (last 10 rows)
        preview = st.session_state.results[-10:]
        live_table.markdown(render_table(preview), unsafe_allow_html=True)

        time.sleep(delay_ms / 1000.0)

    status_text.markdown(
        f'<p style="color:#68d391;font-size:13px;text-align:center;">⛔ Stopped at <b>MC-{st.session_state.current_mc:07d}</b> &nbsp;·&nbsp; <b>{count}</b> total scraped</p>',
        unsafe_allow_html=True,
    )
    st.session_state.scraping = False

# ── Results tabs ──────────────────────────────────────────────────────────────
results = st.session_state.results
found = [r for r in results if r.get("_found", False)]
active = [r for r in found if "ACTIVE" in r.get("Operating Status", "").upper() and "IN" not in r.get("Operating Status", "").upper()]
with_email = [r for r in active if r.get("Email Address", "—") not in ("—", "", None)]

if results:
    # ── Stats row ─────────────────────────────────────────────────────────────
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

    # ── Tabs ──────────────────────────────────────────────────────────────────
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
                    f'<div class="email-list-item">'
                    f'<div>'
                    f'<div class="email-cell" style="font-size:14px;">{r["Email Address"]}</div>'
                    f'<div class="email-list-name">{r["Carrier Name"]} &nbsp;·&nbsp; {r["MC Number"]} &nbsp;·&nbsp; {r["Location"]}</div>'
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
    # Empty state
    st.markdown(
        """
        <div style="text-align:center;padding:72px 32px;">
            <div style="font-size:64px;margin-bottom:16px;">🚛</div>
            <h3 style="color:#e2e8f0;font-size:20px;margin-bottom:8px;">Ready to Scrape</h3>
            <p style="color:#718096;font-size:14px;max-width:400px;margin:0 auto;">
                Enter a start and end MC number above, then click <strong style="color:#a5b4fc;">Start Scraping</strong>.<br>
                Results appear in real-time as each carrier is fetched.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
