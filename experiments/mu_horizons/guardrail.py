"""Exploratory follow-up to the Ridge audit. Development folds only, no test scoring."""
import numpy as np
from sklearn.base import clone
from sklearn.preprocessing import FunctionTransformer
from sklearn.pipeline import Pipeline
from experiment import df, env, partitions, sets, raw_weight, rmse, save

def bounded(z):
    return np.clip(z,-5,5)

def run():
    train,_,folds=partitions("6m")
    cols=[c for c in sets["C_price_macro_financials"] if df[c].iloc[train].notna().any()]
    y=df.model_target_6m.to_numpy()
    outputs=[]
    residuals={"control":[],"bounded_ridge":[]}
    actual=[]
    for fold,(tr,va) in enumerate(folds,1):
        ids=env["thin_validation"](df.iloc[va],126).index.to_numpy()
        x_train,x_val=df[cols].iloc[tr],df[cols].iloc[ids]
        others=sum(clone(env["models"][name]).fit(x_train,y[tr]).predict(x_val)
                   for name in ["HistGradientBoosting","RandomForest"])
        for label in residuals:
            model=clone(env["models"]["Ridge"])
            if label=="bounded_ridge":
                model=Pipeline(model.steps[:-1]+[("bound",FunctionTransformer(bounded))]+model.steps[-1:])
            ridge=model.fit(x_train,y[tr]).predict(x_val)
            residual=(others+ridge)/3
            residuals[label].extend(residual)
            outputs.append(dict(variant=label,fold=fold,n=len(ids),max_abs_ridge=max(abs(ridge)),
                                unshrunk_rmse=rmse(y[ids]-residual),raw_weight=raw_weight(y[ids],residual)))
        actual.extend(y[ids])
    actual=np.array(actual)
    for label,values in residuals.items():
        r=np.array(values)
        w=raw_weight(actual,r)
        outputs.append(dict(variant=label,fold="pooled",n=len(r),raw_weight=w,base_rmse=rmse(actual),
                            unshrunk_rmse=rmse(actual-r),fitted_rmse=rmse(actual-np.clip(w,0,1)*r)))
    save("guardrail_development_only",outputs)

if __name__=="__main__":
    run()
