import os
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# CONFIGURATION FOR GITHUB DISPATCH TRIGGER
# Replace these values with your actual GitHub username and Personal Access Token
# ---------------------------------------------------------------------------
GITHUB_USER = "YOUR_GITHUB_USERNAME_HERE"
GITHUB_REPO = "market-rates-dashboard"
GITHUB_PAT = "YOUR_FINE_GRAINED_PAT_TOKEN_HERE"

# ---------------------------------------------------------------------------
# DATA SCRAPING FUNCTIONS
# ---------------------------------------------------------------------------


def fetch_ccil_rates():
    """Scrapes MIBOR, MIOIS, and TREPS rates from CCIL using Playwright."""
    data = {"mibor": [], "miois": [], "treps": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Fetch MIBOR
        try:
            page.goto("https://www.ccilindia.com/web/ccil/mibor", timeout=30000)
            page.wait_for_selector("table", timeout=10000)
            soup = BeautifulSoup(page.content(), "html.parser")
            for row in soup.select("table tr"):
                cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(cols) >= 2 and any(
                    term in cols[0] for term in ["Overnight", "14-Day", "1-Month"]
                ):
                    data["mibor"].append(
                        {"tenor": cols[0], "rate": cols[1], "change": cols[-1]}
                    )
        except Exception as e:
            print(f"Error fetching MIBOR: {e}")

        # Fetch MIOIS
        try:
            page.goto("https://www.ccilindia.com/web/ccil/miois", timeout=30000)
            page.wait_for_selector("table", timeout=10000)
            soup = BeautifulSoup(page.content(), "html.parser")
            for row in soup.select("table tr"):
                cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(cols) >= 2 and any(
                    term in cols[0]
                    for term in ["1-Month", "3-Month", "6-Month", "1-Year"]
                ):
                    data["miois"].append({"tenor": cols[0], "rate": cols[1]})
        except Exception as e:
            print(f"Error fetching MIOIS: {e}")

        # Fetch TREPS
        try:
            page.goto("https://www.ccilindia.com/web/ccil/treps", timeout=30000)
            page.wait_for_selector("table", timeout=10000)
            soup = BeautifulSoup(page.content(), "html.parser")
            for row in soup.select("table tr"):
                cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(cols) >= 2 and "Overnight" in cols[0]:
                    data["treps"].append({"tenor": cols[0], "rate": cols[1]})
        except Exception as e:
            print(f"Error fetching TREPS: {e}")

        browser.close()
    return data


def fetch_us_treasury_yields():
    """Fetches latest US Treasury Yield Curve data from US Treasury XML Feed."""
    yields = []
    current_year = datetime.now().year
    url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={current_year}"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            namespaces = {
                "atom": "http://www.w3.org/2005/Atom",
                "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
                "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
            }
            entries = root.findall("atom:entry", namespaces)
            if entries:
                last_entry = entries[-1]
                properties = last_entry.find(
                    "atom:content/m:properties", namespaces
                )
                date_str = (
                    properties.find("d:NEW_DATE", namespaces).text.split("T")[0]
                    if properties.find("d:NEW_DATE", namespaces) is not None
                    else ""
                )

                tenors = [
                    ("1 Month", "d:BC_1MONTH"),
                    ("3 Month", "d:BC_3MONTH"),
                    ("6 Month", "d:BC_6MONTH"),
                    ("1 Year", "d:BC_1YEAR"),
                    ("2 Year", "d:BC_2YEAR"),
                    ("5 Year", "d:BC_5YEAR"),
                    ("10 Year", "d:BC_10YEAR"),
                    ("30 Year", "d:BC_30YEAR"),
                ]

                for name, tag in tenors:
                    val_elem = properties.find(tag, namespaces)
                    val = (
                        val_elem.text
                        if val_elem is not None and val_elem.text
                        else "N/A"
                    )
                    yields.append(
                        {"tenor": name, "rate": f"{val}%", "date": date_str}
                    )
    except Exception as e:
        print(f"Error fetching US Treasury Yields: {e}")

    return yields


def fetch_sofr_rates():
    """Fetches SOFR rate via New York Fed Public API."""
    sofr_data = []
    try:
        url = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            ref_rate = data.get("refRates", [{}])[0]
            rate = ref_rate.get("percentRate", "N/A")
            date = ref_rate.get("effectiveDate", "N/A")
            sofr_data.append(
                {"tenor": "SOFR (Overnight)", "rate": f"{rate}%", "date": date}
            )
    except Exception as e:
        print(f"Error fetching SOFR: {e}")
    return sofr_data


def fetch_fx_and_commodities():
    """Fetches FX (USD/INR) and Commodity Rates (Gold, Oil)."""
    items = []
    try:
        resp = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD", timeout=10
        )
        if resp.status_code == 200:
            inr = resp.json().get("rates", {}).get("INR", "N/A")
            items.append({"name": "USD / INR", "value": f"₹{inr}"})
    except Exception as e:
        print(f"Error fetching USD/INR: {e}")

    items.append({"name": "Brent Crude Oil", "value": "Refer Exchange Feed"})
    items.append({"name": "Gold (XAU/USD)", "value": "Refer Exchange Feed"})

    return items


# ---------------------------------------------------------------------------
# HTML GENERATOR FUNCTION
# ---------------------------------------------------------------------------


def generate_html_dashboard():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    print("Fetching CCIL Rates...")
    ccil = fetch_ccil_rates()

    print("Fetching US Treasury Yields...")
    ust = fetch_us_treasury_yields()

    print("Fetching SOFR Rates...")
    sofr = fetch_sofr_rates()

    print("Fetching FX & Commodity Rates...")
    fx_comm = fetch_fx_and_commodities()

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global & Domestic Market Rates Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f6f9;
            color: #333;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #e1e4e8;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 24px;
            margin: 0;
            color: #1a252f;
        }}
        .timestamp {{
            font-size: 13px;
            color: #6c757d;
        }}
        .refresh-btn {{
            background-color: #0066cc;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            transition: background-color 0.2s;
        }}
        .refresh-btn:hover {{
            background-color: #0052a3;
        }}
        .refresh-btn:disabled {{
            background-color: #a0c4e8;
            cursor: not-allowed;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            padding: 20px;
            border: 1px solid #e1e4e8;
        }}
        .card h2 {{
            font-size: 18px;
            margin-top: 0;
            border-bottom: 1px solid #eee;
            padding-bottom: 8px;
            color: #2c3e50;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 14px;
        }}
        th, td {{
            text-align: left;
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
        }}
        th {{
            color: #7f8c8d;
            font-weight: 600;
        }}
        td:last-child, th:last-child {{
            text-align: right;
        }}
        .status-msg {{
            font-size: 13px;
            color: #28a745;
            margin-top: 5px;
            display: inline-block;
        }}
    </style>
</head>
<body>

<div class="container">
    <div class="header">
        <div>
            <h1>Global & Domestic Market Rates Dashboard</h1>
            <div class="timestamp">Last Updated: {timestamp}</div>
        </div>
        <div>
            <button id="refreshBtn" class="refresh-btn" onclick="triggerScraper()">🔄 Refresh Live Rates</button>
            <br>
            <span id="statusMsg" class="status-msg"></span>
        </div>
    </div>

    <div class="grid">
        <!-- CCIL MIBOR -->
        <div class="card">
            <h2>India - CCIL MIBOR</h2>
            <table>
                <tr><th>Tenor</th><th>Rate</th></tr>
                {"".join([f"<tr><td>{item['tenor']}</td><td>{item['rate']}</td></tr>" for item in ccil['mibor']]) or "<tr><td colspan='2'>No data available</td></tr>"}
            </table>
        </div>

        <!-- CCIL MIOIS & TREPS -->
        <div class="card">
            <h2>India - MIOIS & TREPS</h2>
            <table>
                <tr><th>Instrument</th><th>Rate</th></tr>
                {"".join([f"<tr><td>MIOIS ({item['tenor']})</td><td>{item['rate']}</td></tr>" for item in ccil['miois']])}
                {"".join([f"<tr><td>TREPS ({item['tenor']})</td><td>{item['rate']}</td></tr>" for item in ccil['treps']])}
            </table>
        </div>

        <!-- US Treasury Yield Curve -->
        <div class="card">
            <h2>US Treasury Yields</h2>
            <table>
                <tr><th>Tenor</th><th>Yield</th></tr>
                {"".join([f"<tr><td>{item['tenor']}</td><td>{item['rate']}</td></tr>" for item in ust]) or "<tr><td colspan='2'>No data available</td></tr>"}
            </table>
        </div>

        <!-- SOFR & Global Rates -->
        <div class="card">
            <h2>US SOFR</h2>
            <table>
                <tr><th>Rate Type</th><th>Value</th></tr>
                {"".join([f"<tr><td>{item['tenor']}</td><td>{item['rate']}</td></tr>" for item in sofr]) or "<tr><td colspan='2'>No data available</td></tr>"}
            </table>
        </div>

        <!-- FX & Commodities -->
        <div class="card">
            <h2>FX & Key Indicators</h2>
            <table>
                <tr><th>Indicator</th><th>Rate</th></tr>
                {"".join([f"<tr><td>{item['name']}</td><td>{item['value']}</td></tr>" for item in fx_comm])}
            </table>
        </div>
    </div>
</div>

<script>
async function triggerScraper() {{
    const btn = document.getElementById('refreshBtn');
    const msg = document.getElementById('statusMsg');
    
    const GITHUB_USER = '{GITHUB_USER}';
    const GITHUB_REPO = '{GITHUB_REPO}';
    const GITHUB_PAT = '{GITHUB_PAT}'; 

    btn.disabled = true;
    msg.style.color = '#0066cc';
    msg.innerText = 'Triggering Python scraper...';

    try {{
        const response = await fetch(`https://api.github.com/repos/${{GITHUB_USER}}/${{GITHUB_REPO}}/dispatches`, {{
            method: 'POST',
            headers: {{
                'Accept': 'application/vnd.github+json',
                'Authorization': `Bearer ${{GITHUB_PAT}}`,
                'Content-Type': 'application/json'
            }},
            body: JSON.stringify({{ event_type: 'run_scraper' }})
        }});

        if (response.ok || response.status === 204) {{
            msg.style.color = '#28a745';
            msg.innerText = 'Scraper started! Reloading dashboard in 90 seconds...';
            setTimeout(() => {{
                window.location.reload();
            }}, 90000); 
        }} else {{
            msg.style.color = '#dc3545';
            msg.innerText = 'Failed to trigger scraper. Check token permissions.';
            btn.disabled = false;
        }}
    }} catch (err) {{
        msg.style.color = '#dc3545';
        msg.innerText = 'Error connecting to API server.';
        btn.disabled = false;
    }}
}}
</script>

</body>
</html>
"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("Dashboard index.html generated successfully!")


if __name__ == "__main__":
    generate_html_dashboard()
