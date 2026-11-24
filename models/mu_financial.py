"""Quarterly statement forecasts using information available by each release."""
import numpy as np
import pandas as pd

LINES = {
    "revenue": "is_totalRevenue",
    "grossProfit": "is_grossProfit",
    "operatingIncome": "is_operatingIncome",
    "netIncome": "is_netIncome",
    "assets": "bs_totalAssets",
    "liabilities": "bs_totalLiabilities",
    "operatingCash": "cf_operatingCashflow",
}


def financial_review(env):
    if "fin" not in env:
        return None
    reports = env["fin"]
    reports = reports[reports.date <= env["df"].date.max()].sort_values("fiscalDateEnding")
    if reports.empty:
        return None
    latest = reports.iloc[-1]
    adjacent = reports.fiscalDateEnding.diff().dt.days.between(65, 115)
    # When a report is missing or arrived out of order, stop extrapolating across it.
    adjacent &= reports.date.diff().dt.days.gt(0)
    review = {"quarter": latest.fiscalDateEnding.date().isoformat(),
              "release": latest.date.date().isoformat(), "lines": {}}
    for key, column in LINES.items():
        if column not in reports or not np.isfinite(latest[column]):
            continue
        values = reports[column].replace([np.inf, -np.inf], np.nan)
        item = {"actual": float(values.iloc[-1])}
        review["lines"][key] = item
        if len(values) < 2 or not adjacent.iloc[-1] or pd.isna(values.iloc[-2]):
            continue
        item["previous"] = float(values.iloc[-2])
        estimates = pd.DataFrame({"carry": values, "trend": values + .5 * values.diff()})
        errors = estimates.shift().sub(values, axis=0).abs()
        errors = errors[adjacent & adjacent.shift(fill_value=False)].dropna()
        if len(errors) < 12:
            continue
        split = int(.75 * len(errors))
        rule = errors.iloc[:split].mean().idxmin()
        test = errors.iloc[split:]
        item.update(rule=rule, estimate=float(estimates[rule].iloc[-1]),
                    testMAE=float(test[rule].mean()), carryMAE=float(test.carry.mean()),
                    testQuarters=len(test))
    return review
