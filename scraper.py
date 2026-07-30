"""
scraper.py — Two-step FMCSA SAFER + SMS Carrier Registration scraper.

Step 1: POST to SAFER with MC number → get base carrier data + USDOT number
Step 2: GET SMS Carrier Registration page using USDOT → extract email
"""

import re
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup

# ── Request headers to mimic a real browser ──────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://safer.fmcsa.dot.gov/CompanySnapshot.aspx",
}

SAFER_URL = "https://safer.fmcsa.dot.gov/query.asp"
SMS_REG_URL = "https://ai.fmcsa.dot.gov/SMS/Carrier/{dot}/CarrierRegistration.aspx"

REQUEST_DELAY = 0.4  # seconds between requests


def _clean(text: str) -> str:
    """Strip whitespace and HTML entities from a string."""
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    return " ".join(text.split()).strip()


def format_mc_number(mc: int, entity_type: str) -> str:
    """Return MC display string, prefixed with BROKER if applicable."""
    mc_str = f"MC-{mc:07d}"
    if "BROKER" in entity_type.upper():
        return f"BROKER {mc_str}"
    return mc_str


def fetch_safer_snapshot(mc_number: int) -> Optional[dict]:
    """
    Step 1: Scrape SAFER Company Snapshot for a given MC number.
    Returns a dict with carrier info, or None if not found.
    """
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

    # Detect "not found" pages
    if "no records found" in page_text.lower() or "your search" in page_text.lower():
        return None

    # ── Helper: extract a queryfield cell after a label ──────────────────────
    def get_field(label_text: str) -> str:
        """Find a <TH> or <TD> containing label_text, return next sibling <TD>."""
        # Search all th tags
        for th in soup.find_all(["th", "td"]):
            if label_text.lower() in _clean(th.get_text()).lower():
                sibling = th.find_next_sibling("td")
                if sibling:
                    return _clean(sibling.get_text())
        return ""

    # ── USDOT Number ─────────────────────────────────────────────────────────
    usdot = ""
    usdot_th = soup.find("a", href=lambda h: h and "USDOTID" in h)
    if usdot_th:
        td = usdot_th.find_parent("th")
        if td:
            td = td.find_next_sibling("td")
            if td:
                usdot = _clean(td.get_text())

    # Fallback: look for pattern in text "USDOT Number: XXXXXXX"
    if not usdot:
        match = re.search(r"USDOT Number[:\s]+(\d+)", page_text)
        if match:
            usdot = match.group(1)

    # ── Entity Type ───────────────────────────────────────────────────────────
    entity_type = get_field("Entity Type")

    # ── Operating Status ──────────────────────────────────────────────────────
    # Look for USDOT Status field
    status = ""
    for th in soup.find_all("th"):
        th_text = _clean(th.get_text())
        if "USDOT Status" in th_text:
            td = th.find_next_sibling("td")
            if td:
                raw = _clean(td.get_text())
                # Pick just first token (ACTIVE / INACTIVE / OUT-OF-SERVICE)
                status = raw.split()[0] if raw else ""
                break

    # ── Legal Name ────────────────────────────────────────────────────────────
    carrier_name = ""
    # It appears in the page title like "Company Snapshot CARRIER NAME"
    title_tag = soup.find("title")
    if title_tag:
        title_text = _clean(title_tag.get_text())
        # "SAFER Web - Company Snapshot DAN MCPHERSON"
        parts = title_text.replace("SAFER Web - Company Snapshot", "").strip()
        if parts:
            carrier_name = parts

    # Also try the Legal Name field
    if not carrier_name:
        carrier_name = get_field("Legal Name")

    # ── Phone ─────────────────────────────────────────────────────────────────
    phone = get_field("Phone")

    # ── Physical Address → City, State ───────────────────────────────────────
    location = ""
    addr_td = soup.find("td", id="physicaladdressvalue")
    if addr_td:
        # Address usually: "2866 CHURCH ST<br>GEORGETOWN, CA  95634"
        addr_text = _clean(addr_td.get_text())
        # Try to extract city, state from last line
        # Pattern: "CITY, ST  ZIP" or "CITY, ST ZIP"
        match = re.search(r"([A-Z\s]+),\s+([A-Z]{2})\s+\d{5}", addr_text)
        if match:
            location = f"{match.group(1).strip()}, {match.group(2)}"
        else:
            # Just take the second line
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
    """
    Step 2: Fetch email from SMS Carrier Registration Details page.
    URL: https://ai.fmcsa.dot.gov/SMS/Carrier/{DOT}/CarrierRegistration.aspx
    Returns email string or empty string if not found.
    """
    if not dot_number:
        return ""

    url = SMS_REG_URL.format(dot=dot_number)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(resp.text, "lxml")

    # Look for an email label in the table
    for th in soup.find_all(["th", "td", "label", "span"]):
        text = _clean(th.get_text())
        if text.lower() in ("email", "e-mail", "email address"):
            # Check next sibling or parent row's next cell
            sibling = th.find_next_sibling("td")
            if sibling:
                email_text = _clean(sibling.get_text())
                if "@" in email_text:
                    return email_text

    # Fallback: regex scan entire page for email patterns
    email_match = re.search(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", resp.text
    )
    if email_match:
        return email_match.group(0)

    return ""


def scrape_mc(mc_number: int) -> dict:
    """
    Full two-step scrape for one MC number.
    Returns a dict ready for DataFrame insertion.
    """
    result = {
        "MC Number": f"MC-{mc_number:07d}",
        "Carrier Name": "—",
        "Entity Type": "—",
        "Operating Status": "NOT FOUND",
        "Phone Number": "—",
        "Email Address": "—",
        "Location": "—",
        "_found": False,
    }

    # Step 1: SAFER snapshot
    data = fetch_safer_snapshot(mc_number)
    if data is None:
        return result

    entity_type = data.get("entity_type", "")
    result["MC Number"] = format_mc_number(mc_number, entity_type)
    result["Carrier Name"] = data.get("carrier_name", "—") or "—"
    result["Entity Type"] = entity_type or "—"
    result["Operating Status"] = data.get("status", "—") or "—"
    result["Phone Number"] = data.get("phone", "—") or "—"
    result["Location"] = data.get("location", "—") or "—"
    result["_found"] = True

    time.sleep(REQUEST_DELAY)

    # Step 2: SMS Carrier Registration email
    dot = data.get("usdot", "")
    if dot:
        email = fetch_carrier_email(dot)
        result["Email Address"] = email if email else "—"
        time.sleep(REQUEST_DELAY)

    return result
