"""Offline checks for the unified download entry point."""
import contextlib
import io
import unittest
from unittest.mock import patch

from fetch_data import run_all_fetch as runner
from fetch_data import download_amv_research as research


class UnifiedDownloadTests(unittest.TestCase):
    def test_all_datasets_are_scheduled(self):
        scripts = dict(runner.SCRIPTS)
        self.assertEqual(set(scripts), {
            'fetch_etf.py', 'fetch_index.py', 'fetch_kline.py',
            'fetch_moneyflow_cnt_ths.py', 'fetch_moneyflow_ind_dc.py',
            'fetch_moneyflow_ind_ths.py', 'download_amv_research.py',
        })
        self.assertEqual(scripts['download_amv_research.py'],
                         ['--start', '20240910', '--end', runner.today])
        self.assertIn('--exclude-boards', scripts['fetch_kline.py'])

    def test_research_failure_does_not_skip_stock_download(self):
        with patch.object(runner, 'run_script', side_effect=lambda name, args: name != 'download_amv_research.py') as run:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(run.call_count, len(runner.SCRIPTS))
        self.assertEqual(run.call_args.args[0], 'fetch_kline.py')

    def test_invalid_research_dates_do_not_download(self):
        with patch.object(research, 'rpc') as rpc:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    research.main(['--start', '20260921', '--end', '20240910'])
            rpc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
