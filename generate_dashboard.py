import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests

# ---------------------------------------------------------------------------
# CONFIGURATION FOR GITHUB DISPATCH TRIGGER
# ---------------------------------------------------------------------------
GITHUB_USER = "tarunbajaj1107"  # Replace with your GitHub username
GITHUB_REPO = "market-rates-dashboard"
GITHUB_PAT = "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"             # Replace with your PAT

# ---------------------------------------------------------------------------
# DATA SCRAPING FUNCTIONS
# ---------------------------------------------------------------------------

def fetch_ccil_derivatives_playwright():
    """Renders CCIL using Playwright with targeted MMIFOR context detection."""
    rates = {
        'MIOIS 1 Month': 'N/A',
        'MIOIS 3 Month': 'N/A',
        'MIOIS 6 Month': 'N/A',
        'MIOIS 1 Year': 'N/A',
        'MMIFOR 2 Year': 'N/A',
        'MMIFOR 3 Year': 'N/A',
    }
    url = 'https://www.ccilindia.com/interbank-inr-interest-rate-swaps'

    print('=== [DEBUG] Starting CCIL Swaps Scraping Job ===')

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, args=['--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    ' (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                ),
                viewport={'width': 1366, 'height': 768},
            )
            page = context.new_page()

            page.add_init_script(
                'Object.defineProperty(navigator, "webdriver", {get: () =>'
                ' undefined})'
            )

            page.goto(url, wait_until='networkidle', timeout=45000)

            # Handle popup disclaimers if present
            accept_selectors = [
                "button:has-text('Accept')",
                "button:has-text('I Agree')",
                "button:has-text('Proceed')",
                '#btnAccept',
            ]
            for selector in accept_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue

            page.wait_for_selector('table', timeout=20000)
            tables = page.locator('table').all()

            print(f'=== [DEBUG] Total tables found: {len(tables)} ===')

            for t_idx, table in enumerate(tables):
                parent_text = (
                    table.locator('xpath=./ancestor::div[contains(@class, "section")]')
                    .first.inner_text()
                    if table.locator(
                        'xpath=./ancestor::div[contains(@class, "section")]'
                    ).count()
                    > 0
                    else ''
                )
                table_text = table.inner_text()
                full_context_text = (table_text + ' ' + parent_text).upper()

                is_mifor = (
                    'MODIFIED MIFOR' in full_context_text
                    or 'MMIFOR' in full_context_text
                    or 'MMFOR' in full_context_text
                    or t_idx >= 2
                )

                print(
                    f'\n--- [DEBUG] Table #{t_idx+1} | Detected MMIFOR Context:'
                    f' {is_mifor} ---'
                )

                rows = table.locator('tr').all()
                for r_idx, row in enumerate(rows):
                    cells = [
                        c.replace('\xa0', ' ').strip()
                        for c in row.locator('td, th').all_text_contents()
                        if c.strip()
                    ]

                    if len(cells) < 2:
                        continue

                    raw_tenor = cells[0].upper()
                    clean_tenor = re.sub(r'\s+', '', raw_tenor)

                    valid_rates = []
                    for cell in cells[1:]:
                        match = re.search(r'\d+\.\d+', cell)
                        if match:
                            valid_rates.append(match.group(0))

                    if any(t in clean_tenor for t in ['2Y', '2YEAR', '3Y', '3YEAR']):
                        print(
                            f'  👉 [MMIFOR TARGET ROW FOUND] Table #{t_idx+1} Row #{r_idx+1}:'
                        )
                        print(f'     Raw Cells: {cells}')
                        print(f'     Clean Tenor: "{clean_tenor}"')
                        print(f'     Detected Rates: {valid_rates}')
                        print(f'     Is MIFOR Context Flag: {is_mifor}')

                    if not valid_rates:
                        continue

                    try:
                        formatted_rate = f'{float(valid_rates[0]):.2f}%'
                    except ValueError:
                        continue

                    mapped = False
                    if not is_mifor:
                        if clean_tenor in ['1M', 'ON', 'O/N', 'OVERNIGHT']:
                            rates['MIOIS 1 Month'] = formatted_rate
                            mapped = True
                        elif clean_tenor in ['3M', '3MONTH']:
                            rates['MIOIS 3 Month'] = formatted_rate
                            mapped = True
                        elif clean_tenor in ['6M', '6MONTH']:
                            rates['MIOIS 6 Month'] = formatted_rate
                            mapped = True
                        elif clean_tenor in ['1Y', '12M', '1YEAR']:
                            rates['MIOIS 1 Year'] = formatted_rate
                            mapped = True
                    else:
                        if clean_tenor in ['2Y', '2YEAR']:
                            rates['MMIFOR 2 Year'] = formatted_rate
                            mapped = True
                            print(
                                f'  ✅ [SUCCESS] Successfully mapped MMIFOR 2 Year ->'
                                f' {formatted_rate}'
                            )
                        elif clean_tenor in ['3Y', '3YEAR']:
                            rates['MMIFOR 3 Year'] = formatted_rate
                            mapped = True
                            print(
                                f'  ✅ [SUCCESS] Successfully mapped MMIFOR 3 Year ->'
                                f' {formatted_rate}'
                            )

                    if (
                        any(t in clean_tenor for t in ['2Y', '2YEAR', '3Y', '3YEAR'])
                        and not mapped
                    ):
                        print(
                            f'  ❌ [MAPPING FAILED] Found target tenor ({clean_tenor}), but'
                            f' mapped=False. (is_mifor={is_mifor})'
                        )

            browser.close()
    except Exception as e:
        print(f'!!! [DEBUG EXCEPTION] CCIL Swaps failed: {e} !!!')

    return rates


def fetch_ccil_tenorwise_yields():
    """Scrapes 3M, 6M T-Bills and 2Y, 5Y, 10Y Indicative Yields from CCIL."""
    yields = {
        'INR 3M T-Bill': 'N/A',
        'INR 6M T-Bill': 'N/A',
        'INR 2Y G-Sec': 'N/A',
        'INR 5Y G-Sec': 'N/A',
        'INR 10Y G-Sec': 'N/A',
    }
    url = 'https://www.ccilindia.com/tenorwise-indicative-yields'

    print('=== [DEBUG] Starting CCIL Tenorwise Yields Scraping Job ===')

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, args=['--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    ' (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                ),
                viewport={'width': 1366, 'height': 768},
            )
            page = context.new_page()
            page.add_init_script(
                'Object.defineProperty(navigator, "webdriver", {get: () =>'
                ' undefined})'
            )

            page.goto(url, wait_until='networkidle', timeout=45000)

            # Handle popup disclaimers if present
            accept_selectors = [
                "button:has-text('Accept')",
                "button:has-text('I Agree')",
                "button:has-text('Proceed')",
                '#btnAccept',
            ]
            for selector in accept_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue

            page.wait_for_selector('table', timeout=20000)
            rows = page.locator('table tr').all()

            for row in rows:
                cells = [
                    c.strip()
                    for c in row.locator('td, th').all_text_contents()
                    if c.strip()
                ]
                if len(cells) < 3:
                    continue

                tenor_bucket = cells[1].upper() if len(cells) > 1 else ''
                security_name = cells[2].upper() if len(cells) > 2 else ''
                ytm_cell = cells[-1]

                match = re.search(r'\d+\.\d+', ytm_cell)
                if not match:
                    continue

                formatted_rate = f'{float(match.group(0)):.2f}%'

                if '91D' in tenor_bucket or '91 DTB' in security_name:
                    yields['INR 3M T-Bill'] = formatted_rate
                elif '182D' in tenor_bucket or '182 DTB' in security_name:
                    yields['INR 6M T-Bill'] = formatted_rate
                elif '1Y-2Y' in tenor_bucket:
                    yields['INR 2Y G-Sec'] = formatted_rate
                elif '4Y-5Y' in tenor_bucket:
                    yields['INR 5Y G-Sec'] = formatted_rate
                elif '9Y-10Y' in tenor_bucket:
                    yields['INR 10Y G-Sec'] = formatted_rate

            browser.close()
    except Exception as e:
        print(f'!!! [DEBUG EXCEPTION] CCIL Tenorwise Yields failed: {e} !!!')

    return yields


def fetch_sofr():
    """Fetches official SOFR directly from NY Fed API."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = 'https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json'
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            rate = res.json()['refRates'][0]['percentRate']
            return f'{float(rate):.2f}%'
    except Exception:
        pass
    return 'N/A'


def fetch_us_treasuries():
    """Fetches official Daily US Treasury Yields via US Treasury API."""
    yields = {}
    current_year = datetime.now().year
    url = f'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={current_year}'
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'm': (
                    'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata'
                ),
                'd': 'http://schemas.microsoft.com/ado/2007/08/dataservices',
            }
            entries = root.findall('atom:entry', ns)
            if entries:
                properties = entries[-1].find('.//m:properties', ns)
                mapping = {
                    'US T-Bill 3M': 'd:BC_3MONTH',
                    'US T-Bill 6M': 'd:BC_6MONTH',
                    'US T-Bill 1Y': 'd:BC_1YEAR',
                    'US 2Y Bond Yield': 'd:BC_2YEAR',
                    'US 5Y Bond Yield': 'd:BC_5YEAR',
                    'US 10Y Bond Yield': 'd:BC_10YEAR',
                }
                for label, tag in mapping.items():
                    elem = properties.find(tag, ns)
                    yields[label] = (
                        f'{float(elem.text):.2f}%'
                        if (elem is not None and elem.text)
                        else 'N/A'
                    )
    except Exception:
        pass

    return yields


def fetch_market_commodities_fx():
    """Fetches real-time USD/INR FX Rate, Brent Crude, and Gold Rates."""
    data = {
        'USD / INR Spot': 'N/A',
        'Crude Oil (Brent)': 'N/A',
        'Gold Rate (24K / 10g)': 'N/A',
    }
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        fx_res = requests.get(
            'https://api.exchangerate-api.com/v4/latest/USD',
            headers=headers,
            timeout=8,
        )
        if fx_res.status_code == 200:
            inr_val = fx_res.json()['rates'].get('INR')
            if inr_val:
                data['USD / INR Spot'] = f'₹{float(inr_val):.2f}'
    except Exception:
        pass

    try:
        crude_res = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/BZ=F',
            headers=headers,
            timeout=8,
        )
        if crude_res.status_code == 200:
            crude_val = crude_res.json()['chart']['result'][0]['meta'][
                'regularMarketPrice'
            ]
            data['Crude Oil (Brent)'] = f'${float(crude_val):.2f} / bbl'
    except Exception:
        pass

    try:
        gold_res = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/GC=F',
            headers=headers,
            timeout=8,
        )
        if gold_res.status_code == 200 and data['USD / INR Spot'] != 'N/A':
            gold_oz_usd = gold_res.json()['chart']['result'][0]['meta'][
                'regularMarketPrice'
            ]
            usd_inr = float(data['USD / INR Spot'].replace('₹', ''))
            gold_inr_10g = (float(gold_oz_usd) / 31.1034768) * 10 * usd_inr
            data['Gold Rate (24K / 10g)'] = f'₹{int(gold_inr_10g):,}'
    except Exception:
        pass

    return data

# ---------------------------------------------------------------------------
# HTML GENERATOR FUNCTION WITH ADVANCED PAT LOGGING
# ---------------------------------------------------------------------------

def generate_html_dashboard():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    print("Fetching live market rates via provided script functions...")
    ccil_rates = fetch_ccil_derivatives_playwright()
    ccil_yields = fetch_ccil_tenorwise_yields()
    sofr = fetch_sofr()
    treasuries = fetch_us_treasuries()
    macro_data = fetch_market_commodities_fx()

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
            display: block;
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
        <div style="text-align: right;">
            <button id="refreshBtn" class="refresh-btn" onclick="triggerScraper()">🔄 Refresh Live Rates</button>
            <span id="statusMsg" class="status-msg"></span>
        </div>
    </div>

    <div class="grid">
        <!-- INR Benchmarks & Swaps (CCIL) -->
        <div class="card">
            <h2>🇮🇳 INR Benchmarks & Swaps (CCIL)</h2>
            <table>
                <tr><th>Instrument</th><th>Rate</th></tr>
                {"".join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in ccil_rates.items()])}
            </table>
        </div>

        <!-- INR Government Securities & T-Bills (CCIL) -->
        <div class="card">
            <h2>🇮🇳 INR Government Securities & T-Bills</h2>
            <table>
                <tr><th>Tenor / Security</th><th>Yield</th></tr>
                {"".join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in ccil_yields.items()])}
            </table>
        </div>

        <!-- US Benchmarks & Yields -->
        <div class="card">
            <h2>🇺🇸 US Benchmarks & Yields</h2>
            <table>
                <tr><th>Tenor</th><th>Yield</th></tr>
                <tr><td>SOFR Rate</td><td>{sofr}</td></tr>
                {"".join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in treasuries.items()])}
            </table>
        </div>

        <!-- FX & Global Commodities -->
        <div class="card">
            <h2>🌐 FX & Global Commodities</h2>
            <table>
                <tr><th>Indicator</th><th>Rate</th></tr>
                {"".join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in macro_data.items()])}
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

    console.log('=== [GITHUB API DEBUG LOGS] ===');
    console.log(`Target Repo: ${{GITHUB_USER}}/${{GITHUB_REPO}}`);
    console.log(`PAT Length: ${{GITHUB_PAT ? GITHUB_PAT.length : 0}} chars`);
    console.log(`PAT Prefix: ${{GITHUB_PAT ? GITHUB_PAT.substring(0, 10) + '...' : 'NONE'}}`);

    btn.disabled = true;
    msg.style.color = '#0066cc';
    msg.innerText = 'Triggering Python scraper...';

    if (!GITHUB_PAT || GITHUB_PAT.includes('YOUR_') || GITHUB_PAT.length < 20) {{
        console.error('[PAT LOG ERROR] GITHUB_PAT appears invalid, placeholder, or truncated.');
        msg.style.color = '#dc3545';
        msg.innerText = 'Error: Invalid PAT configured in script.';
        btn.disabled = false;
        return;
    }}

    const targetUrl = `https://api.github.com/repos/${{GITHUB_USER}}/${{GITHUB_REPO}}/dispatches`;

    try {{
        const response = await fetch(targetUrl, {{
            method: 'POST',
            headers: {{
                'Accept': 'application/vnd.github+json',
                'Authorization': `Bearer ${{GITHUB_PAT}}`,
                'Content-Type': 'application/json'
            }},
            body: JSON.stringify({{ event_type: 'run_scraper' }})
        }});

        console.log(`Response Status: ${{response.status}} ${{response.statusText}}`);

        let responseBody = {{}};
        try {{
            responseBody = await response.json();
            console.log('Response Details:', responseBody);
        }} catch(e) {{
            console.log('No JSON response body returned (Normal for HTTP 204).');
        }}

        if (response.ok || response.status === 204) {{
            console.log('✅ Dispatch event created successfully!');
            msg.style.color = '#28a745';
            msg.innerText = 'Scraper started! Reloading dashboard in 90 seconds...';
            setTimeout(() => {{
                window.location.reload();
            }}, 90000); 
        }} else {{
            const errorReason = responseBody.message || 'Check browser console for full headers.';
            console.error(`❌ GitHub API Error [HTTP ${{response.status}}] - ${{errorReason}}`);
            
            if (response.status === 401) {{
                console.error('💡 Hint: 401 Unauthorized means the token is invalid, expired, or auto-revoked by GitHub because it was committed in a public repository.');
            }} else if (response.status === 403) {{
                console.error('💡 Hint: 403 Forbidden means the PAT lacks required permissions. Ensure "Contents" or "Actions" write permissions are granted.');
            }} else if (response.status === 404) {{
                console.error('💡 Hint: 404 Not Found means either the owner/repo string is incorrect OR the fine-grained PAT does not have explicit access selected for this repo.');
            }}

            msg.style.color = '#dc3545';
            msg.innerText = `Error (${{response.status}}): ${{errorReason}}`;
            btn.disabled = false;
        }}
    }} catch (err) {{
        console.error('❌ Network or Fetch Error:', err);
        msg.style.color = '#dc3545';
        msg.innerText = 'Network error connecting to GitHub API.';
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
