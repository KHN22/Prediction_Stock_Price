// All scores below use the same realized target dates for model and benchmark.
export function backtestPoints(data, row) {
  const index = new Map(data.history.map(([date], i) => [date, i]));
  return (row.test || []).map((values, i) => {
    const [targetDate, actual, predicted, baseline, lo95, hi95, lo80, hi80] = values;
    const targetIndex = index.get(targetDate);
    const originIndex = targetIndex == null ? null : targetIndex - row.sessions;
    const saved = row.backtestOrigins?.[i];
    const origin = saved || (originIndex >= 0 ? data.history[originIndex] : null);
    return {targetDate, targetIndex, originIndex, originDate: origin?.[0] ?? null,
      originClose: origin?.[1] ?? null, actual, predicted, baseline,
      intervals: values.length >= 8 ? [lo95, hi95, lo80, hi80] : null,
      baselineIntervals: row.baselineIntervals?.[i] ?? null};
  }).filter(p => [p.actual, p.predicted, p.baseline].every(v => Number.isFinite(v) && v > 0));
}

export function selectBacktest(points, nonoverlap) {
  if (!nonoverlap) return points;
  let lastTarget = -Infinity;
  return points.filter(point => {
    if (point.originIndex == null || point.originIndex < 0 || point.originIndex < lastTarget) return false;
    lastTarget = point.targetIndex;
    return true;
  });
}

function validBand(band) {
  return Array.isArray(band) && band.length === 4 && band.every(v => Number.isFinite(v) && v > 0)
    && band[0] <= band[2] && band[2] <= band[3] && band[3] <= band[1];
}

export function evaluateBacktest(points, baseline = false) {
  if (!points.length) return null;
  const prediction = p => baseline ? p.baseline : p.predicted;
  const mean = values => values.reduce((a, b) => a + b, 0) / values.length;
  const errors = points.map(p => Math.log(prediction(p) / p.actual));
  const origins = points.filter(p => Number.isFinite(p.originClose) && p.originClose > 0);
  const result = {
    n: points.length,
    rmse: Math.sqrt(mean(errors.map(e => e * e))),
    maeUSD: mean(points.map(p => Math.abs(prediction(p) - p.actual))),
    direction: origins.length ? mean(origins.map(p => Number(Math.sign(prediction(p) - p.originClose) === Math.sign(p.actual - p.originClose)))) : null,
    upRate: origins.length ? mean(origins.map(p => Number(p.actual > p.originClose))) : null,
    nDirection: origins.length,
  };
  const bands = points.map(p => baseline ? p.baselineIntervals : p.intervals);
  // Do not compare scores computed from a smaller subset of the sample.
  if (!bands.every(validBand)) return result;
  const intervalScore = (actual, lower, upper, alpha) => {
    const y = Math.log(actual), lo = Math.log(lower), hi = Math.log(upper);
    return hi - lo + 2 / alpha * (Math.max(lo - y, 0) + Math.max(y - hi, 0));
  };
  for (const [level, lo, hi, alpha] of [[80, 2, 3, .2], [95, 0, 1, .05]]) {
    const hits = points.map((p, i) => Number(p.actual >= bands[i][lo] && p.actual <= bands[i][hi]));
    result['hits' + level] = hits.reduce((a, b) => a + b, 0);
    result['coverage' + level] = mean(hits);
    result['score' + level] = mean(points.map((p, i) => intervalScore(p.actual, bands[i][lo], bands[i][hi], alpha)));
    result['width' + level] = origins.length === points.length
      ? mean(points.map((p, i) => 100 * (bands[i][hi] - bands[i][lo]) / p.originClose)) : null;
  }
  return result;
}
