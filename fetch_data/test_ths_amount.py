import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_backend'))
from fetch_data import download_amv_research as fetch


class ThsAmountTest(unittest.TestCase):
    def test_units_and_source_fields(self):
        row = dict(vol=41216068, avg_price=63.2149, close=14029.228)
        calculated = fetch.with_ths_amount([row])[0]
        self.assertAlmostEqual(calculated['amount'], 260546961701.32, places=2)
        self.assertEqual(calculated['avg_price'], row['avg_price'])
        self.assertEqual(calculated['close'], row['close'])
        self.assertNotIn('amount', row)

    def test_missing_invalid_and_zero(self):
        rows = [dict(vol=1), dict(vol=None, avg_price=3), dict(vol=-1, avg_price=3),
                dict(vol=1, avg_price='NaN'), dict(vol='Infinity', avg_price=3),
                dict(vol=1, avg_price=0), dict(vol=0, avg_price=3)]
        result = fetch.with_ths_amount(rows)
        self.assertTrue(all(r['amount'] is None for r in result[:-1]))
        self.assertEqual(result[-1]['amount'], 0)

    def test_fetch_cache_and_csv_keep_derived_amount(self):
        arguments = dict(ts_code='881121.TI', start_date='20240101', end_date='20240102', fields=fetch.THS_DAILY_FIELDS)
        raw = [dict(ts_code='881121.TI', trade_date='20240102', vol=10, avg_price=2.5)]
        response = {'content': [{'type': 'text', 'text': json.dumps(raw)}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(fetch, 'ROOT', Path(folder)), \
                patch.object(fetch, 'archive_output') as archive, patch.object(fetch, 'MANIFEST', []), \
                patch('research_storage.read_file', return_value=None) as read, \
                patch.object(fetch, 'rpc', return_value=response) as rpc:
            first = fetch.query('ths_daily', arguments, '881121.TI')
            cache = Path(folder) / 'raw/ths_daily/881121.TI.json'
            self.assertEqual(first[0]['amount'], 2500)
            self.assertEqual(fetch.read_csv(cache.with_suffix('.csv'))[0]['amount'], '2500.0')
            saved = json.loads(cache.read_text(encoding='utf-8'))
            self.assertEqual(saved['derived_amount']['unit'], 'CNY')
            self.assertTrue(archive.called)
            read.return_value = cache.read_bytes()
            rpc.reset_mock()
            self.assertEqual(fetch.query('ths_daily', arguments, '881121.TI'), first)
            rpc.assert_not_called()
            # Previous request without avg_price must not satisfy the new request.
            saved['request']['arguments']['fields'] = [f for f in fetch.THS_DAILY_FIELDS if f != 'avg_price']
            read.return_value = json.dumps(saved).encode()
            fetch.query('ths_daily', arguments, '881121.TI')
            rpc.assert_called_once()


if __name__ == '__main__':
    unittest.main()
