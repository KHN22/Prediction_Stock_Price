"""Adapter for the original MU Capstone v5 notebook."""

import ast
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "Copy_of_MU_Capstone_v5_WalkForward_Improved.ipynb"
PRICE = "mu_prices.csv"
SCHEMA = {
    PRICE: {"date", "open", "high", "low", "close", "volume"},
    "cleaned_macro_data.csv": {"date"},
    "mu_income_statement_raw.csv": {"quarterlyReports"},
    "mu_earnings_raw.csv": {"quarterlyEarnings"},
    "mu_cash_flow_raw.csv": {"quarterlyReports"},
    "mu_balance_sheet_raw.csv": {"quarterlyReports"},
}


def run(files):
    if set(files) not in ({PRICE}, set(SCHEMA)):
        raise ValueError("เลือก mu_prices.csv เพียงไฟล์เดียว หรือเลือกชุดข้อมูลครบทั้ง 6 ไฟล์")

    tables = {}
    for name, content in files.items():
        table = pd.read_csv(io.StringIO(content))
        table.columns = table.columns.str.strip()
        missing = SCHEMA[name] - set(table.columns)
        if table.empty or missing:
            raise ValueError(f"{name}: ไฟล์ว่างหรือขาดคอลัมน์ {', '.join(sorted(missing))}")
        tables[name] = table

    prices = tables[PRICE]
    prices["date"] = pd.to_datetime(prices["date"], utc=True, errors="coerce", format="mixed")
    if "stock_splits" not in prices:
        prices["stock_splits"] = 0
    for column in SCHEMA[PRICE] - {"date"}:
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
    if not np.isfinite(prices[list(SCHEMA[PRICE] - {"date"})]).all().all() or prices["date"].isna().any():
        raise ValueError("ข้อมูลราคามีวันที่หรือค่า OHLCV ที่อ่านไม่ได้")

    cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]

    def source(index):
        return "".join(cells[index]["source"])

    def quiet(*args, **kwargs):
        pass

    env = {"np": np, "pd": pd, "ast": ast, "print": quiet, "display": quiet, "prices": prices}
    # Skip plot and Colab I/O while running the notebook's original transformations.
    exec(source(10).split("plt.figure", 1)[0], env)
    if len(env["prices"]) < 1100:
        raise ValueError("ต้องมีราคาปิดรายวันอย่างน้อย 1,100 วันซื้อขายเพื่อประเมินครบทั้งสามช่วง")
    exec(source(12), env)
    if len(files) == 1:
        env["feature_sets"] = {"A_price_only": env["technical_features"]}
    else:
        env.update(
            macro=tables["cleaned_macro_data.csv"],
            income_raw=tables["mu_income_statement_raw.csv"],
            earnings_raw=tables["mu_earnings_raw.csv"],
            cash_raw=tables["mu_cash_flow_raw.csv"],
            balance_raw=tables["mu_balance_sheet_raw.csv"],
        )
        try:
            exec(source(6).split("for name, table in", 1)[0], env)
        except (ValueError, SyntaxError) as error:
            raise ValueError("อ่านรายงานรายไตรมาสไม่ได้ กรุณาใช้รูปแบบ raw CSV ของโน้ตบุ๊ก") from error
        for key in ("income_q", "earnings_q", "cash_q", "balance_q"):
            if "fiscalDateEnding" not in env[key]:
                raise ValueError("รายงานรายไตรมาสต้องมี fiscalDateEnding")
        if len(env["macro"].columns) < 2 or pd.to_datetime(env["macro"]["date"], errors="coerce").notna().sum() == 0:
            raise ValueError("ไฟล์ Macro ต้องมีวันที่และตัวแปรเศรษฐกิจ")
        exec(source(14), env)

    # Keep estimator settings and CV intact. Limit tree parallelism on local machines.
    evaluation = source(16).replace("n_jobs=-1", "n_jobs=2")
    exec(evaluation, env)

    frame = env["df"]
    latest = frame.iloc[[-1]]
    as_of = latest["date"].iloc[0]
    inputs = {}
    if "fin" in env:
        financials = env["fin"]
        available = financials[financials["date"] <= as_of]
        if not available.empty:
            current = available.iloc[-1]
            inputs["financialsAvailable"] = current["date"].date().isoformat()
            for key, column in {"revenue": "is_totalRevenue", "fcf": "fin_approx_fcf"}.items():
                value = current.get(column, np.nan)
                inputs[key] = float(value) if np.isfinite(value) else None
        inputs["financialsImported"] = financials["date"].max().date().isoformat() if not financials.empty else None
        macro_dates = env["macro"]["date"]
        macro_date = macro_dates[macro_dates <= as_of].max()
        inputs["macroAvailable"] = macro_date.date().isoformat() if pd.notna(macro_date) else None
    results = []
    for row in env["results_df"].to_dict("records"):
        horizon, feature_set = row["horizon"], row["feature_set"]
        target, target_date = f"target_log_return_{horizon}", f"target_date_{horizon}"
        known = frame.loc[frame[target_date] <= latest["date"].iloc[0]]
        columns = [column for column in env["feature_sets"][feature_set] if known[column].notna().any()]
        model = env["clone"](env["models"][row["best_model"]])
        model.fit(known[columns], known[target])
        predicted_return = float(np.expm1(model.predict(latest[columns])[0]))
        predicted_price = predicted_return * float(latest["close"].iloc[0]) + float(latest["close"].iloc[0])
        if not np.isfinite(predicted_price) or predicted_price <= 0:
            raise ValueError("โมเดลให้ราคานอกช่วงที่แสดงผลได้")
        predictions = env["predictions_df"]
        test = predictions[(predictions.horizon == horizon) & (predictions.feature_set == feature_set)]
        results.append({
            **row,
            "sessions": env["HORIZONS"][horizon],
            "forecast": predicted_price,
            "return": predicted_return,
            "test": [
                [date.date().isoformat(), float(actual), float(predicted),
                 float(close * np.exp(baseline))]
                for date, actual, predicted, close, baseline in zip(
                    test[target_date], test[f"target_close_{horizon}"], test.predicted_close,
                    test.close, test[f"pred_{row['best_baseline']}"],
                )
            ],
        })

    if {result["horizon"] for result in results} != set(env["HORIZONS"]):
        raise ValueError("ข้อมูลที่ผ่านการตรวจสอบยังไม่พอสำหรับทุกช่วงคาดการณ์")
    return {
        "model": "mu",
        "asOf": latest["date"].iloc[0].date().isoformat(),
        "history": [[date.date().isoformat(), float(close)] for date, close in zip(frame.date, frame.close)],
        "files": list(files),
        "inputs": inputs,
        "results": results,
    }
