import os
import sys
import time
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# 1. Path Setup for Streamlit Cloud
# -----------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import local scraper module safely
try:
    from scraper import scrape_mc
except ModuleNotFoundError:
    st.error("Could not find scraper.py. Ensure scraper.py is located in your root GitHub folder.")

# -----------------------------------------------------------------------------
# 2. Page Config & Custom Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FMCSA MC Number Scraper",
    page_icon="🚚",
    layout="wide"
)

st.markdown("""
<style>
    .stApp {
        background-color: #0b1120 !important;
        color: #f1f5f9;
    }

    .header-card {
        background-color: #151e32;
        border: 1px solid #232d48;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
    }
    
    div[data-testid="stMetric"] {
        background-color: #151e32 !important;
        border: 1px solid #232d48 !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
        text-align: center !important;
    }
    div[data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-size: 2.2rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #8292ab !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.08em !important;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        height: 42px !important;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3) !important;
    }

    div.stButton > button[kind="secondary"] {
        background-color: #2a151b !important;
        color: #f87171 !important;
        border: 1px solid #7f1d1d !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        height: 42px !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        background-color: transparent;
        border-bottom: 1px solid #232d48;
    }
    .stTabs [data-baseweb="tab"] {
        color: #94a3b8 !important;
        font-weight: 600 !important;
        padding-bottom: 12px !important;
    }
    .stTabs [aria-selected="true"] {
        color: #ef4444 !important;
        border-bottom-color: #ef4444 !important;
    }
    
    div[data-testid="stDataFrame"] {
        background-color: #151e32;
        border: 1px solid #232d48;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. Session State Initialization
# -----------------------------------------------------------------------------
if "is_scraping" not in st.session_state:
    st.session_state.is_scraping = False
if "master_log" not in st.session_state:
    st.session_state.master_log = []
if "current_mc" not in st.session_state:
    st.session_state.current_mc = 1066434
if "last_raw_response" not in st.session_state:
    st.session_state.last_raw_response = None

# -----------------------------------------------------------------------------
# 4. Header Banner
# -----------------------------------------------------------------------------
st.markdown("""
<div class="header-card">
    <div style="display: flex; align-items: center; gap: 16px;">
        <span style="font-size: 32px;">🚚</span>
        <div>
            <h2 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 700;">FMCSA MC Number Scraper</h2>
            <p style="margin: 4px 0 0 0; color: #8292ab; font-size: 14px;">Scrape carrier data from FMCSA SAFER · SMS Registration · Email Extraction</p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. Control Panel & Actions
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
    if st.button("🛑 Stop", use_container_width=True, type="secondary"):
        st.session_state.is_scraping = False

log_data = st.session_state.master_log
total_scraped = len(log_data)

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
if st.session_state.is_scraping:
    st.markdown(f"<p style='text-align: center; color: #10b981; font-weight: 600;'>🟢 Scraping active at MC-{st.session_state.current_mc} · {total_scraped} total scraped</p>", unsafe_allow_html=True)
else:
    st.markdown(f"<p style='text-align: center; color: #f87171; font-weight: 600;'>🔴 Stopped at MC-{st.session_state.current_mc} · {total_scraped} total scraped</p>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. Metrics Layout
# -----------------------------------------------------------------------------
carriers_found = sum(1 for r in log_data if r.get("CARRIER NAME") != "RECORD INACTIVE")
active_carriers = sum(1 for r in log_data if "ACTIVE" in str(r.get("OPERATING STATUS")).upper())
with_email = sum(1 for r in log_data if r.get("EMAIL ADDRESS") and r.get("EMAIL ADDRESS") not in ["-", "NONE", "N/A"])

m1, m2, m3, m4 = st.columns(4)
m1.metric("TOTAL SCRAPED", total_scraped)
m2.metric("CARRIERS FOUND", carriers_found)
m3.metric("ACTIVE CARRIERS", active_carriers)
m4.metric("WITH EMAIL", with_email)

# -----------------------------------------------------------------------------
# 7. Raw Scraper Debug Panel
# -----------------------------------------------------------------------------
with st.expander("🛠️ Raw Scraper Output (Debug Mode - Click to Inspect)", expanded=False):
    st.write("This shows the raw response returned by `scrape_mc()` for the latest request:")
    st.json(st.session_state.last_raw_response if st.session_state.last_raw_response else {"info": "No request made yet. Start scraping to view raw output."})

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 8. Main Data Tabs
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📋 Complete Master Log", 
    "✅ Verified Leads (Active Only)", 
    "📧 Raw Active Email List"
])

columns_order = ["MC NUMBER", "CARRIER NAME", "ENTITY TYPE", "OPERATING STATUS", "PHONE NUMBER", "EMAIL ADDRESS", "LOCATION"]

df_master = pd.DataFrame(log_data) if log_data else pd.DataFrame(columns=columns_order)

with tab1:
    st.dataframe(df_master, use_container_width=True, hide_index=True)

with tab2:
    if not df_master.empty and "OPERATING STATUS" in df_master.columns:
        df_active = df_master[df_master["OPERATING STATUS"].str.contains("ACTIVE", case=False, na=False)]
        st.dataframe(df_active, use_container_width=True, hide_index=True)
    else:
        st.info("No active carriers scraped yet.")

with tab3:
    if not df_master.empty and "EMAIL ADDRESS" in df_master.columns:
        df_emails = df_master[(df_master["OPERATING STATUS"].str.contains("ACTIVE", case=False, na=False)) & (df_master["EMAIL ADDRESS"] != "-")]
        st.dataframe(df_emails[["MC NUMBER", "CARRIER NAME", "EMAIL ADDRESS"]], use_container_width=True, hide_index=True)
    else:
        st.info("No active email leads found yet.")

# -----------------------------------------------------------------------------
# 9. Response Parser Function
# -----------------------------------------------------------------------------
def parse_carrier_response(res, mc_int):
    formatted_mc = f"MC-{mc_int}"
    
    if not res:
        return {
            "MC NUMBER": formatted_mc,
            "CARRIER NAME": "RECORD INACTIVE",
            "ENTITY TYPE": "-",
            "OPERATING STATUS": "-",
            "PHONE NUMBER": "-",
            "EMAIL ADDRESS": "-",
            "LOCATION": "-"
        }
    
    if isinstance(res, dict):
        name = (
            res.get("legal_name") or res.get("carrier_name") or res.get("name") or 
            res.get("CARRIER NAME") or res.get("company_name") or res.get("legalName") or
            res.get("dba_name")
        )
        status = (
            res.get("operating_status") or res.get("status") or res.get("OPERATING STATUS") or 
            res.get("operatingStatus") or res.get("carrier_status") or res.get("authority_status")
        )
        entity = (
            res.get("entity_type") or res.get("entity") or res.get("ENTITY TYPE") or 
            res.get("entityType") or res.get("type") or "CARRIER"
        )
        phone = (
            res.get("phone") or res.get("phone_number") or res.get("PHONE NUMBER") or 
            res.get("phoneNumber") or "-"
        )
        email = (
            res.get("email") or res.get("email_address") or res.get("EMAIL ADDRESS") or 
            res.get("emailAddress") or "-"
        )
        location = (
            res.get("location") or res.get("address") or res.get("LOCATION") or 
            res.get("phy_location") or res.get("city_state") or "-"
        )

        if name:
            status_upper = str(status).upper() if status else "INACTIVE"
            formatted_status = "🟢 ACTIVE" if ("ACTIVE" in status_upper or "AUTHORIZED" in status_upper) else f"🔴 {status_upper}"

            return {
                "MC NUMBER": formatted_mc,
                "CARRIER NAME": str(name).upper(),
                "ENTITY TYPE": str(entity).upper(),
                "OPERATING STATUS": formatted_status,
                "PHONE NUMBER": str(phone),
                "EMAIL ADDRESS": str(email).upper(),
                "LOCATION": str(location).upper()
            }

    return {
        "MC NUMBER": formatted_mc,
        "CARRIER NAME": "RECORD INACTIVE",
        "ENTITY TYPE": "-",
        "OPERATING STATUS": "-",
        "PHONE NUMBER": "-",
        "EMAIL ADDRESS": "-",
        "LOCATION": "-"
    }

# -----------------------------------------------------------------------------
# 10. Execution Loop
# -----------------------------------------------------------------------------
if st.session_state.is_scraping:
    try:
        raw_mc = int(st.session_state.current_mc)
    except (ValueError, TypeError):
        raw_mc = 1066434

    try:
        # Attempt scrape with int and fallback string
        try:
            res = scrape_mc(raw_mc)
        except Exception:
            res = scrape_mc(str(raw_mc))

        st.session_state.last_raw_response = res
        parsed_row = parse_carrier_response(res, raw_mc)
        st.session_state.master_log.append(parsed_row)
        st.session_state.current_mc = raw_mc + 1
        time.sleep(0.5)
        st.rerun()

    except Exception as e:
        st.error(f"Scraper execution error on MC-{raw_mc}: {e}")
        st.session_state.is_scraping = False
