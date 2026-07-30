import uuid
import time
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# Import core scraping logic unchanged from your scrapper module
from scrapper import scrape_mc

# ------------------------------------------------------------------------------
# Streamlit Page Config
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="FMCSA SAFER & SMS Harvester",
    page_icon="🚛",
    layout="wide",
)

# ------------------------------------------------------------------------------
# Supabase Client Initialization (using st.secrets)
# ------------------------------------------------------------------------------
@st.cache_resource
def init_supabase() -> Client:
    """Initialize Supabase client using secrets configured in .streamlit/secrets.toml or Streamlit Cloud."""
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as e:
        st.error(
            f"Missing secret configuration: `{e}`. "
            "Please ensure SUPABASE_URL and SUPABASE_KEY are set in your Streamlit Secrets."
        )
        st.stop()

supabase = init_supabase()

# ------------------------------------------------------------------------------
# Security & Activity Audit Utilities
# ------------------------------------------------------------------------------
def log_activity(email: str, action: str, details: str = ""):
    """Audit logging: Inserts critical user actions into activity_logs."""
    try:
        supabase.table("activity_logs").insert({
            "user_email": email,
            "action": action,
            "details": details,
        }).execute()
    except Exception as e:
        st.error(f"Audit log failure: {e}")

def get_user_record(email: str) -> dict:
    """Retrieves current user details from Supabase."""
    res = supabase.table("users").select("*").eq("email", email).execute()
    return res.data[0] if res.data else None

def update_active_session_token(email: str, token: str):
    """Sets a unique session token for single-device lockout enforcement."""
    supabase.table("users").update({"active_session_id": token}).eq("email", email).execute()

def verify_active_session() -> bool:
    """Verifies that the session token matches the database (enforces single-device lockout)."""
    if not st.session_state.get("authenticated"):
        return False
    user = get_user_record(st.session_state.user_email)
    if not user or user.get("active_session_id") != st.session_state.session_token:
        force_logout("Terminated: Account logged in on another device.")
        return False
    return True

def force_logout(reason: str = "Session expired."):
    """Terminates session and clears local state."""
    if st.session_state.get("authenticated"):
        log_activity(st.session_state.user_email, "FORCE_LOGOUT", reason)
    st.session_state.clear()
    st.session_state["logout_reason"] = reason
    st.rerun()

def get_global_speed_override() -> dict:
    """Retrieves system-wide speed override setting."""
    try:
        res = supabase.table("system_settings").select("value").eq("key", "global_speed_override").execute()
        if res.data:
            return res.data[0]["value"]
    except Exception:
        pass
    return {"enabled": False, "delay_ms": 400}

# ------------------------------------------------------------------------------
# Session State Initialization
# ------------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "session_token" not in st.session_state:
    st.session_state.session_token = ""
if "session_expires_at" not in st.session_state:
    st.session_state.session_expires_at = None
if "scraped_data" not in st.session_state:
    st.session_state.scraped_data = []
if "scraping_active" not in st.session_state:
    st.session_state.scraping_active = False

# Check session timeout on every interaction
if st.session_state.authenticated:
    if datetime.now(timezone.utc) > st.session_state.session_expires_at:
        force_logout("Session automatically expired after maximum duration.")
    else:
        verify_active_session()

# ------------------------------------------------------------------------------
# Login Screen Component
# ------------------------------------------------------------------------------
def render_login_screen():
    st.title("🚛 FMCSA SAFER Scraper Authentication")
    
    if "logout_reason" in st.session_state and st.session_state.logout_reason:
        st.warning(st.session_state.logout_reason)
        st.session_state.logout_reason = ""

    with st.form("login_form"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign In")

        if submit:
            user = get_user_record(email.strip())
            if user and user["password"] == password:
                session_token = str(uuid.uuid4())
                duration = float(user.get("session_duration_hours") or 3.0)
                expires_at = datetime.now(timezone.utc) + timedelta(hours=duration)

                # Set session details in DB (Single Device Lockout enforcement)
                update_active_session_token(user["email"], session_token)

                st.session_state.authenticated = True
                st.session_state.user_email = user["email"]
                st.session_state.is_admin = user.get("is_admin", False)
                st.session_state.session_token = session_token
                st.session_state.session_expires_at = expires_at

                log_activity(user["email"], "LOGIN_SUCCESS", "User authenticated.")
                st.rerun()
            else:
                st.error("Invalid email address or password.")

# ------------------------------------------------------------------------------
# Sidebar Navigation & User Info Panel
# ------------------------------------------------------------------------------
def render_sidebar():
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state.user_email}`")
    st.sidebar.markdown(f"**Role:** `{'Super Admin' if st.session_state.is_admin else 'Standard User'}`")

    # Display real-time expiration countdown
    remaining = st.session_state.session_expires_at - datetime.now(timezone.utc)
    secs_left = max(0, int(remaining.total_seconds()))
    mins, secs = divmod(secs_left, 60)
    hrs, mins = divmod(mins, 60)
    st.sidebar.info(f"⏳ Session Expires In: **{hrs:02d}:{mins:02d}:{secs:02d}**")

    if st.sidebar.button("🔒 Sign Out"):
        log_activity(st.session_state.user_email, "LOGOUT_MANUAL", "User triggered manual sign out.")
        update_active_session_token(st.session_state.user_email, None)
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()

# ------------------------------------------------------------------------------
# Standard User Interface: Scraper Operation
# ------------------------------------------------------------------------------
def render_scraper_tab():
    st.header("Harvest Carrier Registration Data")

    col1, col2 = st.columns(2)
    with col1:
        start_mc = st.number_input("Start MC Number", min_value=1, value=100000, step=1)
    with col2:
        end_mc = st.number_input("End MC Number", min_value=1, value=100005, step=1)

    # Determine delay based on user settings & global speed override
    user_rec = get_user_record(st.session_state.user_email)
    user_delay = user_rec.get("delay_ms", 400) if user_rec else 400
    
    override = get_global_speed_override()
    if override.get("enabled"):
        effective_delay_ms = override.get("delay_ms", 400)
        st.info(f"⚡ Global Speed Override Active: Delay enforced at **{effective_delay_ms} ms**.")
    else:
        effective_delay_ms = user_delay
        st.caption(f"Configured Scraping Delay: **{effective_delay_ms} ms** per request.")

    start_btn = st.button("🚀 Start Scraping", disabled=st.session_state.scraping_active)
    stop_btn = st.button("🛑 Stop Scraping", disabled=not st.session_state.scraping_active)

    if stop_btn:
        st.session_state.scraping_active = False
        st.warning("Scraping cancellation requested...")

    if start_btn:
        if end_mc < start_mc:
            st.error("End MC number must be greater than or equal to Start MC number.")
            return

        st.session_state.scraping_active = True
        log_activity(
            st.session_state.user_email,
            "SCRAPE_START",
            f"Range: MC-{start_mc} to MC-{end_mc}"
        )

        progress_bar = st.progress(0.0)
        status_text = st.empty()
        table_placeholder = st.empty()

        total_records = (end_mc - start_mc) + 1

        for idx, current_mc in enumerate(range(start_mc, end_mc + 1)):
            if not st.session_state.scraping_active:
                st.info("Scraping stopped by user.")
                break

            status_text.text(f"Scraping MC-{current_mc} ({idx + 1}/{total_records})...")

            # Execute Core Scraping Engine (UNCHANGED)
            result = scrape_mc(current_mc)
            st.session_state.scraped_data.append(result)

            # Audit logging individual harvests
            if result.get("_found"):
                log_activity(
                    st.session_state.user_email,
                    "MC_HARVESTED",
                    f"MC: {result['MC Number']} | Name: {result['Carrier Name']}"
                )

            # Update progress UI
            progress = (idx + 1) / total_records
            progress_bar.progress(progress)

            df = pd.DataFrame(st.session_state.scraped_data)
            table_placeholder.dataframe(df.drop(columns=["_found"], errors="ignore"))

            # Enforce request delay
            time.sleep(effective_delay_ms / 1000.0)

        st.session_state.scraping_active = False
        st.success("Scraping operation concluded!")

    # Render persisted results table & download
    if st.session_state.scraped_data:
        st.subheader("Results Data")
        df_results = pd.DataFrame(st.session_state.scraped_data)
        display_df = df_results.drop(columns=["_found"], errors="ignore")
        st.dataframe(display_df, use_container_width=True)

        csv_data = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Results CSV",
            data=csv_data,
            file_name=f"fmcsa_carriers_{int(time.time())}.csv",
            mime="text/csv",
        )

# ------------------------------------------------------------------------------
# Super Admin Controls Tab
# ------------------------------------------------------------------------------
def render_admin_tab():
    st.header("🛡️ System Administration & User Management")

    admin_action = st.tabs([
        "👥 User Accounts",
        "⚙️ Rate Limits & Duration",
        "⚡ Global Speed Override",
        "📋 System Activity Audit"
    ])

    # --- TAB 1: User Management ---
    with admin_action[0]:
        st.subheader("Create New User Account")
        with st.form("create_user_form"):
            new_email = st.text_input("New User Email")
            new_pass = st.text_input("New User Password", type="password")
            new_role = st.selectbox("Role Permission", ["Standard User", "Super Admin"])
            new_delay = st.number_input("Request Delay (ms)", value=400, step=50)
            new_duration = st.number_input("Session Timeout (Hours)", value=3.0, step=0.5)

            if st.form_submit_button("Create User"):
                if new_email and new_pass:
                    try:
                        supabase.table("users").insert({
                            "email": new_email.strip(),
                            "password": new_pass,
                            "is_admin": (new_role == "Super Admin"),
                            "delay_ms": int(new_delay),
                            "session_duration_hours": float(new_duration),
                        }).execute()
                        
                        log_activity(st.session_state.user_email, "ADMIN_USER_CREATED", f"Created: {new_email}")
                        st.success(f"User account `{new_email}` successfully provisioned.")
                    except Exception as e:
                        st.error(f"Failed to create user: {e}")
                else:
                    st.warning("All fields are required.")

        st.subheader("Existing User Accounts")
        users_res = supabase.table("users").select("email, is_admin, delay_ms, session_duration_hours, created_at").execute()
        if users_res.data:
            st.dataframe(pd.DataFrame(users_res.data), use_container_width=True)

    # --- TAB 2: Per-User Speed & Duration Control ---
    with admin_action[1]:
        st.subheader("Per-User Rate Limits & Session Expiration")
        users_list = supabase.table("users").select("email").execute().data
        if users_list:
            selected_user = st.selectbox("Select User Account", [u["email"] for u in users_list])
            user_data = get_user_record(selected_user)

            if user_data:
                with st.form("update_user_settings_form"):
                    updated_delay = st.number_input(
                        "Scraping Delay (ms)",
                        value=int(user_data.get("delay_ms") or 400),
                        step=50
                    )
                    updated_duration = st.number_input(
                        "Session Expiration (Hours)",
                        value=float(user_data.get("session_duration_hours") or 3.0),
                        step=0.5
                    )

                    if st.form_submit_button("Save User Settings"):
                        supabase.table("users").update({
                            "delay_ms": int(updated_delay),
                            "session_duration_hours": float(updated_duration),
                        }).eq("email", selected_user).execute()

                        log_activity(
                            st.session_state.user_email,
                            "ADMIN_USER_UPDATED",
                            f"Target: {selected_user} | Delay: {updated_delay}ms | Duration: {updated_duration}h"
                        )
                        st.success(f"Settings updated for `{selected_user}`.")

    # --- TAB 3: Global Speed Override ---
    with admin_action[2]:
        st.subheader("Global Speed Control")
        st.caption("Enforces a mandatory uniform delay across all standard users, ignoring their specific preferences.")

        override_state = get_global_speed_override()
        
        with st.form("global_speed_form"):
            enable_override = st.checkbox("Enable Global Speed Override", value=override_state.get("enabled", False))
            override_delay = st.number_input("Override Delay (ms)", value=int(override_state.get("delay_ms", 400)), step=50)

            if st.form_submit_button("Apply Global Setting"):
                new_setting = {"enabled": enable_override, "delay_ms": int(override_delay)}
                supabase.table("system_settings").upsert({
                    "key": "global_speed_override",
                    "value": new_setting
                }).execute()

                log_activity(
                    st.session_state.user_email,
                    "ADMIN_SPEED_OVERRIDE",
                    f"Override Active: {enable_override} | Delay: {override_delay}ms"
                )
                st.success("Global speed override configuration applied.")

    # --- TAB 4: Activity Monitoring ---
    with admin_action[3]:
        st.subheader("Centralized Activity Logs (Latest 200 Actions)")
        logs_res = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(200).execute()
        if logs_res.data:
            st.dataframe(pd.DataFrame(logs_res.data), use_container_width=True)

# ------------------------------------------------------------------------------
# Main Application Entry Point
# ------------------------------------------------------------------------------
def main():
    if not st.session_state.authenticated:
        render_login_screen()
    else:
        render_sidebar()

        if st.session_state.is_admin:
            tab1, tab2 = st.tabs(["🚛 Scraper Dashboard", "🛡️ Admin Controls"])
            with tab1:
                render_scraper_tab()
            with tab2:
                render_admin_tab()
        else:
            render_scraper_tab()

if __name__ == "__main__":
    main()
