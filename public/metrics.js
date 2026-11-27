// Legacy AMZN snapshots stored volatility scores under log-return field names.
// Interpret those snapshots without rewriting the saved research data.
export function rmseMetric(model, row) {
  const volatility = model === 'amzn';
  return {
    model: volatility ? row.model_RMSE_log_volatility ?? row.model_RMSE_log_return : row.model_RMSE_log_return,
    baseline: volatility ? row.best_baseline_RMSE_log_volatility ?? row.best_baseline_RMSE_log_return : row.best_baseline_RMSE_log_return,
    unit: volatility ? 'log volatility' : 'log return',
    sample: volatility ? 'CV' : 'test',
    // Older snapshots do not store the CV volatility sample size.
    count: volatility ? row.n_rmse ?? null : row.n_test,
  };
}
