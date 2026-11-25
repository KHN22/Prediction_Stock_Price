"""Diagnostic: why do feature sets diverge at the 6m horizon?"""
import ast, io, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
NB = ROOT / "MU_Capstone_v5_WalkForward_Improved.ipynb"
cells = json.loads(NB.read_text(encoding="utf-8"))["cells"]

def source(i):
    return "".join(cells[i]["source"])

def quiet(*a, **k):
    pass

D = ROOT / "data"
prices = pd.read_csv(D / "mu_prices.csv")
prices.columns = prices.columns.str.strip()
prices["date"] = pd.to_datetime(prices["date"], utc=True, errors="coerce", format="mixed")
if "stock_splits" not in prices:
    prices["stock_splits"] = 0
for c in ["open", "high", "low", "close", "volume"]:
    prices[c] = pd.to_numeric(prices[c], errors="coerce")

macro = pd.read_csv(D / "cleaned_macro_data.csv")
income_raw = pd.read_csv(D / "mu_income_statement_raw.csv")
earnings_raw = pd.read_csv(D / "mu_earnings_raw.csv")
cash_raw = pd.read_csv(D / "mu_cash_flow_raw.csv")
balance_raw = pd.read_csv(D / "mu_balance_sheet_raw.csv")

env = {"np": np, "pd": pd, "ast": ast, "print": quiet, "display": quiet, "prices": prices}
exec(source(10).split("plt.figure", 1)[0], env)
exec(source(12), env)
env.update(macro=macro, income_raw=income_raw, earnings_raw=earnings_raw,
           cash_raw=cash_raw, balance_raw=balance_raw)
exec(source(6).split("for name, table in", 1)[0], env)
exec(source(14), env)

from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error

models = {
    'Ridge': Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True)), ('scale', StandardScaler()), ('model', Ridge(alpha=30.0))]),
    'RandomForest': Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True)), ('model', RandomForestRegressor(n_estimators=400, min_samples_leaf=8, max_features=0.7, random_state=42, n_jobs=2))]),
    'ExtraTrees': Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True)), ('model', ExtraTreesRegressor(n_estimators=400, min_samples_leaf=8, max_features=0.7, random_state=42, n_jobs=2))]),
    'HistGradientBoosting': Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True)), ('model', HistGradientBoostingRegressor(max_iter=150, learning_rate=0.03, max_leaf_nodes=15, l2_regularization=5.0, random_state=42))]),
}

df = env["df"]; HORIZONS = env["HORIZONS"]; feature_sets = env["feature_sets"]

def calc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    return dict(MAE=mean_absolute_error(y, p), RMSE=mean_squared_error(y, p) ** 0.5,
                bias=float(np.mean(p - y)),
                diracc=float(np.mean(np.sign(y) == np.sign(p))))

rows = []
fold_rows = []
for horizon in ["6m", "3m", "1m"]:
    h = HORIZONS[horizon]
    target = f'target_log_return_{horizon}'; target_date = f'target_date_{horizon}'
    usable = df.dropna(subset=[target, target_date]).sort_values('date').reset_index(drop=True)
    n = len(usable); test_start_pos = int(n * 0.80)
    test_start = usable.loc[test_start_pos, 'date']
    pretest = usable.iloc[:test_start_pos].copy()
    test = usable.iloc[test_start_pos:].copy()
    pretest = pretest[pretest[target_date] < test_start].copy()
    print(f"\n=== {horizon} (h={h}) usable={n} pretest={len(pretest)} test={len(test)} "
          f"test_range={test['date'].min().date()}..{test['date'].max().date()} ===")

    for set_name, feature_list in feature_sets.items():
        cols = [c for c in feature_list if c in usable.columns and pretest[c].notna().any()]
        # CV fold scores (same as notebook)
        fold_scores = {m: [] for m in models}
        tscv = TimeSeriesSplit(n_splits=4)
        for tr_idx, va_idx in tscv.split(pretest):
            tr = pretest.iloc[tr_idx].copy(); va = pretest.iloc[va_idx].copy()
            va_start = va['date'].min()
            tr = tr[tr[target_date] < va_start]
            if len(tr) < 150 or len(va) < 25:
                continue
            for mn, est in models.items():
                m = clone(est); m.fit(tr[cols], tr[target]); pred = m.predict(va[cols])
                fold_scores[mn].append(mean_squared_error(va[target], pred) ** 0.5)
        # Fit EVERY model on all pretest, eval on test — see which CV mispicks
        test_rows = {}
        for mn, est in models.items():
            m = clone(est); m.fit(pretest[cols], pretest[target])
            pred = m.predict(test[cols])
            test_rows[mn] = calc(test[target], pred)
        for mn, sc in fold_scores.items():
            fold_rows.append(dict(horizon=horizon, feature_set=set_name, model=mn,
                                  cv_rmse=float(np.mean(sc)) if sc else np.nan,
                                  n_folds=len(sc)))
        best_cv = min((k for k, v in fold_scores.items() if len(v) >= 2),
                      key=lambda k: np.mean(fold_scores[k]))
        for mn, sc in test_rows.items():
            rows.append(dict(horizon=horizon, feature_set=set_name, model=mn,
                             cv_rmse=float(np.mean(fold_scores[mn])) if fold_scores[mn] else np.nan,
                             picked=(mn == best_cv),
                             **{f'test_{k}': v for k, v in sc.items()}))

res = pd.DataFrame(rows)
pd.set_option('display.width', 250)
print("\n--- TEST metrics per model (6m) ---")
print(res[res.horizon == '6m'][['feature_set','model','picked','test_RMSE','test_MAE','test_bias','test_diracc','cv_rmse']].to_string(index=False))
print("\n--- CV fold RMSE spread per model (6m) ---")
fr = pd.DataFrame(fold_rows)
print(fr[fr.horizon=='6m'].pivot_table(index=['feature_set','model'], values='cv_rmse').to_string())

# Overlap diagnostic: 6m targets overlap heavily -> effective sample size
t6 = 'target_log_return_6m'
u6 = df.dropna(subset=[t6, 'target_date_6m']).sort_values('date')
print("\n6m target overlap: consecutive target dates separated by", h, "sessions;",
      "test rows:", len(test) if horizon=='6m' else '')
# autocorrelation of 6m target in test period
if horizon == '6m':
    tv = test[t6].values
    print("test target autocorr lag1:", np.corrcoef(tv[:-1], tv[1:])[0,1].round(3),
          "| std:", tv.std().round(3), "| mean:", tv.mean().round(3))
    # what did price actually do in test window?
    print("test actual 6m log-return stats: min %.3f max %.3f mean %.3f" % (tv.min(), tv.max(), tv.mean()))
    # baseline check
    mom = test['return_21d'].fillna(0)
    bm = np.log1p(mom.values)
    print("momentum_21d baseline:", calc(test[t6], bm))
    # spread between feature-set predictions (picked models)
    picks = {}
    for mn in models:
        pass
