"""6m target statistics: pretest vs test regime shift."""
import ast, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
NB = ROOT / "MU_Capstone_v5_WalkForward_Improved.ipynb"
cells = json.loads(NB.read_text(encoding="utf-8"))["cells"]
def source(i): return "".join(cells[i]["source"])
def quiet(*a, **k): pass

D = ROOT / "data"
prices = pd.read_csv(D / "mu_prices.csv")
prices.columns = prices.columns.strip() if hasattr(prices.columns, 'strip') else prices.columns
prices.columns = prices.columns.str.strip()
prices["date"] = pd.to_datetime(prices["date"], utc=True, errors="coerce", format="mixed")
prices["stock_splits"] = 0
for c in ["open","high","low","close","volume"]:
    prices[c] = pd.to_numeric(prices[c], errors="coerce")

env = {"np": np, "pd": pd, "ast": ast, "print": quiet, "display": quiet, "prices": prices}
exec(source(10).split("plt.figure", 1)[0], env)
exec(source(12), env)
df = env["df"]; HORIZONS = env["HORIZONS"]

for horizon in ["1m","3m","6m"]:
    h = HORIZONS[horizon]
    t = f'target_log_return_{horizon}'; td = f'target_date_{horizon}'
    u = df.dropna(subset=[t, td]).sort_values('date').reset_index(drop=True)
    n = len(u); pos = int(n*0.80)
    test_start = u.loc[pos,'date']
    pre = u.iloc[:pos]; pre = pre[pre[td] < test_start]
    test = u.iloc[pos:]
    for name, seg in [("pretest", pre), ("test", test), ("all", u)]:
        v = seg[t]
        # effective sample size: targets spaced h sessions apart are ~independent
        ess = len(v) / h
        print(f"{horizon} {name:8s} n={len(v):4d} mean={v.mean():+.3f} std={v.std():.3f} "
              f"min={v.min():+.2f} max={v.max():+.2f} ESS~{ess:.0f} "
              f"P(pos)={(v>0).mean():.2f}")
    ac = np.corrcoef(test[t].values[:-1], test[t].values[1:])[0,1]
    print(f"   test target lag-1 autocorr={ac:.2f}")
    # price path in test window
    print(f"   test close {test['close'].iloc[0]:.1f} -> actual target close mean "
          f"{np.exp(test[t].mean()):.2f}x  |  span {test['date'].min().date()}..{test['date'].max().date()}")
    print()
