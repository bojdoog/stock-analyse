"""Offline checks for the unified download entry point."""
import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fetch_data import run_all_fetch as runner
from fetch_data import download_amv_research as research
from fetch_data import parse_compass_amv_cache as intraday


class UnifiedDownloadTests(unittest.TestCase):
    def test_all_datasets_are_scheduled(self):
        scripts = dict(runner.SCRIPTS)
        self.assertEqual(set(scripts), {
            'fetch_compass_amv_daily.py',
            'parse_compass_amv_cache.py',
            'import_compass_amv_intraday.py',
            'fetch_etf.py', 'fetch_index.py',
            'fetch_moneyflow_cnt_ths.py', 'fetch_moneyflow_ind_dc.py',
            'fetch_moneyflow_ind_ths.py', 'download_amv_research.py',
        })
        self.assertEqual(scripts['download_amv_research.py'],
                         ['--start', '20240910', '--end', runner.today])
        self.assertEqual(scripts['parse_compass_amv_cache.py'],
                         ['--split-by-date', '--output', str(runner.TOOLS_DIR.parent / 'data' / 'core_index' / '0AMV-intraday')])
        names = [name for name, _ in runner.SCRIPTS]
        self.assertEqual(names.index('import_compass_amv_intraday.py'), names.index('parse_compass_amv_cache.py') + 1)
        self.assertNotIn('fetch_kline.py', scripts)
        self.assertNotIn('fetch_one.py', scripts)

    def test_failure_does_not_skip_research_download(self):
        with patch.object(runner, 'run_script', side_effect=lambda name, args: name != 'fetch_index.py') as run:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(run.call_count, len(runner.SCRIPTS))
        self.assertEqual(run.call_args.args[0], 'download_amv_research.py')

    def test_invalid_research_dates_do_not_download(self):
        with patch.object(research, 'rpc') as rpc:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    research.main(['--start', '20260921', '--end', '20240910'])
        rpc.assert_not_called()

    def test_failed_parse_skips_import_but_other_downloads_continue(self):
        with patch.object(runner, 'run_script', side_effect=lambda name, args: name != 'parse_compass_amv_cache.py') as run:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
        self.assertEqual(error.exception.code, 1)
        names = [call.args[0] for call in run.call_args_list]
        self.assertNotIn('import_compass_amv_intraday.py', names)
        self.assertIn('download_amv_research.py', names)

    def test_failed_import_marks_overall_failure(self):
        with patch.object(runner, 'run_script', side_effect=lambda name, args: name != 'import_compass_amv_intraday.py'):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
        self.assertEqual(error.exception.code, 1)

    def test_daily_file_lock_does_not_skip_intraday(self):
        with patch.object(runner, 'run_script', side_effect=lambda name, args: name != 'fetch_compass_amv_daily.py') as run:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    runner.main()
        self.assertIn('import_compass_amv_intraday.py', [call.args[0] for call in run.call_args_list])

    def test_intraday_uses_header_date_for_current_day_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            output = Path(tmp) / 'output'
            content = struct.pack('<4s4I', b'2ACR', 20260930, 16, 145900, 16) + struct.pack('<Ifff', 145859, 100, 10, 20)
            (source / 'Z_SK0AMV__.fde').write_bytes(content)
            args = ['parse_compass_amv_cache.py', '--source', str(source), '--output', str(output), '--split-by-date']
            with patch('sys.argv', args), contextlib.redirect_stdout(io.StringIO()):
                intraday.main()
            self.assertTrue((output / '2026-09-30.csv').exists())
            report = json.loads((output / 'parse_report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['files'][0]['date'], '2026-09-30')
            original = (output / '2026-09-30.csv').read_bytes()
            (source / 'Z_SK0AMV20260929.fde').write_bytes(b'broken')
            with patch('sys.argv', args):
                with self.assertRaises(SystemExit):
                    intraday.main()
            self.assertEqual((output / '2026-09-30.csv').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
