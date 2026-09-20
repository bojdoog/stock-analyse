from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'back_test_data/amv_research'))
from formula import build_daily_bars


class CandidateBarsTest(unittest.TestCase):
    def setUp(self):
        self.closes = pd.DataFrame({'date': ['2026-09-11', '2026-09-14', '2026-09-15'],
                                    'close': [100., 110., 95.]})
        # Deliberately reversed: the join must match dates, not positions.
        self.market = pd.DataFrame({'date': ['2026-09-15', '2026-09-14', '2026-09-11'],
                                    'volume': [300., 200., 100.], 'amount': [3000., 2000., 1000.]})

    def test_previous_trading_close_and_same_date_benchmark(self):
        result = build_daily_bars(self.closes, self.market)
        self.assertEqual(result.open.tolist(), [100., 100., 110.])
        self.assertEqual(result.high.tolist(), [100., 110., 110.])
        self.assertEqual(result.low.tolist(), [100., 100., 95.])
        self.assertEqual(result.close.tolist(), self.closes.close.tolist())
        self.assertEqual(result.volume.tolist(), [100., 200., 300.])
        self.assertEqual(result.amount.tolist(), [1000., 2000., 3000.])

    def test_missing_benchmark_does_not_fill_from_another_day(self):
        with self.assertRaises(ValueError):
            build_daily_bars(self.closes, self.market.iloc[:2])
        missing_amount = self.market.copy()
        missing_amount.loc[0, 'amount'] = np.nan
        with self.assertRaises(ValueError):
            build_daily_bars(self.closes, missing_amount)

    def test_appending_future_data_keeps_existing_bars(self):
        full = build_daily_bars(self.closes, self.market)
        prefix = build_daily_bars(self.closes.iloc[:2], self.market)
        pd.testing.assert_frame_equal(prefix, full.iloc[:2])


if __name__ == '__main__':
    unittest.main()
