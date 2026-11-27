"""Free public sources for the AMZN V4 model: Yahoo Finance prices + VIX + earnings dates."""

import io
import json
import math
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

# Yahoo downsamples `range=max` to monthly bars; period1/period2 keeps daily data.
_START = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp())


def chart_url(symbol):
    end = int(time.time())
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={_START}&period2={end}&interval=1d"


PRICE_URL = chart_url("AMZN")
VIX_URL = chart_url("%5EVIX")
EARNINGS_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/AMZN?modules=calendarEvents"
NY = ZoneInfo("America/New_York")


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Model411 personal research", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)
    except Exception as error:
        raise ValueError("ดึงข้อมูลจาก Yahoo Finance ไม่สำเร็จ กรุณาลองใหม่ภายหลัง") from error


def chart_rows(payload, symbol):
    chart = payload.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"Yahoo Finance ไม่ส่งข้อมูลราคา {symbol}")
    result = chart["result"][0]
    if result["meta"].get("symbol") != symbol:
        raise ValueError(f"สัญลักษณ์ราคาจาก Yahoo ไม่ตรงกับ {symbol}")
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
        row.update(volume=quote["volume"][i])
        rows.append(row)
    frame = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    if len(frame) < 1500:
        raise ValueError("ข้อมูลราคาจาก Yahoo มีประวัติไม่พอสำหรับโมเดล")
    return frame


def vix_series(payload, index):
    chart = payload.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise ValueError("Yahoo Finance ไม่ส่งข้อมูล ^VIX")
    result = chart["result"][0]
    quote = result["indicators"]["quote"][0]
    stamps = [datetime.fromtimestamp(s, timezone.utc).date().isoformat() for s in result["timestamp"]]
    frame = pd.DataFrame({"date": stamps, "^VIX": quote["close"]}).dropna()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date")["^VIX"].sort_index()
    # Align to AMZN trading days; carry the last VIX close over non-trading gaps.
    aligned = frame.reindex(pd.DatetimeIndex(index)).ffill()
    return pd.DataFrame({"Date": index.strftime("%Y-%m-%d"), "^VIX": aligned.values})


def earnings_frame(base_csv, last_date):
    frame = pd.read_csv(io.StringIO(base_csv))
    stamps = pd.to_datetime(frame["Earnings Date"], utc=True, errors="coerce")
    frame["_norm"] = stamps.dt.tz_convert(NY).dt.tz_localize(None).dt.normalize()
    frame = frame.dropna(subset=["_norm"]).sort_values("_norm")

    # Next scheduled earnings from Yahoo quoteSummary when available.
    try:
        payload = download(EARNINGS_URL)
        events = payload["quoteSummary"]["result"][0].get("calendarEvents", {}).get("earnings", {})
        for item in events.get("earningsTimestamp", []):
            stamp = datetime.fromtimestamp(item["raw"], tz=timezone.utc).astimezone(NY)
            norm = stamp.normalize()
            if norm not in set(frame["_norm"]):
                frame = pd.concat([frame, pd.DataFrame({
                    "Earnings Date": [stamp.strftime("%Y-%m-%d %H:%M:%S%z")],
                    "EPS Estimate": [pd.NA], "Reported EPS": [pd.NA], "Surprise(%)": [pd.NA],
                    "_norm": [norm],
                })], ignore_index=True)
    except Exception:
        pass

    # Top up with quarterly estimates so long-horizon windows keep an earnings date.
    frame = frame.sort_values("_norm")
    last_known = frame["_norm"].max()
    horizon_end = last_date + pd.Timedelta(days=400)
    cursor = last_known
    existing = set(frame["_norm"])
    while cursor < horizon_end:
        cursor = cursor + pd.Timedelta(days=91)
        if cursor in existing or cursor <= last_known:
            continue
        stamp = datetime(cursor.year, cursor.month, cursor.day, 16, 0, tzinfo=NY)
        frame = pd.concat([frame, pd.DataFrame({
            "Earnings Date": [stamp.strftime("%Y-%m-%d %H:%M:%S%z")],
            "EPS Estimate": [pd.NA], "Reported EPS": [pd.NA], "Surprise(%)": [pd.NA],
            "_norm": [cursor],
        })], ignore_index=True)
        existing.add(cursor)

    out = frame.drop(columns=["_norm"]).sort_values("Earnings Date")
    return out.to_csv(index=False)


def fetch_inputs(base, macro_tables=None):
    price_frame = chart_rows(download(PRICE_URL), "AMZN")
    vix_frame = vix_series(download(VIX_URL), pd.DatetimeIndex(price_frame["date"]))
    earnings_csv = earnings_frame(base["amzn_earnings.csv"], pd.Timestamp(price_frame["date"].iloc[-1]))
    earnings_norm = pd.to_datetime(
        pd.read_csv(io.StringIO(earnings_csv))["Earnings Date"], utc=True, errors="coerce"
    ).dt.tz_convert(NY).dt.tz_localize(None).dt.normalize().dropna()
    last_earnings = earnings_norm[earnings_norm <= pd.Timestamp(price_frame["date"].iloc[-1])].max()

    files = dict(base)
    files["amzn_prices.csv"] = price_frame.rename(columns={
        "date": "Date", "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"}).to_csv(index=False)
    files["amzn_market.csv"] = vix_frame.to_csv(index=False)
    files["amzn_earnings.csv"] = earnings_csv
    sources = {
        "prices": "Yahoo Finance · adjusted daily OHLC",
        "financials": "Yahoo Finance · earnings calendar",
        "macroSeries": [],
        "quarter": last_earnings.date().isoformat() if pd.notna(last_earnings) else None,
        "note": "AMZN V4 · ราคาและ VIX จาก Yahoo Finance · วันงบใช้ปฏิทินจริงบวกประมาณการรายไตรมาส · ช่วงราคาไม่ใช่คำแนะนำการลงทุน",
    }
    return files, sources
