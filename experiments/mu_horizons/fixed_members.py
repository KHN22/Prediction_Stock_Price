"""Paired baseline intervention: freeze the control's selected members and CV rows."""
import numpy as np
import pandas as pd
from sklearn.base import clone
from threadpoolctl import threadpool_limits
from experiment import (OUT, baseline_vectors, baseline, control, df, env, partitions,
                        raw_weight, rmse, save, sets)

def run():
    scores=pd.read_csv(OUT/"baseline_cv.csv")
    summary, points, folds_out=[],[],[]
    for hor,h in env["HORIZONS"].items():
        pool=scores[(scores.horizon==hor)&(scores.fold=="pooled")]
        key=pool.loc[pool.rmse.idxmin(),"baseline"]
        vectors=baseline_vectors(h)
        tr_final, test, folds=partitions(hor)
        y=df["target_log_return_"+hor].to_numpy()
        all_known=np.flatnonzero(df["target_date_"+hor].le(df.date.iloc[-1]))
        now=np.array([len(df)-1])
        for feature,columns in sets.items():
            old=next(r for r in control["results"] if r["horizon"]==hor and r["feature_set"]==feature)
            def predict(tr,va):
                schema_rows=all_known if tr is all_known else tr_final
                active=[c for c in columns if df[c].iloc[schema_rows].notna().any()]
                b=baseline(vectors,key,y,tr,tr)
                return np.mean([clone(env["models"][m]).fit(df[active].iloc[tr],y[tr]-b).predict(df[active].iloc[va])
                                for m in old["ensemble_members"]],axis=0)
            errors,resids=[],[]
            for k,(tr,va) in enumerate(folds,1):
                ids=env["thin_validation"](df.iloc[va],h).index.to_numpy()
                err=y[ids]-baseline(vectors,key,y,tr,ids)
                r=predict(tr,ids)
                errors.extend(err)
                resids.extend(r)
                folds_out.append(dict(horizon=hor,feature_set=feature,fold=k,n=len(ids),dot=err@r,norm=r@r))
            weight=np.clip(raw_weight(np.array(errors),np.array(resids)),0,1)
            b=baseline(vectors,key,y,tr_final,test)
            r=predict(tr_final,test)
            p=b+weight*r
            latest_base=baseline(vectors,key,y,all_known,now)[0]
            latest_res=predict(all_known,now)[0]
            increment=100*np.exp(latest_base)*np.expm1(weight*latest_res)
            summary.append(dict(horizon=hor,feature_set=feature,baseline=key,members=old["best_model"],weight=weight,
                rmse=rmse(p-y[test]),mae=np.mean(abs(p-y[test])),direction=np.mean(np.sign(p)==np.sign(y[test])),
                bias=(p-y[test]).mean(),price_mae=np.mean(abs(df.close.iloc[test].to_numpy()*np.exp(p)-df.close.iloc[test+h].to_numpy())),
                latest_base_log=latest_base,latest_raw_residual_log=latest_res,latest_weighted_residual_log=weight*latest_res,
                latest_base_pct=100*np.expm1(latest_base),residual_increment_pp=increment,latest_return_pct=100*np.expm1(latest_base+weight*latest_res)))
            for i,idx in enumerate(test):
                points.append(dict(horizon=hor,feature_set=feature,origin=df.date.iloc[idx].date(),target=df.date.iloc[idx+h].date(),
                    actual_log=y[idx],base_log=b[i],raw_residual_log=r[i],weighted_residual_log=weight*r[i],pred_log=p[i]))
            print(hor,feature,flush=True)
    save("fixed_members",summary)
    save("fixed_members_points",points)
    save("fixed_members_folds",folds_out)

if __name__=="__main__":
    with threadpool_limits(limits=2):
        run()
