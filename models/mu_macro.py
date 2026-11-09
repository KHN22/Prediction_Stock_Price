"""FRED public tables aligned to the notebook's monthly input."""

import re
from html.parser import HTMLParser

import numpy as np
import pandas as pd

SERIES = {
    "consumer_price_index": ("CPIAUCSL", "CPI", "Index 1982–84=100"),
    "fed_funds_rate": ("FEDFUNDS", "Fed funds", "%"),
    "unemployment_rate": ("UNRATE", "Unemployment", "%"),
    "treasury_10y_yield": ("GS10", "Treasury 10Y", "%"),
    "real_gdp": ("GDPC1", "Real GDP", "Billions of chained 2017 USD, SAAR"),
}


class FredTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th"):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        if tag == "tr" and self.row:
            self.rows.append(self.row)


def parse_table(html, series):
    table = FredTable()
    table.feed(html)
    if ["Series ID", series] not in table.rows:
        raise ValueError(f"ตาราง FRED ไม่ตรงกับ {series}")
    observations = [row for row in table.rows
                    if len(row) == 2 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0])]
    if not observations:
        raise ValueError(f"ไม่พบข้อมูลในตาราง FRED {series}")
    frame = pd.DataFrame(observations, columns=["observation_date", series])
    frame[series] = frame[series].replace(".", np.nan)
    return frame


def prepare_macro(payloads, as_of, start):
    cutoff = pd.Timestamp(as_of).normalize()
    index = pd.date_range(pd.Timestamp(start).to_period("M").start_time, cutoff, freq="MS")
    frame = pd.DataFrame(index=index)
    metadata = []
    for column, (series, label, units) in SERIES.items():
        try:
            raw = parse_table(payloads[series], series)
            date_column = "observation_date" if "observation_date" in raw else "DATE"
            dates = pd.to_datetime(raw[date_column], errors="raise")
            values = pd.to_numeric(raw[series], errors="raise")
        except (KeyError, ValueError) as error:
            raise ValueError(f"รูปแบบ CSV ของ FRED {series} ไม่ถูกต้อง") from error
        data = pd.Series(values.to_numpy(), index=dates).dropna().sort_index()
        data = data.loc[data.index <= cutoff]
        if data.empty or data.index.has_duplicates or not np.isfinite(data).all():
            raise ValueError(f"FRED {series} มีข้อมูลไม่เพียงพอหรือไม่ถูกต้อง")
        latest_date = data.index[-1]
        # GDP observations are quarter-start dates. Delay them until the
        # quarter has ended; the notebook adds its existing one-month lag.
        if series == "GDPC1":
            data.index = data.index + pd.DateOffset(months=3)
        values_on_grid = data.reindex(data.index.union(index)).sort_index().ffill()
        frame[column] = values_on_grid.reindex(index)
        available = data.copy()
        available.index = available.index + pd.offsets.MonthBegin(1)
        eligible = available.loc[available.index <= cutoff]
        metadata.append({
            "series": series, "label": label, "units": units,
            "observationDate": latest_date.date().isoformat(),
            "latestValue": float(raw.loc[dates == latest_date, series].iloc[-1]),
            "usedValue": float(eligible.iloc[-1]) if not eligible.empty else None,
            "availableFrom": eligible.index[-1].date().isoformat() if not eligible.empty else None,
            "url": f"https://fred.stlouisfed.org/series/{series}",
        })
    frame = frame.dropna()
    if len(frame) < 60:
        raise ValueError("ประวัติ Macro จาก FRED ไม่ครอบคลุมอย่างน้อย 60 เดือน")
    frame.index.name = "date"
    return frame.to_csv(), metadata

