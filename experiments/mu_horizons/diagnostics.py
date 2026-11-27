"""Control-only temporal checks and matched six-month financial ablation."""
from experiment import control, df, env, partitions, sets, save, OUT, raw_weight, rmse
from sklearn.base import clone
import numpy as np
import pandas as pd

def audit_alignment():
    macro=env["macro"].sort_values("date").set_index("date")
    fin=env["fin"].sort_values("date").set_index("date")
    for table,cols in [(macro,env["macro_features"]),(fin,env["financial_features"])]:
        expected=table[cols].reindex(pd.DatetimeIndex(df.date),method="ffill")
        np.testing.assert_allclose(expected.to_numpy(),df[cols].to_numpy(),equal_nan=True)
    financial_ages=(pd.Series(df.date.values)-pd.Series(fin.index.to_series().reindex(df.date,method="ffill").values)).dt.days
    quarter_gap=fin.fiscalDateEnding.sort_values().diff().dt.days
    eq=env["earnings_q"]
    return dict(market_days=len(df),fin_quarters_in_daily_frame=df.fiscalDateEnding.nunique(),
                fin_max_age_days=financial_ages.max(),reported_dates_missing=int(pd.to_datetime(eq.reportedDate,errors="coerce").isna().sum()),
                quarterly_gaps_over_110_days=int((quarter_gap>110).sum()),max_period_gap_days=quarter_gap.max(),
                macro_dates=len(macro),aligned_financial_cells=len(df)*len(env["financial_features"]),
                aligned_macro_cells=len(df)*len(env["macro_features"]))

def diagnose():
    save("availability",[audit_alignment()])
    train,test,folds=partitions("6m")
    y=df.model_target_6m.to_numpy()
    feat=list(sets)
    members=next(r["ensemble_members"] for r in control["results"] if r["feature_set"]==feat[-1] and r["horizon"]=="6m")
    records=[]
    for name in feat:
        cols=[c for c in sets[name] if df[c].iloc[train].notna().any()]
        by_member={m:[] for m in members+["ensemble"]}
        labels=[]
        for k,(tr,va) in enumerate(folds,1):
            ids=env["thin_validation"](df.iloc[va],126).index.to_numpy()
            pred={m:clone(env["models"][m]).fit(df[cols].iloc[tr],y[tr]).predict(df[cols].iloc[ids]) for m in members}
            pred["ensemble"]=np.mean(list(pred.values()),axis=0)
            for m,r in pred.items():
                by_member[m].extend(r)
                records.append(dict(feature=name,member=m,fold=k,n=len(ids),max_abs=np.max(abs(r)),
                    rmse=rmse(y[ids]-r),raw_weight=raw_weight(y[ids],r),dot=y[ids]@r,norm=r@r))
            labels.extend(y[ids])
        for m,values in by_member.items():
            r=np.array(values)
            records.append(dict(feature=name,member=m,fold="pooled",n=len(labels),max_abs=np.max(abs(r)),
                rmse=rmse(labels-r),raw_weight=raw_weight(np.array(labels),r),dot=labels@r,norm=r@r))
    save("financial_ablation",records)

def ridge_peak():
    train,_,folds=partitions("6m")
    tr,va=folds[0]
    ids=env["thin_validation"](df.iloc[va],126).index.to_numpy()
    cols=[c for c in list(sets.values())[-1] if df[c].iloc[train].notna().any()]
    model=clone(env["models"]["Ridge"]).fit(df[cols].iloc[tr],df.model_target_6m.iloc[tr])
    x=df[cols].iloc[ids]
    pred=model.predict(x)
    j=np.argmax(abs(pred))
    z=model[:-1].transform(x)[j]
    terms=z*model[-1].coef_
    np.testing.assert_allclose(terms.sum()+model[-1].intercept_,pred[j])
    names=model[0].get_feature_names_out(cols)
    rows=[]
    for i in np.argsort(-abs(terms)):
        field=names[i]
        rows.append(dict(validation_date=df.date.iloc[ids[j]].date(),feature=field,term=terms[i],z=z[i],
            raw=x.iloc[j].get(field,np.nan),train_min=df[field].iloc[tr].min() if field in cols else np.nan,
            train_max=df[field].iloc[tr].max() if field in cols else np.nan,
            intercept=model[-1].intercept_,ridge_pred=pred[j]))
    save("ridge_peak",rows)

def diagnose_errors():
    data=pd.read_csv(OUT/"predictions.csv")
    rows,phase=[],[]
    for (horizon,feature),g in data.groupby(["horizon","feature_set"]):
        h=env["HORIZONS"][horizon]
        old=g[g.arm=="control"]
        new=g[g.arm=="challenger"]
        assert old.target.tolist()==new.target.tolist()
        y=old.actual_log.to_numpy()
        a=old.pred_log.to_numpy()
        b=new.pred_log.to_numpy()
        # Positive lag: changes in the forecast follow changes in realized h-session returns.
        for lag in [-21,-10,-5,-1,0,1,5,10,21]:
            pred=pd.Series(np.diff(a))
            actual=pd.Series(np.diff(y)).shift(lag)
            rows.append(dict(horizon=horizon,feature=feature,lag=lag,corr=pred.corr(actual)))
        for offset in range(h):
            obs=slice(offset,None,h)
            phase.append(dict(horizon=horizon,feature=feature,offset=offset,n=len(y[obs]),
                              delta_rmse=rmse((b-y)[obs])-rmse((a-y)[obs])))
    save("lag_diagnostic",rows)
    save("nonoverlapping_sensitivity",phase)

if __name__=="__main__":
    ridge_peak()
    diagnose_errors()
    diagnose()
