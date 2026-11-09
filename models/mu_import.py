"""Merge updated input files without changing the forecast model."""

import ast
import io
import re

import numpy as np
import pandas as pd

from mu import PRICE, SCHEMA

QUARTERLY = "mu_quarterly_update.csv"
EARNINGS = "mu_earnings_raw.csv"
FIELDS = {
    "mu_income_statement_raw.csv": ("totalRevenue", "grossProfit", "operatingIncome", "netIncome"),
    "mu_cash_flow_raw.csv": ("operatingCashflow", "capitalExpenditures"),
    "mu_balance_sheet_raw.csv": ("totalAssets", "totalLiabilities", "totalShareholderEquity"),
    EARNINGS: ("reportedEPS", "estimatedEPS", "surprise", "surprisePercentage"),
}
KEY = "fiscalDateEnding"
REPORTED = "reportedDate"


def read(content):
    frame = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False)
    frame.columns = frame.columns.str.strip()
    return frame


def dates(values, name):
    result = pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
    if result.isna().any():
        raise ValueError(f"{name}: พบวันที่ไม่ถูกต้อง")
    return result.dt.strftime("%Y-%m-%d")


def merge_series(name, base, update):
    previous, added = read(base), read(update)
    required = SCHEMA[name] if name == PRICE else set(previous.columns)
    if added.empty or required - set(added.columns):
        raise ValueError(f"{name}: ต้องมีข้อมูลและคอลัมน์ {', '.join(sorted(required))}")
    added["date"] = dates(added["date"], name)
    if added["date"].duplicated().any():
        raise ValueError(f"{name}: พบวันที่ซ้ำในไฟล์อัปเดต")
    previous["date"] = dates(previous["date"], name)
    if name == PRICE:
        numeric = added[list(required - {"date"})].apply(pd.to_numeric, errors="coerce")
        if (not np.isfinite(numeric).all().all() or
                (numeric[["open", "high", "low", "close"]] <= 0).any().any() or
                (numeric["volume"] < 0).any() or
                (numeric["high"] < numeric[["open", "low", "close"]].max(axis=1)).any() or
                (numeric["low"] > numeric[["open", "high", "close"]].min(axis=1)).any()):
            raise ValueError(f"{name}: ค่า OHLCV ไม่ถูกต้อง")
    for column in previous.columns.difference(added.columns):
        added[column] = added["date"].map(previous.drop_duplicates("date").set_index("date")[column]).fillna("")
    return pd.concat([previous, added]).drop_duplicates("date", keep="last").sort_values("date").to_csv(index=False)


def report_table(content, name):
    frame = read(content)
    column, = SCHEMA[name]
    try:
        rows = ast.literal_eval(frame[column].iloc[0])
        if not isinstance(rows, list) or not rows or any(
            not isinstance(row, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get(KEY))) for row in rows
        ):
            raise ValueError()
    except (KeyError, IndexError, ValueError, SyntaxError) as error:
        raise ValueError(f"{name}: ต้องใช้รายงาน raw ตามรูปแบบเดิม หรือใช้ {QUARTERLY}") from error
    return frame, column, {row[KEY]: row for row in rows}


def merge_quarters(files, content):
    update = read(content)
    allowed = {KEY, REPORTED, *(field for fields in FIELDS.values() for field in fields)}
    if update.empty or not {KEY, REPORTED}.issubset(update.columns) or set(update.columns) - allowed:
        raise ValueError(f"{QUARTERLY}: กรุณาใช้หัวคอลัมน์จากไฟล์แม่แบบ")
    for column in (KEY, REPORTED):
        update[column] = dates(update[column], QUARTERLY)
    if update[KEY].duplicated().any() or (update[REPORTED] < update[KEY]).any():
        raise ValueError("งบมีวันสิ้นไตรมาสซ้ำ หรือวันประกาศอยู่ก่อนวันสิ้นไตรมาส")
    reports = {name: report_table(files[name], name) for name in FIELDS}
    known = {key for _, _, rows in reports.values() for key in rows}

    for row in update.to_dict("records"):
        quarter = row[KEY]
        fields = {key: value.strip() for key, value in row.items() if key not in (KEY, REPORTED) and value.strip()}
        numbers = pd.to_numeric(pd.Series(fields, dtype=str), errors="coerce")
        if not fields or not np.isfinite(numbers).all():
            raise ValueError("ระบุตัวเลขของงบอย่างน้อยหนึ่งรายการ โดยใช้หน่วย USD เต็มและไม่มีเครื่องหมายคั่นหลัก")
        if quarter not in known:
            nearby = next((key for key in sorted(known)
                           if abs((pd.Timestamp(key) - pd.Timestamp(quarter)).days) <= 14), None)
            if nearby:
                raise ValueError(f"{quarter} อยู่ใกล้ไตรมาสเดิม {nearby} ให้ใช้วันที่เดิมเมื่อต้องการแก้ไตรมาสเดียวกัน")
            if not {"totalRevenue", "operatingCashflow", "capitalExpenditures"}.issubset(fields):
                raise ValueError("ไตรมาสใหม่ต้องมีรายได้ กระแสเงินสดจากการดำเนินงาน และ CapEx")
            known.add(quarter)
        elif (existing := reports[EARNINGS][2].get(quarter, {}).get(REPORTED)) not in (None, "", "None", row[REPORTED]):
            raise ValueError(f"{quarter}: วันประกาศเดิมคือ {existing} ให้ใช้วันเดิมเมื่ออัปเดตไตรมาสเดียวกัน")
        for name, columns in FIELDS.items():
            _, _, rows = reports[name]
            changes = {key: fields[key] for key in columns if key in fields}
            if name == EARNINGS:
                changes[REPORTED] = row[REPORTED]
            if changes:
                rows.setdefault(quarter, {KEY: quarter}).update(changes)
    for name, (frame, column, rows) in reports.items():
        frame.loc[0, column] = repr(list(rows.values()))
        files[name] = frame.to_csv(index=False)


def merge_inputs(base, updates):
    files = base.copy()
    for name, content in updates.items():
        if name == QUARTERLY:
            continue
        if name in (PRICE, "cleaned_macro_data.csv"):
            files[name] = merge_series(name, files[name], content)
        else:
            _, _, new_rows = report_table(content, name)
            frame, column, rows = report_table(files[name], name)
            for key in new_rows.keys() - rows.keys():
                if any(abs((pd.Timestamp(key) - pd.Timestamp(old)).days) <= 14 for old in rows):
                    raise ValueError(f"{name}: {key} อาจซ้ำกับไตรมาสเดิม ให้ใช้วันที่เดิมหรือรันชุด CSV ใหม่ทั้งหมด")
            rows.update(new_rows)
            frame.loc[0, column] = repr(list(rows.values()))
            files[name] = frame.to_csv(index=False)
    if QUARTERLY in updates:
        merge_quarters(files, updates[QUARTERLY])
    return files
