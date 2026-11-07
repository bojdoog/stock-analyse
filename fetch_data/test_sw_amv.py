import contextlib
import io
import unittest
from unittest.mock import patch
import pandas as pd
from fetch_data.build_sw_amv import contributions
from fetch_data import run_all_fetch as runner


class SwAmvTests(unittest.TestCase):
    def test_missing_industry_carries_contribution_without_future_data(self):
        frame = pd.DataFrame([
            ['2025-01-01','A',10,100000000],
            ['2025-01-01','B',20,200000000],
            ['2025-01-02','A',11,100000000],
            ['2025-01-03','A',12,100000000],
            ['2025-01-03','B',100,900000000],
        ], columns=['date','ts_code','close','amount'])
        result, coverage = contributions(frame,['A','B'])
        prefix, _ = contributions(frame[frame.date<'2025-01-03'],['A','B'])
        pd.testing.assert_series_equal(result.iloc[:2],prefix)
        single, _ = contributions(frame[frame.ts_code=='A'],['A'])
        self.assertAlmostEqual(result.iloc[1]-single.iloc[1],2)
        self.assertEqual(list(coverage),[2,1,2])

    def test_unified_fetch_does_not_run_sw_tasks(self):
        with patch.object(runner,'run_script',return_value=True) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main()
        names=[call.args[0] for call in run.call_args_list]
        self.assertNotIn('fetch_sw_daily.py',names)
        self.assertNotIn('fetch_sw_members.py',names)
        self.assertNotIn('build_sw_amv.py',names)
        self.assertIn('fetch_etf.py',names)


if __name__=='__main__':
    unittest.main()
