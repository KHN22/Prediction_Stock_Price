"""Adapter for the AMZN Prediction V4 notebook (volatility + conformal intervals)."""

import io
from amzn_direction import direction_forecast
from notebook_sections import load_sections
from forecast_explanations import amzn_sensitivity
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "AMZN_Prediction_V4.ipynb"

# Server-facing file names -> names the notebook reads from its data bundle.
FILEMAP = {
    "amzn_prices.csv": "01_amzn_ohlcv_adjusted.csv",
    "amzn_market.csv": "03_market_competitor_prices.csv",
    "amzn_earnings.csv": "12_amzn_earnings_surprise.csv",
}
REQUIRED = set(FILEMAP)
HORIZON_LABEL = {21: "1m", 63: "3m", 126: "6m"}
QUANTILE_COLS = ["p2.5", "p10", "p25", "p50", "p75", "p90", "p97.5"]


def run(files):
    if set(files) != REQUIRED:
        raise ValueError("ต้องเลือกไฟล์ amzn_prices.csv, amzn_market.csv และ amzn_earnings.csv ครบทั้ง 3 ไฟล์")
    bundle = {notebook_name: files[server_name] for server_name, notebook_name in FILEMAP.items()}

    sections = load_sections(NOTEBOOK, {
        'setup': ('class _FilesZip:', 'HOLDOUT_DAYS'),
        'features': ('def earn_feats(', 'YV[h]'),
        'volatility': ('def vol_predictions(', 'D = {}'),
        'selection': ('def dm_test(', 'BEST ='),
        'intervals': ('def eval_intervals(', 'SHR[h]'),
        'evaluation': ("'Holdout non-overlap'", 'res = pd.DataFrame(rows)'),
        'forecast': ('fc_rows = []', 'def score_log('),
    })

    def source(role):
        return sections[role]

    def quiet(*args, **kwargs):
        pass

    # The notebook imports matplotlib for its plot cells, which the adapter skips.
    if "matplotlib" not in sys.modules:
        mpl = types.ModuleType("matplotlib")
        pyplot = types.ModuleType("matplotlib.pyplot")
        mpl.pyplot = pyplot
        sys.modules.setdefault("matplotlib", mpl)
        sys.modules.setdefault("matplotlib.pyplot", pyplot)

    with tempfile.TemporaryDirectory(prefix="amzn_v4_") as out_dir:
        env = {
            "io": io,
            "AMZN_FILES": bundle,
            "AMZN_OUT": out_dir,
            "print": quiet,
            "display": quiet,
        }
        for role in ("setup", "features", "volatility", "selection", "intervals", "evaluation", "forecast"):
            exec(compile(source(role), f"<amzn_{role}>", "exec"), env)

        idx, close = env["idx"], env["close"]
        last = env["LAST"]
        as_of = last.date().isoformat()
        history = [[stamp.date().isoformat(), float(value)] for stamp, value in zip(idx, close)]

        # Directional accuracy on the non-overlapping CV window.
        def direction(h):
            ev = env["EV"][h]
            cv = ev[(ev.index >= env["CV_START"]) & (ev["end"] < env["HOLDOUT_START"])]
            sub = cv.dropna(subset=["ret", "q0.5", "c0.5"]).iloc[::h]
            if sub.empty:
                return None, None, 0
            model_acc = float(np.mean(np.sign(sub["ret"]) == np.sign(sub["q0.5"])))
            base_acc = float(np.mean(np.sign(sub["ret"]) == np.sign(sub["c0.5"])))
            return model_acc, base_acc, len(sub)

        cvs = env["cvs"]
        res = env["res"]
        fc = env["fc"].set_index("horizon")
        results = []
        for h in env["HORIZONS"]:
            label = HORIZON_LABEL[h]
            frow = fc.loc[h]
            price = float(frow["price"])
            median = float(frow["p50"])
            vol_model = str(frow["vol_model"])

            cv_row = cvs[(cvs["horizon"] == h) & (cvs["model"] == vol_model)].iloc[0]
            naive_row = cvs[(cvs["horizon"] == h) & (cvs["model"] == "naive")].iloc[0]
            model_rmse = float(cv_row["rmse"])
            naive_rmse = float(naive_row["rmse"])
            diracc, base_diracc, n_test = direction(h)

            # Backtest series from the holdout year: [target date, actual, model, baseline,
            # 95% band lo/hi, 80% band lo/hi] as prices.
            ev = env["EV"][h]
            hold = ev[ev.index >= env["HOLDOUT_START"]].dropna(
                subset=["ret", "q0.5", "c0.5", "q0.1", "q0.9", "q0.025", "q0.975"])
            origin_close = close.reindex(hold.index)
            test = []
            origins = []
            baseline_intervals = []
            for (origin, rrow), spot in zip(hold.iterrows(), origin_close):
                end_date = rrow["end"]
                if pd.isna(end_date):
                    continue
                origins.append([origin.date().isoformat(), float(spot)])
                baseline_intervals.append([
                    float(spot * np.exp(rrow["c0.025"])), float(spot * np.exp(rrow["c0.975"])),
                    float(spot * np.exp(rrow["c0.1"])), float(spot * np.exp(rrow["c0.9"])),
                ])
                test.append([
                    pd.Timestamp(end_date).date().isoformat(),
                    float(spot * np.exp(rrow["ret"])),
                    float(spot * np.exp(rrow["q0.5"])),
                    float(spot * np.exp(rrow["c0.5"])),
                    float(spot * np.exp(rrow["q0.025"])),
                    float(spot * np.exp(rrow["q0.975"])),
                    float(spot * np.exp(rrow["q0.1"])),
                    float(spot * np.exp(rrow["q0.9"])),
                ])

            coverage = {}
            for sample in ("CV", "Holdout"):
                crow = res[(res["horizon"] == h) & (res["sample"] == sample) &
                           (res["method"] == "vol-scaled")].iloc[0]
                coverage[sample] = {"cov80": float(crow["cov80"]), "cov95": float(crow["cov95"]),
                                    "width80": float(crow["width80"])}

            results.append({
                "horizon": label,
                "feature_set": "interval_forecast",
                "sessions": int(h),
                "forecast": median,
                "return": median / price - 1.0,
                "best_model": vol_model,
                "model_RMSE_log_volatility": model_rmse,
                "rmse_sample": "CV",
                "n_rmse": int(cv_row["n"]),
                "direction_sample": "CV non-overlap",
                "best_baseline": "naive",
                "best_baseline_RMSE_log_volatility": naive_rmse,
                "beats_best_baseline_RMSE": model_rmse < naive_rmse,
                "model_directional_accuracy": diracc,
                "baseline_directional_accuracy": base_diracc,
                "n_test": n_test,
                "test": test,
                "backtestOrigins": origins,
                "baselineIntervals": baseline_intervals,
                "explanation": amzn_sensitivity(env, h, frow),
                "directionProbability": direction_forecast(env, h, frow),
                "coverage": coverage,
                "intervals": {
                    "targetDate": pd.Timestamp(frow["target_date"]).date().isoformat(),
                    "volModel": vol_model,
                    "shrink": float(frow["shrink"]),
                    "expDailyVol": float(frow["exp_daily_vol"]),
                    "expAnnualVol": float(frow["exp_annual_vol"]),
                    "earningsInWindow": int(frow["earnings_in_window"]),
                    "centerReturn": float(frow["center_return"]),
                    **{q: float(frow[q]) for q in QUANTILE_COLS},
                },
            })

        earnings_raw = pd.read_csv(io.StringIO(bundle["12_amzn_earnings_surprise.csv"]))["Earnings Date"]
        earnings_dates = pd.to_datetime(earnings_raw, utc=True, errors="coerce")
        earnings_dates = earnings_dates.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
        last_key = last.tz_localize(None) if last.tzinfo else last
        past_earnings = earnings_dates[earnings_dates <= last_key]
        inputs = {}
        if not past_earnings.empty:
            inputs["earningsAvailable"] = past_earnings.max().date().isoformat()

        return {
            "model": "amzn",
            "asOf": as_of,
            "history": history,
            "files": sorted(files),
            "inputs": inputs,
            "results": results,
            "sources": {
                "prices": "Yahoo Finance · adjusted daily OHLC",
                "financials": "Yahoo Finance · earnings calendar",
                "macroSeries": [],
                "quarter": inputs.get("earningsAvailable"),
                "note": "AMZN V4 · volatility forecast + rolling conformal intervals · ช่วงราคาไม่ใช่จุดคาดการณ์เดียว · ไม่ใช่คำแนะนำการลงทุน",
            },
        }
