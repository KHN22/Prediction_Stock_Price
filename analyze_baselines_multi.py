"""Multi-origin walk-forward comparison of baseline candidates."""
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
NB = ROOT / "MU_Capstone_v5_WalkForward_Improved.ipynb"

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

LAG = {21: "return_21d", 63: "return_63d", 126: "return_126d"}

records = []
for horizon, h in HORIZONS.items():
    target = f"target_log_return_{horizon}"
    mt = f"model_target_{horizon}"
    target_date = f"target_date_{horizon}"
    usable = df.dropna(subset=[target, mt, target_date, "baseline_momentum_log"]).sort_values("date").reset_index(drop=True)
    n = len(usable)
    # Rolling origins: each test window is the next 20% of data after the origin.
    for frac in [0.50, 0.60, 0.70, 0.80]:
        start = int(n * frac)
        end = min(int(n * (frac + 0.20)), n)
        if end - start < 30:
            continue
        window = usable.iloc[start:end]
        hist_src = usable.iloc[:start]
        hist_src = hist_src[hist_src[target_date] < window["date"].min()]
        if len(hist_src) < 200:
            continue
        y = window[target].to_numpy()
        hist_mean = float(hist_src[target].mean())
        mom21 = window["baseline_momentum_log"].to_numpy()
        mom_h = np.log1p(window[LAG[h]].fillna(0).to_numpy())
        # smoothed momentum computed on full df, restricted to window
        roll = df["baseline_momentum_log"].rolling(63).mean()
        mom_r63 = roll.reindex(window.index).to_numpy()
        cands = {
            "zero": np.zeros(len(window)),
            "hist_mean": np.full(len(window), hist_mean),
            "mom21": mom21,
            f"mom{h}": mom_h,
            "mom21_roll63": mom_r63,
            "blend_25": 0.25 * mom21 + 0.75 * hist_mean,
        }
        for name, pred in cands.items():
            records.append({"horizon": horizon, "origin": frac, "n_test": len(window),
                            "baseline": name, "rmse": rmse(y, pred)})

res = pd.DataFrame(records)
pivot = res.pivot_table(index=["horizon", "baseline"], columns="origin", values="rmse")
pivot["mean"] = pivot.mean(axis=1)
print(pivot.round(3).to_string())
print("\nMean RMSE across origins:")
print(pivot["mean"].groupby("horizon").rank().astype(int).unstack().to_string())
res.to_csv(ROOT / "baseline_multiorigin.csv", index=False)
