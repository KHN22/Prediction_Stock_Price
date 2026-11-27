"""Estimate AMZN terminal direction from historical outcomes and forecast quantiles."""
import numpy as np
import pandas as pd


def direction_forecast(env, h, forecast):
    quantiles = np.asarray(env["QUANTILES"])
    columns = [f"q{q}" for q in quantiles]
    history = env["EV"][h].dropna(subset=["ret", "end", *columns])
    ends, returns = env["END"][h], env["RET"][h]
    cutoff = env["HOLDOUT_START"]

    def score(sample):
        if sample.empty:
            return None
        predictions = []
        for _, block in sample.groupby(sample.index.year):
            known = returns[ends < block.index[0]].dropna()
            if known.empty:
                continue
            base = float((known > 0).mean())
            from_range = np.array([1 - np.interp(0, row, quantiles)
                                   for row in block[columns].to_numpy()])
            observed = (block.ret > 0).to_numpy()
            predictions.extend(zip(((base + from_range) / 2 - observed) ** 2,
                                   (base - observed) ** 2))
        if not predictions:
            return None
        candidate, baseline = np.mean(predictions, axis=0)
        return dict(candidate=float(candidate), baseline=float(baseline), n=len(predictions))

    cv = score(history[(history.index >= env["CV_START"]) & (history.end < cutoff)])
    test = score(history[history.index >= cutoff])
    realized = returns[ends <= env["LAST"]].dropna()
    if realized.empty:
        return None
    base = float((realized > 0).mean())
    prices = np.array([forecast[f"p{q*100:g}"] for q in quantiles])
    from_range = float(1 - np.interp(0, np.log(prices / forecast["price"]), quantiles))
    # The 126-session blend lost to the benchmark in the development holdout.
    blend = h != 126 and cv is not None and cv["candidate"] < cv["baseline"]
    return dict(up=(base + from_range)/2 if blend else base, historicalRate=base,
                rangeUp=from_range, method="rangeBlend" if blend else "historical",
                version=2, cv=cv, holdout=test)
