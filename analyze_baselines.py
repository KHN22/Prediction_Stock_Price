"""Compare candidate forecast baselines on the same 80/20 test split as cell 16."""
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
NB = ROOT / "MU_Capstone_v5_WalkForward_Improved.ipynb"

# Use the newest price data embedded in the last computed snapshot.
working = json.loads((ROOT / "data" / "mu.working.json").read_text(encoding="utf-8"))
prices = pd.read_csv(io.StringIO(working["files"]["mu_prices.csv"]))
prices["date"] = pd.to_datetime(prices["date"], utc=True, errors="coerce", format="mixed")
for col in ["open", "high", "low", "close", "volume"]:
    prices[col] = pd.to_numeric(prices[col], errors="coerce")
prices = prices.sort_values("date").reset_index(drop=True)

cells = json.loads(NB.read_text(encoding="utf-8"))["cells"]

def source(i):
    return "".join(cells[i]["source"])

def quiet(*a, **k):
    pass

env = {"np": np, "pd": pd, "print": quiet, "display": quiet, "prices": prices}
exec(source(10).split("plt.figure", 1)[0], env)
exec(source(12), env)
df = env["df"]

HORIZONS = env["HORIZONS"]

def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))

def diracc(y, p):
    return float(np.mean(np.sign(y) == np.sign(p)))

rows = []
for horizon, h in HORIZONS.items():
    target = f"target_log_return_{horizon}"
    mt = f"model_target_{horizon}"
    target_date = f"target_date_{horizon}"
    usable = df.dropna(subset=[target, mt, target_date, "baseline_momentum_log"]).sort_values("date").reset_index(drop=True)
    n = len(usable)
    test_start_pos = int(n * 0.80)
    test_start = usable.loc[test_start_pos, "date"]
    pretest = usable.iloc[:test_start_pos]
    test = usable.iloc[test_start_pos:]
    pretest = pretest[pretest[target_date] < test_start]

    y = test[target].to_numpy()
    hist_mean = float(pretest[target].mean())
    mom21 = test["baseline_momentum_log"].to_numpy()
    # Same-length momentum: recent h-session return as the h-period forecast.
    lag = {21: "return_21d", 63: "return_63d", 126: "return_126d"}[h]
    mom_h = np.log1p(test[lag].fillna(0).to_numpy())
    # Smoothed momentum: expanding-ish mean of daily baseline over trailing window.
    mom_s21 = df["baseline_momentum_log"].rolling(21).mean().reindex(test.index).to_numpy()
    mom_s63 = df["baseline_momentum_log"].rolling(63).mean().reindex(test.index).to_numpy()
    # Blends of momentum with historical mean.
    cands = {
        "zero": np.zeros(len(test)),
        "historical_mean": np.full(len(test), hist_mean),
        "momentum_21d (current)": mom21,
        f"momentum_{h}d": mom_h,
        "mom21_roll21": mom_s21,
        "mom21_roll63": mom_s63,
        "0.5*mom21+0.5*hist": 0.5 * mom21 + 0.5 * hist_mean,
        "0.25*mom21+0.75*hist": 0.25 * mom21 + 0.75 * hist_mean,
    }
    # Oracle-ish blend weight chosen on pretest only (last 50% of pretest as proxy val).
    pv = pretest.iloc[int(len(pretest) * 0.6):]
    pvy = pv[target].to_numpy() - pv["baseline_momentum_log"].to_numpy()
    pvr = pv["baseline_momentum_log"].to_numpy() - hist_mean
    denom = float(np.dot(pvr, pvr))
    a = float(np.clip(np.dot(pvy, pvr) / denom, 0, 1)) if denom > 0 else 0.0
    cands[f"pretest-blend a={a:.2f}"] = hist_mean + a * (mom21 - hist_mean)

    for name, pred in cands.items():
        rows.append({
            "horizon": horizon, "h": h, "baseline": name,
            "rmse": rmse(y, pred), "diracc": diracc(y, pred),
            "test_mean_target": float(np.mean(y)),
        })
    print(f"--- {horizon} (h={h}) test n={len(test)} mean_target={np.mean(y):.3f} hist_mean={hist_mean:.3f}")
    for name, pred in cands.items():
        print(f"  {name:24s} RMSE={rmse(y,pred):.3f} diracc={diracc(y,pred):.2f}")

out = pd.DataFrame(rows)
out.to_csv(ROOT / "baseline_comparison.csv", index=False)
print("\nsaved baseline_comparison.csv")
