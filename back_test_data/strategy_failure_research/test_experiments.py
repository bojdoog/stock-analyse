import unittest
import numpy as np
import pandas as pd
from experiments import Experiment, Rule


def fixture(prices, amv=None):
    engine = Experiment.__new__(Experiment)
    days = pd.date_range('2020-01-01', periods=len(prices)).strftime('%Y-%m-%d')
    engine.prices = pd.DataFrame({'test': prices}, index=days)
    engine.raw = engine.prices.copy()
    engine.amv = pd.DataFrame({'close': amv or prices, 'high': [105] * len(prices)}, index=days)
    engine.weak = pd.Series(True, index=days)
    trade = {'start_date': days[0], 'end_date': days[-1], 'type': 'bull',
             'holdings': [{'name': 'test', 'weight': 1.0}], 'return': prices[-1] / prices[0] - 1}
    return engine, trade


class ManagementTests(unittest.TestCase):
    def test_tranche_buys_at_confirmation_price(self):
        engine, trade = fixture([100, 110, 120])
        curve, details = engine.trade(trade, Rule('half', initial=.5))
        self.assertAlmostEqual(curve.iloc[-1], .5 * 120 / 100 + .5 * 120 / 110)
        self.assertEqual(details['actions'][0]['date'], '2020-01-02')

    def test_unconfirmed_tranche_stays_cash(self):
        engine, trade = fixture([100, 98, 90])
        curve, details = engine.trade(trade, Rule('half', initial=.5))
        self.assertAlmostEqual(curve.iloc[-1], .95)
        self.assertEqual(details['actions'], [])

    def test_protection_does_not_assume_fill_at_threshold(self):
        engine, trade = fixture([100, 110, 100, 105])
        curve, details = engine.trade(trade, Rule('protection', arm=.04, trail=.02))
        self.assertAlmostEqual(curve.iloc[-1], 1.025)
        self.assertEqual(details['actions'][0]['date'], '2020-01-03')
        self.assertAlmostEqual(details['actions'][0]['basket_return_pct'], 0)

    def test_future_price_cannot_change_prior_curve_or_actions(self):
        engine, trade = fixture([100, 110, 100, 105, 115])
        rule = Rule('combo', initial=.5, arm=.04, trail=.02)
        before, events = engine.trade(trade, rule)
        engine.prices.iloc[-1] = 1000
        after, later_events = engine.trade(trade, rule)
        np.testing.assert_allclose(before.iloc[:-1], after.iloc[:-1])
        self.assertEqual(events['actions'], later_events['actions'])

    def test_baseline_retains_buy_hold_returns(self):
        engine, trade = fixture([100, 110, 100, 105])
        curve, _ = engine.trade(trade, Rule('baseline'))
        np.testing.assert_allclose(curve, [1, 1.1, 1, 1.05])


if __name__ == '__main__':
    unittest.main()
