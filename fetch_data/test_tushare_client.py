import datetime as dt
import unittest
import threading
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from fetch_data import tushare_client as client


class RelayTests(unittest.TestCase):
    def test_provider_switch_selects_matching_url_and_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.ini'
            for provider, expected_token in [('official', 'official-secret'), ('relay', 'relay-secret')]:
                path.write_text('[tushare]\nprovider = '+provider+'\n[official]\nurl = http://api.waditu.com/dataapi/{api_name}\ntoken = official-secret\n[relay]\nurl = http://tus.sxdata.top/tu_share/\ntoken = relay-secret\n', encoding='utf-8')
                session = Mock()
                session.post.return_value.json.return_value = {'code':0, 'data':{'fields':[], 'items':[]}}
                with patch.object(client, 'CONFIG_PATH', path), patch.dict('os.environ', {'TUSHARE_TOKEN':'official-secret', 'TUSHARE_RELAY_TOKEN':'relay-secret'}):
                    client.RelayClient(session).daily(trade_date='20260930')
                args, kwargs = session.post.call_args
                self.assertEqual(kwargs['json']['token'], expected_token)
                self.assertEqual(args[0], 'http://api.waditu.com/dataapi/daily' if provider == 'official' else 'http://tus.sxdata.top/tu_share/')

    def test_config_token_precedes_environment(self):
        with patch.dict('os.environ', {'TUSHARE_TOKEN':'environment-secret'}):
            self.assertEqual(client.get_token(dict(provider='official', token='configured-secret', token_env='TUSHARE_TOKEN')), 'configured-secret')

    def test_blank_config_does_not_fall_back_to_environment(self):
        with patch.dict('os.environ', {'TUSHARE_TOKEN':'environment-secret', 'TUSHARE_RELAY_TOKEN':'relay-secret'}):
            with self.assertRaisesRegex(RuntimeError, 'Configure'):
                client.get_token(dict(provider='official', token=''))

    def test_deadline_bounds_stalled_body(self):
        release = threading.Event()
        session = Mock()
        session.post.return_value.json.side_effect = lambda: release.wait(5)
        try:
            with self.assertRaisesRegex(TimeoutError, 'entire request'):
                client.request_body(session, {}, deadline=0.03)
        finally:
            release.set()

    def test_sdk_route_fields_and_credentials(self):
        session = Mock()
        session.post.return_value.json.return_value = {'code': 0, 'data': {'fields': ['close'], 'items': [[12]]}}
        with patch.object(client, 'get_token', return_value='relay-secret'):
            frame = client.RelayClient(session).daily(ts_code='000001.SZ', fields=['close'])
        self.assertEqual(frame.iloc[0]['close'], 12)
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], client.ENDPOINT)
        self.assertEqual(kwargs['json'], {'api_name': 'daily', 'token': 'relay-secret', 'params': {'ts_code': '000001.SZ'}, 'fields': 'close'})

    def test_ranges_have_no_gaps_or_overlap(self):
        batches = list(client.date_batches({'start_date':'20200101', 'end_date':'20261016', 'ts_code':'A'}))
        cursor = dt.date(2020, 1, 1)
        for batch in batches:
            self.assertEqual(batch['start_date'], cursor.strftime('%Y%m%d'))
            last = dt.datetime.strptime(batch['end_date'], '%Y%m%d').date()
            self.assertLessEqual((last-cursor).days, 365)
            self.assertEqual(batch['ts_code'], 'A')
            cursor = last + dt.timedelta(days=1)
        self.assertEqual(cursor, dt.date(2026,10,17))

    def test_incomplete_results_are_not_saved_as_success(self):
        for flag in ['pending', 'partial', 'backfill_pending']:
            session = Mock()
            session.post.return_value.json.return_value = {'code':0, 'meta':{flag:True}, 'data':{'fields':[], 'items':[]}}
            with patch.object(client, 'get_token', return_value='secret'), self.assertRaisesRegex(RuntimeError, 'incomplete'):
                client.RelayClient(session).daily(trade_date='20260930')

    def test_error_redacts_key(self):
        session = Mock()
        session.post.side_effect = RuntimeError('secret failure')
        with patch.object(client, 'get_token', return_value='secret'), self.assertRaisesRegex(RuntimeError, r'\[REDACTED\] failure'):
            client.RelayClient(session).daily(trade_date='20260930')


if __name__ == '__main__':
    unittest.main()
