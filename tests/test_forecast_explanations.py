import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'models'))
from forecast_explanations import amzn_sensitivity


class ExplanationTest(unittest.TestCase):
    def test_amzn_sensitivity_matches_linear_volatility_ratio(self):
        features = pd.DataFrame({'d': [0., 1., 2., 3.], 'vix': [0., 2., 1., 4.]})
        y = features.d * .1 + features.vix * .2
        env = {'FH': {21: features}, 'END': {21: pd.Series([1., 2., 3., np.nan])},
               'YV': {21: y}, 'HARE': ['d', 'vix'], 'HAR': ['d'],
               'HARX': ['d', 'vix'], 'LinearRegression': LinearRegression}
        forecast = {'vol_model': 'har_vix', 'shrink': .5, 'center_return': .02,
                    'exp_daily_vol': .03, 'earnings_in_window': 1}
        output = amzn_sensitivity(env, 21, forecast)
        effects = {f['group']: f['impactPct'] for f in output['factors']}
        self.assertAlmostEqual(effects['vix'], 100 * np.expm1(.2 * (4 - 1)))
        self.assertAlmostEqual(effects['price'], 100 * np.expm1(.1 * (3 - 1)))


if __name__ == '__main__':
    unittest.main()
