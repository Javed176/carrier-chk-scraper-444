import os
import sys
import time
import pandas as pd
import streamlit as st

# 1. Fix Python module search path for Streamlit Cloud
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 2. Import local scraper module safely
try:
    from scraper import scrape_mc
except ModuleNotFoundError:
    st.error("Could not find scraper.py. Ensure scraper.py is in your root GitHub folder.")

# -----------------------------------------------------------------------------
# Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FMCSA MC Number Scraper",
    page_icon="🚚",
    layout="wide"
)

# Optional: Supabase Database Setup
try:
    from supabase import create_client, Client
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None
except Exception:
    supabase = None

# -----------------------------------------------------------------------------
# Session State Initialization
# -----------------------------------------------------------------------------
if "is_scraping" not in st.session_state:
    st.session_state.is_scraping = False
if "master_log" not in st.session_state:
    st.session_state.master_log = []
if "current_mc" not in st.session_state:
    st.session_state.current_mc = 1066434

# -----------------------------------------------------------------------------
# Dashboard UI Header Banner
# -----------------------------------------------------------------------------
st.markdown("""
<div style="background-color: #1e2430; padding: 20px; border-radius: 12px; border: 1px solid #2e3646; margin-bottom: 20px;">
    <h2 style="margin:0; color: #ffffff;">🚚 FMCSA MC Number Scraper</h2>
    <p style="margin:5px 0 0 0; color: #9da8b9;">Scrape carrier data from FMCSA SAFER · SMS Registration · Email Extraction</p>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Control Panel (Start MC Input & Action Buttons)
# -----------------------------------------------------------------------------
col_input, col_start, col_stop = st.columns([4, 2, 2])

with col_input:
    start_mc_val = st.number_input(
        "Start MC Number",
        min_value=1,
        value=int(st.session_state.current_mc),
        step=1
    )

with col_start:
    st.write("##")
    if st.button("🔍 Start Scraping", use_container_width=True, type="primary"):
        st.session_state.current_mc = int(start_mc_val)
        st.session_state.is_scraping = True

with col_stop:
    st.write("##")
    if st.button("🛑 Stop", use_container_width=True):
        st.session_state.is_scraping = False

# -----------------------------------------------------------------------------
# Calculate Live Metrics
# -----------------------------------------------------------------------------
log_data = st.session_state.master_log
total_scraped = len(log_data)
carriers_found = sum(1 for r in log_data if r.get("CARRIER NAME") != "RECORD INACTIVE")
active_carriers = sum(1 for r in log_data if str(r.get("OPERATING STATUS")).upper() == "ACTIVE")
with_email = sum(1 for r in log_data if r.get("EMAIL ADDRESS") and r.get("EMAIL ADDRESS") != "-")

if st.session_state.is_scraping:
    st.caption(f"🔄 **Scraping active...** Current target: MC-{st.session_state.current_mc} · {total_scraped} total scraped")
else:
    st.caption(f"🛑 **Stopped** at MC-{st.session_state.current_mc} · {total_scraped} total scraped")

# Metric Cards Layout
m1, m2, m3, m4 = st.columns(4)
m1.metric("TOTAL SCRAPED", total_scraped)
m2.metric("CARRIERS FOUND", carriers_found)
m3.metric("ACTIVE CARRIERS", active_carriers)
m4.metric("WITH EMAIL", with_email)

st.write("---")

# -----------------------------------------------------------------------------
# Main Tabs & Data Tables
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📋 Complete Master Log", 
    "✅ Verified Leads (Active Only)", 
    "📧 Raw Active Email List"
])

df_master = pd.DataFrame(log_data) if log_data else pd.DataFrame(columns=[
    "MC NUMBER", "CARRIER NAME", "ENTITY TYPE", "OPERATING STATUS", "PHONE NUMBER", "EMAIL ADDRESS", "LOCATION"
])

with tab1:
    st.dataframe(df_master, use_container_width=True, hide_index=True)

with tab2:
    if not df_master.empty and "OPERATING STATUS" in df_master.columns:
        df_active = df_master[df_master["OPERATING STATUS"].str.upper() == "ACTIVE"]
        st.dataframe(df_active, use_container_width=True, hide_index=True)
    else:
        st.info("No active carriers scraped yet.")

with tab3:
    if not df_master.empty and "EMAIL ADDRESS" in df_master.columns:
        df_emails = df_master[(df_master["OPERATING STATUS"].str.upper() == "ACTIVE") & (df_master["EMAIL ADDRESS"] != "-")]
        st.dataframe(df_emails[["MC NUMBER", "CARRIER NAME", "EMAIL ADDRESS"]], use_container_width=True, hide_index=True)
    else:
        st.info("No active email leads found yet.")

# -----------------------------------------------------------------------------
# Batch Execution Loop (Runs 1 step per rerun)
# -----------------------------------------------------------------------------
if st.session_state.is_scraping:
    # Convert MC input to integer explicitly to fix 'Unknown format code d' error
    try:
        raw_mc = int(st.session_state.current_mc)
    except (ValueError, TypeError):
        raw_mc = 1066434

    mc_str_clean = str(raw_mc)
    formatted_mc_label = f"MC-{raw_mc}"

    try:
        res = scrape_mc(mc_str_clean)
        
        if res and isinstance(res, dict) and res.get("legal_name"):
            row = {
                "MC NUMBER": formatted_mc_label,
                "CARRIER NAME": res.get("legal_name", "UNKNOWN"),
                "ENTITY TYPE": res.get("entity_type", "CARRIER"),
                "OPERATING STATUS": res.get("operating_status", res.get("status", "INACTIVE")),
                "PHONE NUMBER": res.get("phone", "-"),
                "EMAIL ADDRESS": res.get("email", "-"),
                "LOCATION": res.get("location", "-")
            }
        else:
            row = {
                "MC NUMBER": formatted_mc_label,
                "CARRIER NAME": "RECORD INACTIVE",
                "ENTITY TYPE": "-",
                "OPERATING STATUS": "-",
                "PHONE NUMBER": "-",
                "EMAIL ADDRESS": "-",
                "LOCATION": "-"
            }
            
        st.session_state.master_log.append(row)
        st.session_state.current_mc = raw_mc + 1
        time.sleep(0.5)
        st.rerun()

    except Exception as e:
        st.error(f"Scraper error on MC-{raw_mc}: {e}")
        st.session_state.is_scraping = False
