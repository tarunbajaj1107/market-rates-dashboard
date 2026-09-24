from datetime import datetime
import json
import os
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests


def fetch_ccil_derivatives_playwright():
  rates = {
      'MIOIS 1 Month': 'N/A',
      'MIOIS 3 Month': 'N/A',
      'MIOIS 6 Month': 'N/A',
      'MIOIS 1 Year': 'N/A',
      'MMIFOR 2 Year': 'N/A',
      'MMIFOR 3 Year': 'N/A',
  }
  url = 'https://www.ccilindia.com/interbank-inr-interest-rate-swaps'

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

          clean_tenor = re.sub(r'\s+', '', cells[0].upper())
          valid_rates = [
              m.group(0)
              for cell in cells[1:]
              if (m := re.search(r'\d+\.\d+', cell))
          ]

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
    print(f'Error fetching CCIL derivatives: {e}')

  return rates


def fetch_ccil_tenorwise_yields():
  yields = {
      'INR 3M T-Bill': 'N/A',
      'INR 6M T-Bill': 'N/A',
      'INR 2Y G-Sec': 'N/A',
      'INR 5Y G-Sec': 'N/A',
      'INR 10Y G-Sec': 'N/A',
  }
  url = 'https://www.ccilindia.com/tenorwise-indicative-yields'

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
    print(f'Error fetching CCIL yields: {e}')

  return yields


def fetch_sofr():
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


def build_dashboard_html(
    ccil_rates, ccil_yields, sofr, treasuries, macro_data, timestamp_str
):
  def generate_cards(data_dict):
    cards = ''
    for k, v in data_dict.items():
      cards += f"""
            <div class="card">
                <div class="card-label">{k}</div>
                <div class="card-value">{v}</div>
            </div>"""
    return cards

  html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Market Rates Dashboard</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --border: #334155;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            margin: 0;
            padding: 2rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1rem;
        }}
        h1 {{
            margin: 0;
            font-size: 1.8rem;
            color: var(--accent);
        }}
        .timestamp {{
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }}
        section {{
            margin-bottom: 2.5rem;
        }}
        h2 {{
            font-size: 1.2rem;
            color: var(--text-muted);
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 1rem;
        }}
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.2rem;
        }}
        .card-label {{
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-bottom: 0.5rem;
        }}
        .card-value {{
            font-size: 1.4rem;
            font-weight: 600;
            color: var(--text-main);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Global & Local Market Rates Dashboard</h1>
            <div class="timestamp">Last Updated: {timestamp_str} UTC</div>
        </header>

        <section>
            <h2>🇮🇳 INR Benchmarks & Swaps (CCIL)</h2>
            <div class="grid">
                {generate_cards(ccil_rates)}
            </div>
        </section>

        <section>
            <h2>🇮🇳 INR Government Securities & T-Bills</h2>
            <div class="grid">
                {generate_cards(ccil_yields)}
            </div>
        </section>

        <section>
            <h2>🇺🇸 US Benchmarks & Yields</h2>
            <div class="grid">
                {generate_cards({'SOFR Rate': sofr})}
                {generate_cards(treasuries)}
            </div>
        </section>

        <section>
            <h2>🌐 FX & Global Commodities</h2>
            <div class="grid">
                {generate_cards(macro_data)}
            </div>
        </section>
    </div>
</body>
</html>"""
  return html


def main():
  timestamp_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
  print('Fetching market rates...')

  ccil_rates = fetch_ccil_derivatives_playwright()
  ccil_yields = fetch_ccil_tenorwise_yields()
  sofr = fetch_sofr()
  treasuries = fetch_us_treasuries()
  macro_data = fetch_market_commodities_fx()

  html_content = build_dashboard_html(
      ccil_rates, ccil_yields, sofr, treasuries, macro_data, timestamp_str
  )

  with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

  print('Dashboard generated successfully as index.html')


if __name__ == '__main__':
  main()
