"""Latest-forecast sensitivities; these describe the fitted model, not causality."""
import numpy as np


def amzn_sensitivity(env, h, forecast):
    """Reproduce the final HAR/stack linear component, holding GJR fixed."""
    model_name = str(forecast["vol_model"])
    if model_name not in ("har", "har_vix", "har_e", "stack"):
        return {"method": "unavailable", "affects": "volatility", "factors": []}
    features = env["FH"][h]
    mask = (env["END"][h].notna() & env["YV"][h].notna()
            & features[env["HARE"]].notna().all(axis=1)).values
    names = {"har": env["HAR"], "har_vix": env["HARX"], "har_e": env["HARE"]}
    if model_name == "stack":
        history = env["D"][h]
        training = history[history.y.notna()].dropna(subset=env["BASE"])
        weights, _ = env["nnls"](training[env["BASE"]].values, training.y.values)
        selected = dict(zip(env["BASE"], weights))
    else:
        selected = {model_name: 1.0}
    groups = {
        "price": ["d", "w", "m", "q", "y", "absr5"],
        "vix": ["vix"],
        "earnings": ["earn_in", "dse"],
    }
    changes = {name: 0.0 for name in groups}
    used = set()
    for name, coefficient in selected.items():
        if name not in names or coefficient == 0:
            continue
        columns = names[name]
        train = features.loc[mask, columns]
        model = env["LinearRegression"]().fit(train, env["YV"][h][mask])
        current = features[columns].iloc[-1]
        reference = train.median()
        for group, members in groups.items():
            indices = [i for i, c in enumerate(columns) if c in members]
            if indices:
                used.add(group)
                changes[group] += float(coefficient * sum(
                    model.coef_[i] * (current.iloc[i] - reference.iloc[i]) for i in indices))
    factors = [{"group": group, "impactPct": float(100 * np.expm1(changes[group]))}
               for group in used]
    factors.sort(key=lambda item: abs(item["impactPct"]), reverse=True)
    return {
        "method": "training_median_group_sensitivity",
        "affects": "volatility",
        "factors": factors,
        "gjrHeldFixed": model_name == "stack" and float(selected.get("gjr", 0)) > 0,
        "components": [{"model": name, "coefficient": float(value)} for name, value in selected.items()],
        "shrink": float(forecast["shrink"]),
        "centerLogReturn": float(forecast["center_return"]),
        "dailyVolatility": float(forecast["exp_daily_vol"]),
        "earningsInWindow": int(forecast["earnings_in_window"]),
    }
