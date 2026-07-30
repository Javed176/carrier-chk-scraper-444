import os
import sys
import io
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd

# 1. Import Streamlit first
import streamlit as st

# 2. Fix Python module search path for Streamlit Cloud
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 3. Import local scraper module
try:
    from scraper import scrape_mc
except ModuleNotFoundError:
    st.error("Could not find scraper.py. Make sure scraper.py is in your root GitHub folder.")

# -----------------------------------------------------------------------------
# 4. Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FMCSA SAFER & SMS Harvester",
    page_icon="🚚",
    layout="wide"
)

# -----------------------------------------------------------------------------
# 5. Supabase Database Setup
# -----------------------------------------------------------------------------
try:
    from supabase import create_client, Client
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    supabase = None

# -----------------------------------------------------------------------------
# 6. User Interface & Scraper Logic
# -----------------------------------------------------------------------------
st.title("🚚 FMCSA SAFER & SMS Harvester")
st.write("Enter an MC or DOT number to scrape and filter carrier data.")

# Input layout
col1, col2 = st.columns([3, 1])

with col1:
    mc_input = st.text_input("Enter MC Number (e.g., 123456):", placeholder="123456")

with col2:
    st.write("##") # Spacing adjustment for button alignment
    run_btn = st.button("Scrape Carrier", use_container_width=True)

# Processing and Conditionals Logic
if run_btn:
    if not mc_input.strip():
        st.warning("⚠️ Please enter an MC or DOT number before scraping.")
    else:
        with st.spinner(f"Scraping data for MC #{mc_input.strip()}..."):
            try:
                # Call scraper function
                data = scrape_mc(mc_input.strip())
                
                if not data:
                    st.error("❌ No data returned. Please check the MC number and try again.")
                else:
                    st.divider()
                    
                    # ---------------------------------------------------------
                    # Conditionals / Filter Section
                    # Adjust dictionary keys to match what scrape_mc() returns
                    # ---------------------------------------------------------
                    status = str(data.get("status", "")).upper()
                    entity_type = str(data.get("entity_type", "")).upper()
                    
                    if "AUTHORIZED" in status and "CARRIER" in entity_type:
                        st.success(f"✅ **ACTIVE CARRIER FOUND**: {data.get('legal_name', 'N/A')}")
                    elif "BROKER" in entity_type:
                        st.warning(f"⚠️ **ENTITY IS A BROKER**: {data.get('legal_name', 'N/A')}")
                    elif "INACTIVE" in status or "NOT AUTHORIZED" in status:
                        st.error(f"🚫 **INACTIVE OR UNAUTHORIZED**: Status is currently '{status}'")
                    else:
                        st.info(f"ℹ️ **Carrier Status**: {status if status else 'Unknown'}")

                    # Display scraped details
                    st.subheader("Carrier Details")
                    
                    # If returned data is a dictionary, display as JSON or Table
                    if isinstance(data, dict):
                        st.json(data)
                    elif isinstance(data, pd.DataFrame):
                        st.dataframe(data, use_container_width=True)

            except Exception as e:
                st.error(f"An error occurred while running the scraper: {e}")
