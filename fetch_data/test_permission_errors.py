"""Offline tests: denied interfaces stop once without suppressing other datasets."""
import contextlib
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fetch_data import download_amv_research as research
from fetch_data import run_all_fetch as runner
from fetch_data.permission_errors import is_permission_denied


class PermissionTests(unittest.TestCase):
    def tearDown(self):
        research.DENIED_TOOLS.clear()

    def test_rate_limit_and_network_errors_are_not_permissions(self):
        self.assertTrue(is_permission_denied('没有接口(ths_index)访问权限'))
        self.assertTrue(is_permission_denied('tushare API error [40203]'))
        for error in ['频率超限', '访问频繁', 'Connection timed out', 'HTTP 503']:
            self.assertFalse(is_permission_denied(error))

    def test_relay_requests_denied_interface_once_and_continues_others(self):
        denied = Mock(text='{"result": {}}')
        denied.json.return_value = {'code':40203,'msg':'no permission'}
        allowed = Mock(text='{"result": {}}')
        allowed.json.return_value = {'code':0,'data':{'fields':[],'items':[]}}
        output = io.StringIO()
        with patch.dict('os.environ', {'TUSHARE_RELAY_TOKEN':'test-relay-token'}), patch.object(research.SESSION, 'post', side_effect=[denied, allowed]) as post, patch.object(research.time, 'sleep'), contextlib.redirect_stdout(output):
            for code in ['A', 'B', 'C']:
                with self.assertRaises(research.InterfacePermissionDenied):
                    research.rpc('tools/call', {'name':'ths_daily', 'arguments':{'ts_code':code}})
            research.rpc('tools/call', {'name':'daily_info','arguments':{}})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(output.getvalue().count('[SKIP]'), 1)
        self.assertNotIn('retry', output.getvalue())

    def test_sdk_flow_permission_exits_before_retry(self):
        for api in ['moneyflow_cnt_ths', 'moneyflow_ind_ths', 'moneyflow_ind_dc']:
            with self.subTest(api=api):
                module = importlib.import_module('fetch_data.fetch_'+api)
                client = Mock()
                getattr(client, api).side_effect = RuntimeError('没有接口('+api+')访问权限')
                output = io.StringIO()
                with patch.object(module, 'pro', client, create=True), patch.object(module.time, 'sleep') as sleep, contextlib.redirect_stdout(output):
                    with self.assertRaises(SystemExit) as error:
                        getattr(module, 'fetch_'+api)('20240910', '20240916')
                self.assertEqual(error.exception.code, 3)
                getattr(client, api).assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(output.getvalue().count('[SKIP]'), 1)

    def test_runner_counts_permission_skip_separately(self):
        with patch.object(runner.subprocess, 'run', return_value=Mock(returncode=3)), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(runner.run_script('fetch_etf.py', []))
        output = io.StringIO()
        with patch.object(runner, 'run_script', side_effect=lambda name,args: None if name=='fetch_moneyflow_cnt_ths.py' else True), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as error:
                runner.main()
        self.assertEqual(error.exception.code,3)
        self.assertIn(f'{len(runner.SCRIPTS)-1} 成功, 0 失败, 1 跳过', output.getvalue())
        self.assertIn('跳过：同花顺概念资金', output.getvalue())

    def test_research_continues_without_catalog_and_preserves_archives(self):
        import sys
        sys.path.insert(0, str(research.PROJECT/'flask_backend'))
        import market_store
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ['metadata', 'ths_index', 'ths_daily', 'ths_member']:
                (root/folder).mkdir()
            (root/'metadata/industry_universe.json').write_text(json.dumps({'codes':['A','B']}))
            originals = ['ths_index/industry_snapshot.csv','ths_daily/all_industries.csv','ths_member/all_industries.csv']
            for name in originals:(root/name).write_text('keep existing data')
            calls=[]
            def query(tool,args,key):
                calls.append(tool)
                if tool=='trade_cal':return [{'cal_date':'20260930','is_open':1}]
                research.DENIED_TOOLS.add(tool)
                raise research.InterfacePermissionDenied(tool)
            with patch.object(research,'ROOT',root), patch.object(research,'archive_output'), patch.object(research,'rpc',return_value={'tools':[]}), patch.object(research,'query',side_effect=query), patch.object(research,'monthly',return_value=[]), patch.object(market_store,'file_content',return_value=b'date,close\n2026-09-30,1\n'), patch.object(market_store,'list_files',return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(research.main(['--start','20260930','--end','20260930']),3)
            for name in originals:self.assertEqual((root/name).read_text(),'keep existing data')
            report=json.loads((root/'download_manifest.json').read_text(encoding='utf8'))
            self.assertEqual(report['failures'],[])
            self.assertIn('ths_index',report['skipped_interfaces'])
            self.assertIn('ths_member',calls)


if __name__=='__main__':
    unittest.main()
