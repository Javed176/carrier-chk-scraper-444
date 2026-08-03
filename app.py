"""
scraper.py — Two-step Carrier Registration & Snapshot Scraper.
"""

import re
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup
import streamlit as st

SAFER_URL = st.secrets.get("SAFER_ENDPOINT_URL", "")
SMS_REG_URL = st.secrets.get("SMS_ENDPOINT_URL", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _clean(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    return " ".join(text.split()).strip()


def format_mc_number(mc: int, entity_type: str) -> str:
    mc_str = f"MC-{mc:07d}"
    if "BROKER" in entity_type.upper():
        return f"BROKER {mc_str}"
    return mc_str


def fetch_safer_snapshot(mc_number: int) -> Optional[dict]:
    if not SAFER_URL:
        st.error("⚠️ SAFER_ENDPOINT_URL is missing from Streamlit Secrets. Please configure App Settings -> Secrets.")
        return None

    try:
        resp = requests.post(
            SAFER_URL,
            data={
                "query_type": "queryCarrierSnapshot",
                "query_param": "MC_MX",
                "query_string": str(mc_number),
                "searchtype": "ANY",
            },
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    page_text = soup.get_text()

    if "no records found" in page_text.lower() or "your search" in page_text.lower():
        return None

    def get_field(label_text: str) -> str:
        for th in soup.find_all(["th", "td"]):
            if label_text.lower() in _clean(th.get_text()).lower():
                sibling = th.find_next_sibling("td")
                if sibling:
                    return _clean(sibling.get_text())
        return ""

    usdot = ""
    usdot_th = soup.find("a", href=lambda h: h and "USDOTID" in h)
    if usdot_th:
        td = usdot_th.find_parent("th")
        if td:
            td = td.find_next_sibling("td")
            if td:
                usdot = _clean(td.get_text())

    if not usdot:
        match = re.search(r"USDOT Number[:\s]+(\d+)", page_text)
        if match:
            usdot = match.group(1)

    entity_type = get_field("Entity Type")

    status = ""
    for th in soup.find_all("th"):
        th_text = _clean(th.get_text())
        if "USDOT Status" in th_text:
            td = th.find_next_sibling("td")
            if td:
                raw = _clean(td.get_text())
                status = raw.split()[0] if raw else ""
                break

    carrier_name = ""
    title_tag = soup.find("title")
    if title_tag:
        title_text = _clean(title_tag.get_text())
        parts = title_text.replace("SAFER Web - Company Snapshot", "").strip()
        if parts:
            carrier_name = parts

    if not carrier_name:
        carrier_name = get_field("Legal Name")

    if "RECORD INACTIVE" in carrier_name.upper() or "INACTIVE" in carrier_name.upper():
        if not status or status.upper() == "ACTIVE":
            status = "INACTIVE"

    phone = get_field("Phone")

    location = ""
    addr_td = soup.find("td", id="physicaladdressvalue")
    if addr_td:
        addr_text = _clean(addr_td.get_text())
        match = re.search(r"([A-Z\s]+),\s+([A-Z]{2})\s+\d{5}", addr_text)
        if match:
            location = f"{match.group(1).strip()}, {match.group(2)}"
        else:
            lines = [l.strip() for l in addr_td.get_text("\n").split("\n") if l.strip()]
            if len(lines) >= 2:
                location = lines[-1]

    return {
        "usdot": usdot,
        "carrier_name": carrier_name,
        "entity_type": entity_type,
        "status": status,
        "phone": phone,
        "location": location,
    }


def fetch_carrier_email(dot_number: str) -> str:
    if not dot_number or not SMS_REG_URL:
        return ""

    url = SMS_REG_URL.format(dot=dot_number)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(resp.text, "lxml")

    for th in soup.find_all(["th", "td", "label", "span"]):
        text = _clean(th.get_text())
        if text.lower() in ("email", "e-mail", "email address"):
            sibling = th.find_next_sibling("td")
            if sibling:
                email_text = _clean(sibling.get_text())
                if "@" in email_text:
                    return email_text

    email_match = re.search(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", resp.text
    )
    if email_match:
        return email_match.group(0)

    return ""


def scrape_mc(mc_number: int) -> dict:
    base_info = fetch_safer_snapshot(mc_number)

    if not base_info:
        return {
            "MC Number": f"MC-{mc_number:07d}",
            "Carrier Name": "Not Found",
            "Entity Type": "—",
            "Operating Status": "NOT FOUND",
            "Phone Number": "—",
            "Email Address": "—",
            "Location": "—",
            "_found": False,
        }

    cname = (base_info.get("carrier_name") or "").upper()
    raw_status = (base_info.get("status") or "").upper().strip()

    if "INACTIVE" in cname or "RECORD INACTIVE" in cname or "INACTIVE" in raw_status:
        final_status = "INACTIVE"
    elif "OUT-OF-SERVICE" in raw_status or "OOS" in raw_status:
        final_status = "OUT-OF-SERVICE"
    elif raw_status == "ACTIVE":
        final_status = "ACTIVE"
    else:
        final_status = raw_status if raw_status else "ACTIVE"

    email = ""
    if base_info.get("usdot"):
        email = fetch_carrier_email(base_info["usdot"])

    mc_display = format_mc_number(mc_number, base_info.get("entity_type", ""))

    return {
        "MC Number": mc_display,
        "Carrier Name": base_info.get("carrier_name") or "—",
        "Entity Type": base_info.get("entity_type") or "CARRIER",
        "Operating Status": final_status,
        "Phone Number": base_info.get("phone") or "—",
        "Email Address": email or "—",
        "Location": base_info.get("location") or "—",
        "_found": True,
    }
