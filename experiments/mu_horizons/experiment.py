"""MU offline research. Production paths are read-only. Run with the project's Python."""
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "2"

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SNAP = HERE / "mu-2026-11-25.json.gz"
NB = ROOT / "MU_Capstone_v5_WalkForward_Improved.ipynb"
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
snapshot_bytes = gzip.decompress(SNAP.read_bytes())
snapshot = json.loads(snapshot_bytes)
control = snapshot["result"]
cells = json.loads(NB.read_text(encoding="utf-8"))["cells"]
def source(i):
    return "".join(cells[i]["source"])
def table(name):
    return pd.read_csv(io.StringIO(snapshot["files"][name]))
def quiet(*args, **kwargs):
    pass

env = dict(np=np, pd=pd, ast=ast, print=quiet, display=quiet, prices=table("mu_prices.csv"),
           macro=table("cleaned_macro_data.csv"))
for key, name in [("income_raw","income_statement"),("earnings_raw","earnings"),
                  ("cash_raw","cash_flow"),("balance_raw","balance_sheet")]:
    env[key] = table("mu_" + name + "_raw.csv")
exec(source(10).split("plt.figure")[0], env)
exec(source(12), env)
exec(source(6).split("for name, table in")[0], env)
exec(source(14), env)
exec(source(16).split("results=[]")[0].replace("n_jobs=-1","n_jobs=2"), env)
df = env["df"]
sets = env["feature_sets"]
assert df.date.is_unique and df.date.is_monotonic_increasing
assert len(control["history"]) == len(df)
np.testing.assert_allclose(df.close, [p[1] for p in control["history"]])
assert (df.date.dt.strftime("%Y-%m-%d").values == [p[0] for p in control["history"]]).all()
def rmse(v):
    return float(np.sqrt(np.mean(np.square(v))))
def raw_weight(err, residual):
    norm = residual @ residual
    return float(err @ residual / norm) if norm > 0 else 0.
def save(name, rows):
    pd.DataFrame(rows).to_csv(OUT / (name + ".csv"), index=False, float_format="%.10g")

def partitions(horizon):
    target_date = df["target_date_" + horizon]
    origins = np.flatnonzero(target_date.notna())
    cut = int(.8 * len(origins))
    test = origins[cut:]
    train = origins[:cut][target_date.iloc[origins[:cut]].to_numpy() < df.date.iloc[test[0]]]
    folds = []
    for tr, va in TimeSeriesSplit(n_splits=4).split(train):
        tr, va = train[tr], train[va]
        tr = tr[target_date.iloc[tr].to_numpy() < df.date.iloc[va[0]]]
        if len(tr) >= 150 and len(va) >= 25:
            assert target_date.iloc[tr].max() < df.date.iloc[va].min()
            folds.append((tr, va))
    assert target_date.iloc[train].max() < df.date.iloc[test].min()
    return train, test, folds

def original_diagnostic():
    horizon = "6m"
    train, test, folds = partitions(horizon)
    y = df["model_target_6m"].to_numpy()
    records = []
    for key, names in sets.items():
        original = next(r for r in control["results"] if r["feature_set"] == key and r["horizon"] == horizon)
        cols = [c for c in names if df[c].iloc[train].notna().any()]
        members = original["ensemble_members"]
        errors, predictions = [], []
        for i, (tr, va) in enumerate(folds, 1):
            ids = env["thin_validation"](df.iloc[va],126).index.to_numpy()
            pred = np.mean([clone(env["models"][m]).fit(df[cols].iloc[tr],y[tr]).predict(df[cols].iloc[ids])
                            for m in members],axis=0)
            errors.extend(y[ids])
            predictions.extend(pred)
            records.append(dict(set=key,fold=i,n=len(ids),dot=y[ids]@pred,norm=pred@pred,
                                raw_weight=raw_weight(y[ids],pred)))
        err, pred = np.array(errors), np.array(predictions)
        ratio = raw_weight(err,pred)
        records.append(dict(set=key,fold="pooled",n=len(err),dot=err@pred,norm=pred@pred,
                            raw_weight=ratio,clipped=np.clip(ratio,0,1),saved=original["blend_weight"]))
        np.testing.assert_allclose(np.clip(ratio,0,1),original["blend_weight"],atol=1e-7)
        save("original_blend_audit",records)
        print("Verified control blend",key,ratio,flush=True)

def baseline_vectors(h):
    price = np.log(df.close)
    ret = lambda k: price.diff(k).fillna(0).to_numpy()
    # Non-overlapping 21-session buckets; older buckets decay geometrically.
    chunks = h // 21
    decay = np.array([.65 ** k for k in range(chunks)])
    buckets = [price.diff(21).shift(21*k).fillna(0).to_numpy() for k in range(chunks)]
    vectors = dict(flat=np.zeros(len(df)), momentum21=ret(21), horizon_momentum=ret(h),
                   decayed=np.average(buckets,weights=decay,axis=0),
                   multi_period=(ret(21)+ret(63)/3+ret(126)/6)/3,
                   reversal=-.5*ret(h), drift=None)
    if h == 21:  # identical definitions at this horizon
        del vectors["horizon_momentum"], vectors["decayed"]
    return vectors

def baseline(vectors, key, target, train, origins):
    if key == "drift":
        return np.full(len(origins),target[train].mean())
    return vectors[key][origins]

def residual_fit(cols,tr,va,y,b_train):
    # Same fixed learner across feature sets and both baseline families.
    active = [c for c in cols if df[c].iloc[tr].notna().any()]
    model = make_pipeline(SimpleImputer(strategy="median",add_indicator=True),
                          StandardScaler(), Ridge(alpha=100.))
    model.fit(df[active].iloc[tr], y[tr]-b_train)
    return model.predict(df[active].iloc[va])

def run():
    metrics, points, latest, candidates, weights, splits, audit = [], [], [], [], [], [], []
    heldout_bases = []
    close = df.close.to_numpy()
    for horizon,h in env["HORIZONS"].items():
        y = df["target_log_return_"+horizon].to_numpy()
        target_dates = df["target_date_"+horizon]
        train,test,folds = partitions(horizon)
        np.testing.assert_allclose(y[:-h], np.log(close[h:] / close[:-h]))
        assert np.array_equal(target_dates.iloc[:-h].values,df.date.iloc[h:].values)
        for i,(tr,va) in enumerate(folds+[(train,test)],1):
            splits.append(dict(horizon=horizon,fold=i if i<=len(folds) else "holdout",n_train=len(tr),n_eval=len(va),
                               last_train_target=target_dates.iloc[tr].max(),first_origin=df.date.iloc[va[0]],last_origin=df.date.iloc[va[-1]],last_target=target_dates.iloc[va[-1]]))
        vectors = baseline_vectors(h)
        scores = {}
        for key in vectors:
            errs=[]
            for i,(tr,va) in enumerate(folds,1):
                error = baseline(vectors,key,y,tr,va)-y[va]
                errs.extend(error)
                candidates.append(dict(horizon=horizon,baseline=key,fold=i,rmse=rmse(error),n=len(va)))
            scores[key]=rmse(errs)
            candidates.append(dict(horizon=horizon,baseline=key,fold="pooled",rmse=scores[key],n=len(errs)))
        winner=min(scores,key=scores.get)
        for key in vectors:
            pred=baseline(vectors,key,y,train,test)
            err=pred-y[test]
            heldout_bases.append(dict(horizon=horizon,baseline=key,selected=key==winner,rmse=rmse(err),
                                      mae=np.mean(abs(err)),direction=np.mean(np.sign(pred)==np.sign(y[test]))))
        all_known = np.flatnonzero(target_dates.le(df.date.iloc[-1]))
        now=np.array([len(df)-1])
        for feature,cols in sets.items():
            original=next(r for r in control["results"] if r["horizon"]==horizon and r["feature_set"]==feature)
            stored=pd.DataFrame(original["test"],columns=["date","actual","pred","reported_benchmark"])
            assert list(stored.date)==target_dates.iloc[test].dt.strftime("%Y-%m-%d").tolist()
            np.testing.assert_allclose(stored.actual,close[test+h])
            old_pred=np.log(stored.pred.to_numpy()/close[test])
            np.testing.assert_allclose(rmse(old_pred-y[test]),original["model_RMSE_log_return"])
            def evaluate(arm,base,correction,key,weight):
                forecast=base+correction
                err=forecast-y[test]
                turns=np.sign(vectors["momentum21"][test])!=np.sign(y[test])
                pred_changes=np.diff(forecast)
                actual_changes=np.diff(y[test])
                metrics.append(dict(horizon=horizon,feature_set=feature,arm=arm,baseline=key,weight=weight,
                    n=len(test),spaced_origins=len(test[::h]),rmse=rmse(err),mae=np.mean(abs(err)),
                    direction=np.mean(np.sign(forecast)==np.sign(y[test])),bias=err.mean(),
                    price_mae=np.mean(abs(close[test]*np.exp(forecast)-close[test+h])),
                    turn_n=turns.sum(),turn_mae=np.mean(abs(err[turns])) if turns.any() else np.nan,
                    change_corr=np.corrcoef(pred_changes,actual_changes)[0,1] if np.std(pred_changes)>0 else np.nan))
                for j,idx in enumerate(test):
                    points.append(dict(horizon=horizon,feature_set=feature,arm=arm,origin=df.date.iloc[idx].date(),
                        target=target_dates.iloc[idx].date(),origin_price=close[idx],actual_price=close[idx+h],
                        predicted_price=close[idx]*np.exp(forecast[j]),actual_log=y[idx],base_log=base[j],
                        weighted_residual_log=correction[j],pred_log=forecast[j]))
            base=vectors["momentum21"][test]
            old_delta = old_pred-base if original["blend_weight"] else np.zeros(len(test))
            np.testing.assert_allclose(base+old_delta,old_pred,atol=1e-10)
            evaluate("control",base,old_delta,"momentum21",original["blend_weight"])
            old_current=np.log1p(original["return"])
            def live(arm,key,w,b,r):
                latest.append(dict(horizon=horizon,feature_set=feature,arm=arm,baseline=key,weight=w,
                    base_log=b,weighted_residual_log=r,base_pct=100*np.expm1(b),
                    residual_increment_pp=100*np.exp(b)*np.expm1(r),total_pct=100*np.expm1(b+r),
                    price=close[-1]*np.exp(b+r)))
            live("control","momentum21",original["blend_weight"],vectors["momentum21"][-1],old_current-vectors["momentum21"][-1] if original["blend_weight"] else 0.)
            for arm,key in [("matched_m21","momentum21"),("challenger",winner)]:
                errors,resids=[],[]
                for i,(tr,va) in enumerate(folds,1):
                    bt=baseline(vectors,key,y,tr,tr)
                    bv=baseline(vectors,key,y,tr,va)
                    resid=residual_fit(cols,tr,va,y,bt)
                    errors.extend(y[va]-bv)
                    resids.extend(resid)
                    weights.append(dict(horizon=horizon,feature_set=feature,arm=arm,fold=i,n=len(va),
                                        raw_weight=raw_weight(y[va]-bv,resid),base_rmse=rmse(y[va]-bv),
                                        unshrunk_rmse=rmse(y[va]-bv-resid)))
                errors,resids=np.array(errors),np.array(resids)
                w=np.clip(raw_weight(errors,resids),0,1)
                weights.append(dict(horizon=horizon,feature_set=feature,arm=arm,fold="pooled",n=len(errors),
                                    raw_weight=raw_weight(errors,resids),base_rmse=rmse(errors),blended_rmse=rmse(errors-w*resids)))
                b=baseline(vectors,key,y,train,test)
                r=residual_fit(cols,train,test,y,baseline(vectors,key,y,train,train))
                evaluate(arm,b,w*r,key,w)
                if arm=="challenger":
                    evaluate("base_only",b,np.zeros(len(b)),key,0)
                b_now=baseline(vectors,key,y,all_known,now)[0]
                r_now=residual_fit(cols,all_known,now,y,baseline(vectors,key,y,all_known,all_known))[0]
                live(arm,key,w,b_now,w*r_now)
            group=cols if feature.startswith("A") else env["macro_features" if feature.startswith("B") else "financial_features"]
            block=df[group].iloc[train]
            corr=block.corr(method="spearman").abs()
            pairs=np.triu(corr.to_numpy()>=.98,k=1)
            audit.append(dict(horizon=horizon,group=feature[0],columns=len(group),constant_or_empty=(block.nunique()<=1).sum(),
                high_corr_pairs=int(pairs.sum()),unique_vectors=len(block.drop_duplicates()),missing_fraction=block.isna().mean().mean(),
                financial_periods=df.fiscalDateEnding.iloc[train].nunique()))
    for name,rows in [("metrics",metrics),("predictions",points),("latest",latest),("baseline_cv",candidates),
                      ("baseline_holdout",heldout_bases),("residual_cv",weights),("splits",splits),("feature_audit",audit)]:
        save(name,rows)
    manifest=dict(as_of=control["asOf"],snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest(),
                  notebook_sha256=hashlib.sha256(NB.read_bytes()).hexdigest(),rows=len(df),start=str(df.date.min().date()))
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

if __name__=="__main__":
    import sys
    if "--audit-original" in sys.argv:
        original_diagnostic()
    else:
        run()
