import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {backtestPoints, selectBacktest, evaluateBacktest} from '../public/backtest.js';

test('coverage and interval scores penalize width and misses', () => {
  const points = [
    {actual: 100, predicted: 100, baseline: 90, originClose: 100, intervals: [70, 140, 90, 110]},
    {actual: 120, predicted: 100, baseline: 100, originClose: 100, intervals: [70, 140, 90, 110]},
  ];
  const score = evaluateBacktest(points);
  assert.equal(score.coverage80, .5);
  assert.equal(score.hits80, 1);
  assert.equal(score.coverage95, 1);
  assert.equal(score.width80, 20);
  assert.equal(score.maeUSD, 10);
  assert.ok(Math.abs(score.rmse - Math.abs(Math.log(100 / 120)) / Math.sqrt(2)) < 1e-12);
  const expected = Math.log(110 / 90) + 5 * Math.log(120 / 110);
  assert.ok(Math.abs(score.score80 - expected) < 1e-12);
});

test('origin reconstruction uses trading sessions rather than calendar days', () => {
  const data = {history: [['2026-01-02', 100], ['2026-01-05', 101], ['2026-01-06', 102]]};
  const [point] = backtestPoints(data, {sessions: 2, test: [['2026-01-06', 102, 103, 100]]});
  assert.equal(point.originDate, '2026-01-02');
  assert.equal(point.originClose, 100);
  assert.equal(point.intervals, null);
});

test('nonoverlap selection uses origin and target indices even with missing dates', () => {
  const points = [
    {originIndex: 0, targetIndex: 3}, {originIndex: 1, targetIndex: 4},
    {originIndex: 3, targetIndex: 6}, {originIndex: 5, targetIndex: 8},
    {originIndex: 7, targetIndex: 10},
  ];
  assert.deepEqual(selectBacktest(points, true), [points[0], points[2], points[4]]);
  assert.equal(selectBacktest(points, false), points);
});

test('missing benchmark bands do not invent coverage or interval scores', () => {
  const point = {actual: 100, predicted: 101, baseline: 100, originClose: 90, intervals: [70, 140, 90, 110]};
  assert.equal(evaluateBacktest([point], true).score80, undefined);
  assert.equal(evaluateBacktest([], false), null);
});

test('saved results match reported coverage and trading-session origin dates', () => {
  for (const name of ['mu', 'amzn']) {
    const {result: data} = JSON.parse(readFileSync(new URL(`../data/${name}.working.json`, import.meta.url)));
    for (const row of data.results) {
      const points = backtestPoints(data, row);
      assert.equal(points.length, row.test.length);
      for (const point of points) {
        assert.equal(point.originDate, data.history[point.originIndex][0]);
        assert.ok(point.originDate < point.targetDate);
      }
      const scores = evaluateBacktest(points);
      if (name === 'amzn') {
        assert.ok(Math.abs(scores.coverage80 - row.coverage.Holdout.cov80) < 1e-12);
        assert.ok(Math.abs(scores.coverage95 - row.coverage.Holdout.cov95) < 1e-12);
        assert.ok(Number.isFinite(evaluateBacktest(points, true).score80));
      } else {
        assert.ok(Math.abs(scores.rmse - row.model_RMSE_log_return) < 1e-12);
      }
    }
  }
});
