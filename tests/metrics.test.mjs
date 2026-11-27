import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { rmseMetric } from '../public/metrics.js';

test('MU retains return RMSE and held-out sample count', () => {
  assert.deepEqual(rmseMetric('mu', {model_RMSE_log_return: .2,
    best_baseline_RMSE_log_return: .3, n_test: 20}),
  {model: .2, baseline: .3, count: 20, unit: 'log return', sample: 'test'});
});

test('new AMZN results use volatility fields and CV count', () => {
  assert.deepEqual(rmseMetric('amzn', {model_RMSE_log_volatility: .4,
    best_baseline_RMSE_log_volatility: .5, n_rmse: 1500, n_test: 25}),
  {model: .4, baseline: .5, count: 1500, unit: 'log volatility', sample: 'CV'});
});

test('existing AMZN snapshot is interpreted without inventing a CV count', () => {
  const snapshot = JSON.parse(readFileSync(new URL('../data/amzn.working.json', import.meta.url)));
  for (const row of snapshot.result.results) {
    const legacy = {...row, model_RMSE_log_return: row.model_RMSE_log_volatility ?? row.model_RMSE_log_return,
      best_baseline_RMSE_log_return: row.best_baseline_RMSE_log_volatility ?? row.best_baseline_RMSE_log_return};
    delete legacy.model_RMSE_log_volatility;
    delete legacy.best_baseline_RMSE_log_volatility;
    delete legacy.n_rmse;
    const before = JSON.stringify(legacy);
    const metric = rmseMetric('amzn', legacy);
    assert.equal(metric.unit, 'log volatility');
    assert.equal(metric.model, legacy.model_RMSE_log_return);
    assert.equal(metric.count, null);
    assert.equal(JSON.stringify(legacy), before);
  }
});
