import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests

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

                    if not valid_rates:
                        continue

                    try:
                        formatted_rate = f'{float(valid_rates[0]):.2f}%'
                    except ValueError:
                        continue

                    if not is_mifor:
                        if clean_tenor in ['1M', 'ON', 'O/N', 'OVERNIGHT']:
                            rates['MIOIS 1 Month'] = formatted_rate
                        elif clean_tenor in ['3M', '3MONTH']:
                            rates['MIOIS 3 Month'] = formatted_rate
                        elif clean_tenor in ['6M', '6MONTH']:
                            rates['MIOIS 6 Month'] = formatted_rate
                        elif clean_tenor in ['1Y', '12M', '1YEAR']:
                            rates['MIOIS 1 Year'] = formatted_rate
                    else:
                        if clean_tenor in ['2Y', '2YEAR']:
                            rates['MMIFOR 2 Year'] = formatted_rate
                        elif clean_tenor in ['3Y', '3YEAR']:
                            rates['MMIFOR 3 Year'] = formatted_rate

            browser.close()
    except Exception as e:
        print(f'!!! CCIL Swaps failed: {e} !!!')

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
        print(f'!!! CCIL Tenorwise Yields failed: {e} !!!')

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


def parse_num(v):
    """Safe helper to parse numerical float from string rate."""
    if not v or v == 'N/A':
        return None
    clean = re.sub(r'[^0-9.]', '', str(v))
    return float(clean) if clean else None


# ---------------------------------------------------------------------------
# HTML GENERATOR FUNCTION WITH EXECUTIVE DASHBOARD STYLING
# ---------------------------------------------------------------------------

def generate_html_dashboard():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    print("Fetching live market rates...")
    ccil_rates = fetch_ccil_derivatives_playwright()
    ccil_yields = fetch_ccil_tenorwise_yields()
    sofr = fetch_sofr()
    treasuries = fetch_us_treasuries()
    macro_data = fetch_market_commodities_fx()

    # Align Data into Tenor Arrays [3M, 6M, 2Y, 5Y, 10Y]
    us_data = [
        parse_num(treasuries.get('US T-Bill 3M')) or 5.20,
        parse_num(treasuries.get('US T-Bill 6M')) or 5.10,
        parse_num(treasuries.get('US 2Y Bond Yield')) or 4.35,
        parse_num(treasuries.get('US 5Y Bond Yield')) or 4.15,
        parse_num(treasuries.get('US 10Y Bond Yield')) or 4.28,
    ]

    in_data = [
        parse_num(ccil_yields.get('INR 3M T-Bill')) or 6.88,
        parse_num(ccil_yields.get('INR 6M T-Bill')) or 6.95,
        parse_num(ccil_yields.get('INR 2Y G-Sec')) or 7.05,
        parse_num(ccil_yields.get('INR 5Y G-Sec')) or 7.12,
        parse_num(ccil_yields.get('INR 10Y G-Sec')) or 7.18,
    ]

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sovereign Yields  -  Dashboard</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        slate: {{ 850: '#0f172a', 900: '#0b0f19', 950: '#05070e' }},
                        amber: {{ 400: '#fbbf24', 500: '#f59e0b' }},
                        cyan: {{ 400: '#22d3ee', 500: '#06b6d4' }},
                        emerald: {{ 400: '#34d399', 500: '#10b981' }}
                    }},
                    fontFamily: {{ sans: ['Inter', 'sans-serif'] }}
                }}
            }}
        }}
    </script>
    <!-- Chart.js and Font Awesome CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            background: radial-gradient(circle at 50% 0%, #1e293b 0%, #0b0f19 75%);
            color: #f8fafc;
            min-height: 100vh;
        }}
        .glass-card {{
            background: rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }}
        .glass-card:hover {{
            border-color: rgba(255, 255, 255, 0.15);
        }}
        .glow-cyan {{ box-shadow: 0 0 20px rgba(34, 211, 238, 0.15); }}
        @keyframes pulse-ring {{
            0% {{ transform: scale(0.95); opacity: 0.8; }}
            50% {{ transform: scale(1.2); opacity: 0.3; }}
            100% {{ transform: scale(0.95); opacity: 0.8; }}
        }}
        .pulse-dot {{ animation: pulse-ring 2s infinite ease-in-out; }}
    </style>
</head>
<body class="p-4 md:p-6 lg:p-8 text-slate-100">

    <!-- Header -->
    <header class="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4 border-b border-slate-800/80 pb-5">
        <div class="flex items-center space-x-4">
            <div class="p-3 bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 rounded-xl border border-cyan-500/30 text-cyan-400 glow-cyan">
                <i class="fa-solid fa-chart-line text-2xl"></i>
            </div>
            <div>
                <h1 class="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
                    Sovereign Yields 
                </h1>
                <p class="text-xs text-slate-400 font-medium"> Interest Rate & Spreads Dashboard</p>
            </div>
        </div>

        <div class="flex flex-wrap items-center gap-3">
            <div class="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs">
                <span class="relative flex h-2.5 w-2.5">
                    <span class="pulse-dot absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                </span>
                <span class="text-slate-300 font-medium">Live Synced</span>
                <span class="text-slate-500 text-[10px]">{timestamp}</span>
            </div>

            <a href="https://github.com/tarunbajaj1107/market-rates-dashboard/actions/workflows/update_dashboard.yml" 
               target="_blank" 
               class="flex items-center space-x-2 px-4 py-1.5 rounded-lg bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-cyan-950/50 transition">
                <i class="fa-solid fa-rotate-right"></i>
                <span>Trigger Scraper Job</span>
            </a>
        </div>
    </header>

    <!-- KPI Highlight Cards Grid -->
    <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <!-- US 10Y Benchmark -->
        <div class="glass-card rounded-2xl p-4 flex flex-col justify-between relative overflow-hidden">
            <div class="flex justify-between items-start mb-2">
                <span class="text-xs font-semibold tracking-wider text-slate-400 uppercase">US 10Y Treasury</span>
                <span class="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-mono">USD</span>
            </div>
            <div class="flex items-baseline justify-between my-1">
                <span class="text-2xl font-extrabold font-mono tracking-tight text-white">{us_data[4]:.2f}%</span>
                <span class="text-xs font-semibold text-cyan-400">SOFR: {sofr}</span>
            </div>
            <div class="text-[11px] text-slate-400 flex justify-between pt-2 border-t border-slate-800/60 mt-1">
                <span>US 2Y: <strong class="text-slate-200">{us_data[2]:.2f}%</strong></span>
                <span>US 2Y/10Y Spread: <strong class="text-cyan-400">{int((us_data[4] - us_data[2])*100)} bps</strong></span>
            </div>
        </div>

        <!-- India 10Y Sovereign -->
        <div class="glass-card rounded-2xl p-4 flex flex-col justify-between relative overflow-hidden">
            <div class="flex justify-between items-start mb-2">
                <span class="text-xs font-semibold tracking-wider text-slate-400 uppercase">India 10Y G-Sec</span>
                <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono">INR</span>
            </div>
            <div class="flex items-baseline justify-between my-1">
                <span class="text-2xl font-extrabold font-mono tracking-tight text-white">{in_data[4]:.2f}%</span>
                <span class="text-xs font-semibold text-amber-400">USD/INR: {macro_data.get('USD / INR Spot')}</span>
            </div>
            <div class="text-[11px] text-slate-400 flex justify-between pt-2 border-t border-slate-800/60 mt-1">
                <span>India 2Y: <strong class="text-slate-200">{in_data[2]:.2f}%</strong></span>
                <span>IN 2Y/10Y Spread: <strong class="text-amber-400">{int((in_data[4] - in_data[2])*100)} bps</strong></span>
            </div>
        </div>

        <!-- US - India Yield Differential -->
        <div class="glass-card rounded-2xl p-4 flex flex-col justify-between relative overflow-hidden">
            <div class="flex justify-between items-start mb-2">
                <span class="text-xs font-semibold tracking-wider text-slate-400 uppercase">10Y Spread (IN - US)</span>
                <i class="fa-solid fa-arrows-left-right-to-line text-xs text-indigo-400"></i>
            </div>
            <div class="flex items-baseline justify-between my-1">
                <span class="text-2xl font-extrabold font-mono tracking-tight text-indigo-300">{int((in_data[4] - us_data[4])*100)} bps</span>
                <span class="text-[10px] text-slate-400">Carry Yield</span>
            </div>
            <p class="text-[11px] text-slate-400 pt-2 border-t border-slate-800/60 mt-1 truncate">
                Real Spread Buffer: <span class="text-emerald-400 font-semibold">Healthy</span>
            </p>
        </div>

        <!-- Macro Indicators -->
        <div class="glass-card rounded-2xl p-4 flex flex-col justify-between relative overflow-hidden">
            <div class="flex justify-between items-start mb-2">
                <span class="text-xs font-semibold tracking-wider text-slate-400 uppercase">Global Commodities</span>
                <i class="fa-solid fa-globe text-xs text-emerald-400"></i>
            </div>
            <div class="my-1">
                <span class="text-sm font-bold text-slate-100 block">Brent: {macro_data.get('Crude Oil (Brent)')}</span>
                <span class="text-xs text-slate-300">Gold: {macro_data.get('Gold Rate (24K / 10g)')}</span>
            </div>
            <div class="text-[11px] text-slate-400 flex justify-between pt-2 border-t border-slate-800/60 mt-1">
                <span>Macro Environment:</span>
                <span class="font-semibold text-emerald-400">Stable</span>
            </div>
        </div>
    </section>

    <!-- Visual Analytics Section -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        
        <!-- Large Chart Container -->
        <div class="lg:col-span-2 glass-card rounded-2xl p-5 flex flex-col justify-between relative">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4 pb-3 border-b border-slate-800/80">
                <div>
                    <h2 class="text-lg font-bold text-white flex items-center space-x-2">
                        <span>Multi-Tenor Yield Curve Visualizer</span>
                        <span class="text-xs text-slate-400 font-normal">(Term Structure)</span>
                    </h2>
                </div>
            </div>

            <!-- Canvas Container -->
            <div class="relative w-full h-[360px]">
                <canvas id="yieldCurveChart"></canvas>
            </div>

            <div class="mt-4 pt-3 border-t border-slate-800/80 flex flex-wrap justify-between items-center text-[11px] text-slate-400 gap-2">
                <div class="flex items-center space-x-4">
                    <span class="flex items-center space-x-1.5">
                        <span class="w-3 h-0.5 bg-cyan-400 inline-block"></span>
                        <span class="text-slate-300">US Treasury Yields</span>
                    </span>
                    <span class="flex items-center space-x-1.5">
                        <span class="w-3 h-0.5 bg-amber-400 inline-block"></span>
                        <span class="text-slate-300">India Sovereign G-Sec</span>
                    </span>
                </div>
            </div>
        </div>

        <!-- Right Column: Summary & Spread Chart -->
        <div class="flex flex-col gap-6">
            <div class="glass-card rounded-2xl p-5 flex-1 flex flex-col justify-between border-l-4 border-l-cyan-500">
                <div>
                    <div class="flex items-center justify-between mb-4 pb-2 border-b border-slate-800">
                        <div class="flex items-center space-x-2">
                            <i class="fa-solid fa-brain text-cyan-400 text-sm"></i>
                            <h3 class="text-sm font-bold tracking-wide uppercase text-slate-200">Executive Insights</h3>
                        </div>
                        <span class="text-[10px] px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-semibold uppercase">Automated</span>
                    </div>

                    <div class="space-y-3 text-xs text-slate-300">
                        <div class="flex items-start space-x-2">
                            <i class="fa-solid fa-circle-chevron-right text-cyan-400 mt-0.5 flex-shrink-0"></i>
                            <p><strong>US Treasury Curve:</strong> 10Y Benchmark at <strong>{us_data[4]:.2f}%</strong> with 2Y-10Y spread at <strong>{int((us_data[4] - us_data[2])*100)} bps</strong>.</p>
                        </div>
                        <div class="flex items-start space-x-2">
                            <i class="fa-solid fa-circle-chevron-right text-amber-400 mt-0.5 flex-shrink-0"></i>
                            <p><strong>India G-Sec Structure:</strong> 10Y Benchmark at <strong>{in_data[4]:.2f}%</strong> maintaining an upward slope over front-end T-Bills.</p>
                        </div>
                        <div class="flex items-start space-x-2">
                            <i class="fa-solid fa-circle-chevron-right text-indigo-400 mt-0.5 flex-shrink-0"></i>
                            <p><strong>Differential Cushion:</strong> 10Y Spread sits at <strong>{int((in_data[4] - us_data[4])*100)} bps</strong>, providing adequate carry for FX stability.</p>
                        </div>
                    </div>
                </div>

                <div class="mt-4 p-3 rounded-xl bg-slate-900/90 border border-slate-800/80">
                    <span class="text-[10px] text-slate-400 uppercase tracking-wider font-semibold block mb-1">Recommended Stance</span>
                    <p class="text-xs font-semibold text-emerald-300">Maintain neutral duration positioning across sovereign curves.</p>
                </div>
            </div>

            <div class="glass-card rounded-2xl p-5">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="text-sm font-bold text-slate-200">Spread Visualizer (India - US)</h3>
                    <span class="text-xs text-indigo-400 font-mono">Basis Points</span>
                </div>
                <div class="relative w-full h-[150px]">
                    <canvas id="spreadChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <!-- Data Matrix Table -->
    <section class="glass-card rounded-2xl p-5 mb-8">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-base font-bold text-white">Sovereign Tenor Matrix</h3>
            <span class="text-xs text-slate-400 font-mono">Values in % / bps</span>
        </div>

        <div class="overflow-x-auto">
            <table class="w-full text-left text-xs font-mono">
                <thead>
                    <tr class="border-b border-slate-800 text-slate-400 uppercase text-[11px]">
                        <th class="py-3 px-3">Tenor</th>
                        <th class="py-3 px-3 text-cyan-400">US Yield</th>
                        <th class="py-3 px-3 text-amber-400">India Yield</th>
                        <th class="py-3 px-3 text-indigo-400">Spread (IN - US)</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/60 text-slate-200">
                    <tr><td class="py-2.5 px-3 font-bold">3M T-Bill</td><td class="py-2.5 px-3 text-cyan-400">{us_data[0]:.2f}%</td><td class="py-2.5 px-3 text-amber-400">{in_data[0]:.2f}%</td><td class="py-2.5 px-3 text-indigo-300">{int((in_data[0]-us_data[0])*100)} bps</td></tr>
                    <tr><td class="py-2.5 px-3 font-bold">6M T-Bill</td><td class="py-2.5 px-3 text-cyan-400">{us_data[1]:.2f}%</td><td class="py-2.5 px-3 text-amber-400">{in_data[1]:.2f}%</td><td class="py-2.5 px-3 text-indigo-300">{int((in_data[1]-us_data[1])*100)} bps</td></tr>
                    <tr><td class="py-2.5 px-3 font-bold">2Y Sovereign</td><td class="py-2.5 px-3 text-cyan-400">{us_data[2]:.2f}%</td><td class="py-2.5 px-3 text-amber-400">{in_data[2]:.2f}%</td><td class="py-2.5 px-3 text-indigo-300">{int((in_data[2]-us_data[2])*100)} bps</td></tr>
                    <tr><td class="py-2.5 px-3 font-bold">5Y Sovereign</td><td class="py-2.5 px-3 text-cyan-400">{us_data[3]:.2f}%</td><td class="py-2.5 px-3 text-amber-400">{in_data[3]:.2f}%</td><td class="py-2.5 px-3 text-indigo-300">{int((in_data[3]-us_data[3])*100)} bps</td></tr>
                    <tr><td class="py-2.5 px-3 font-bold">10Y Sovereign</td><td class="py-2.5 px-3 text-cyan-400">{us_data[4]:.2f}%</td><td class="py-2.5 px-3 text-amber-400">{in_data[4]:.2f}%</td><td class="py-2.5 px-3 text-indigo-300">{int((in_data[4]-us_data[4])*100)} bps</td></tr>
                </tbody>
            </table>
        </div>
    </section>

    <!-- Swap Rates Section -->
    <section class="glass-card rounded-2xl p-5">
        <h3 class="text-base font-bold text-white mb-3">INR Derivatives & Swaps (CCIL)</h3>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
            {"".join([f'<div class="bg-slate-900/80 p-3 rounded-xl border border-slate-800"><span class="text-slate-400 block mb-1">{k}</span><span class="text-sm font-bold text-amber-400">{v}</span></div>' for k, v in ccil_rates.items()])}
        </div>
    </section>

    <script>
        const tenors = ['3M', '6M', '2Y', '5Y', '10Y'];
        const usData = {us_data};
        const inData = {in_data};
        const spreadData = usData.map((u, i) => Math.round((inData[i] - u) * 100));

        // Yield Curve Line Chart
        const ctxYield = document.getElementById('yieldCurveChart').getContext('2d');
        new Chart(ctxYield, {{
            type: 'line',
            data: {{
                labels: tenors,
                datasets: [
                    {{
                        label: 'US Treasuries',
                        data: usData,
                        borderColor: '#22d3ee',
                        backgroundColor: 'rgba(34, 211, 238, 0.1)',
                        fill: true,
                        tension: 0.38,
                        borderWidth: 3,
                        pointRadius: 4
                    }},
                    {{
                        label: 'India G-Sec',
                        data: inData,
                        borderColor: '#fbbf24',
                        backgroundColor: 'rgba(251, 191, 36, 0.1)',
                        fill: true,
                        tension: 0.38,
                        borderWidth: 3,
                        pointRadius: 4
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ labels: {{ color: '#94a3b8', font: {{ family: 'Inter', size: 11 }} }} }}
                }},
                scales: {{
                    x: {{ grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#94a3b8' }} }},
                    y: {{ grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#94a3b8', callback: v => v + '%' }} }}
                }}
            }}
        }});

        // Spread Visualizer Bar Chart
        const ctxSpread = document.getElementById('spreadChart').getContext('2d');
        new Chart(ctxSpread, {{
            type: 'bar',
            data: {{
                labels: tenors,
                datasets: [{{
                    label: 'Spread (bps)',
                    data: spreadData,
                    backgroundColor: 'rgba(99, 102, 241, 0.5)',
                    borderColor: '#6366f1',
                    borderWidth: 1,
                    borderRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }},
                    y: {{ grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("Executive Sovereign Dashboard index.html generated successfully!")


if __name__ == "__main__":
    generate_html_dashboard()
