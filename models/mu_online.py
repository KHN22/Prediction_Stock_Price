"""Free public sources adapted to the notebook's existing input schema."""
import io
import json
import math
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from mu_macro import prepare_macro

PRICE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/MU?range=5y&interval=1d"
SEC_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json"
MAP = {
 "mu_income_statement_raw.csv": {
  "totalRevenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
  "grossProfit": ["GrossProfit"], "operatingIncome": ["OperatingIncomeLoss"],
  "netIncome": ["NetIncomeLoss"], "researchAndDevelopment": ["ResearchAndDevelopmentExpense"],
  "operatingExpenses": ["OperatingExpenses"], "incomeBeforeTax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
  "costOfRevenue": ["CostOfRevenue"]},
 "mu_cash_flow_raw.csv": {
  "operatingCashflow": ["NetCashProvidedByUsedInOperatingActivities"],
  "capitalExpenditures": ["PaymentsToAcquirePropertyPlantAndEquipment"],
  "cashflowFromInvestment": ["NetCashProvidedByUsedInInvestingActivities"],
  "cashflowFromFinancing": ["NetCashProvidedByUsedInFinancingActivities"]},
 "mu_balance_sheet_raw.csv": {
  "totalAssets": ["Assets"], "totalCurrentAssets": ["AssetsCurrent"],
  "cashAndCashEquivalentsAtCarryingValue": ["CashAndCashEquivalentsAtCarryingValue"],
  "inventory": ["InventoryNet"], "totalLiabilities": ["Liabilities"],
  "longTermDebt": ["LongTermDebtNoncurrent"], "totalShareholderEquity": ["StockholdersEquity"]},
 "mu_earnings_raw.csv": {"reportedEPS": ["EarningsPerShareDiluted"]},
}

def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Model411 personal research", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)
    except Exception as error:
        source = "Yahoo Finance" if "yahoo" in url else "SEC EDGAR"
        raise ValueError(f"ดึงข้อมูลจาก {source} ไม่สำเร็จ กรุณาลองใหม่ภายหลัง") from error

def prices(payload):
    chart = payload.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise ValueError("Yahoo Finance ไม่ส่งข้อมูลราคา MU")
    result = chart["result"][0]
    if result["meta"].get("symbol") != "MU" or result["meta"].get("currency") != "USD":
        raise ValueError("สัญลักษณ์หรือสกุลเงินราคาจาก Yahoo ไม่ตรงกับ MU")
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    session = result["meta"]["currentTradingPeriod"]["regular"]
    rows = []
    for i, stamp in enumerate(result["timestamp"]):
        # Exclude the currently unfinished daily candle.
        if stamp >= session["start"] and time.time() < session["end"] + 900:
            continue
        values = [quote[key][i] for key in ("open", "high", "low", "close", "volume")] + [adjusted[i]]
        if any(value is None or not math.isfinite(value) for value in values):
            continue
        if min(values[:4]) <= 0 or adjusted[i] <= 0 or values[4] < 0:
            raise ValueError("Yahoo ส่งข้อมูล OHLCV ที่ไม่ถูกต้อง")
        ratio = adjusted[i] / quote["close"][i]
        row = {"date": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()}
        row.update({key: quote[key][i] * ratio for key in ("open", "high", "low", "close")})
        row.update(volume=quote["volume"][i], stock_splits=0, dividends=0)
        rows.append(row)
    frame = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    if len(frame) < 1100:
        raise ValueError("ข้อมูลราคาจาก Yahoo มีประวัติไม่พอสำหรับโมเดล")
    return frame

def facts_for(facts, tags, unit="USD"):
    for tag in tags:
        items = facts.get(tag, {}).get("units", {}).get(unit, [])
        if items:
            yield from items

def quarter_value(items, end, filed, instant=False, eps=False):
    candidates = [item for item in items if item["end"] == end and item["filed"] <= filed]
    if instant:
        candidates = [item for item in candidates if "start" not in item]
    else:
        candidates = [item for item in candidates if "start" in item]
    # Prefer the current filing's values and short-duration quarter observations.
    candidates.sort(key=lambda item: (item["filed"], item.get("start", "")), reverse=True)
    for item in candidates:
        if instant:
            return item["val"]
        days = (pd.Timestamp(end) - pd.Timestamp(item["start"])).days
        if 70 <= days <= 105:
            return item["val"]
        if eps:
            continue
        if 150 <= days <= 380:
            previous = [old for old in items if old.get("start") == item["start"]
                        and old["filed"] <= filed
                        and 70 <= (pd.Timestamp(end) - pd.Timestamp(old["end"])).days <= 105]
            if previous:
                previous.sort(key=lambda old: (old["end"], old["filed"]), reverse=True)
                return item["val"] - previous[0]["val"]
    return None

def statements(payload, as_of):
    if int(payload.get("cik", 0)) != 723125:
        raise ValueError("SEC ส่งข้อมูลบริษัทไม่ตรงกับ MU")
    facts = payload["facts"]["us-gaap"]
    revenue = list(facts_for(facts, MAP["mu_income_statement_raw.csv"]["totalRevenue"]))
    periods = {}
    for item in revenue:
        if item.get("form") not in ("10-Q", "10-K") or "start" not in item:
            continue
        end, filed = item["end"], item["filed"]
        if end >= "2009-01-01" and filed <= as_of and (pd.Timestamp(filed)-pd.Timestamp(end)).days <= 100:
            periods[end] = min(periods.get(end, filed), filed)
    output = {name: [] for name in MAP}
    for end, filed in sorted(periods.items()):
        quarter = {}
        for name, mapping in MAP.items():
            row = {"fiscalDateEnding": end}
            for column, tags in mapping.items():
                value = quarter_value(list(facts_for(facts, tags, "USD/shares" if column == "reportedEPS" else "USD")),
                                      end, filed, "balance_sheet" in name, column == "reportedEPS")
                if value is not None:
                    row[column] = value
            if name == "mu_earnings_raw.csv":
                row["reportedDate"] = (pd.Timestamp(filed) + pd.Timedelta(days=1)).date().isoformat()
            quarter[name] = row
        if all(field in quarter[name] for name, field in [
            ("mu_income_statement_raw.csv", "totalRevenue"),
            ("mu_cash_flow_raw.csv", "operatingCashflow"),
            ("mu_cash_flow_raw.csv", "capitalExpenditures")]):
            for name, row in quarter.items():
                output[name].append(row)
    if len(output["mu_income_statement_raw.csv"]) < 16:
        raise ValueError("SEC ส่งข้อมูลรายไตรมาสไม่ครบเพียงพอ")
    return output

def fetch_inputs(base, macro_tables):
    with ThreadPoolExecutor(max_workers=2) as pool:
        price_job = pool.submit(download, PRICE_URL)
        sec_job = pool.submit(download, SEC_URL)
        price_data = prices(price_job.result())
        macro_job = pool.submit(prepare_macro, macro_tables, price_data.iloc[-1]["date"],
                                str(pd.Timestamp(price_data.iloc[0]["date"]) - pd.DateOffset(years=1)))
        reports = statements(sec_job.result(), price_data.iloc[-1]["date"])
        macro_csv, macro_series = macro_job.result()
    files = base.copy()
    files["mu_prices.csv"] = price_data.to_csv(index=False)
    files["cleaned_macro_data.csv"] = macro_csv
    for name, rows in reports.items():
        column = "quarterlyEarnings" if "earnings" in name else "quarterlyReports"
        files[name] = pd.DataFrame([{"symbol": "MU", column: repr(rows)}]).to_csv(index=False)
    metadata = {
        "prices": "Yahoo Finance · adjusted daily OHLC",
        "financials": "SEC EDGAR · 10-Q / 10-K",
        "macro": "FRED · CPI / Fed funds / Unemployment / Treasury 10Y / Real GDP",
        "macroSeries": macro_series,
        "quarter": reports["mu_income_statement_raw.csv"][-1]["fiscalDateEnding"],
        "note": "Macro ใช้ค่าที่ FRED เผยแพร่ล่าสุดพร้อม lag ตามโมเดล ประวัติอาจถูกปรับย้อนหลัง · GDP ใช้หลังจบไตรมาสและเลื่อน 1 เดือน · EPS estimate และ surprise อาจขาด",
    }
    return files, metadata
