import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import ast
import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from config import Config
from market_store import (connect, csv_rows, file_content, import_content, instrument_identity,
                          save_dataframe)
from migrate_market_data import verify_file


class MarketStorageTest(unittest.TestCase):
    integrity_error = sqlite3.IntegrityError

    def database_target(self, root):
        return str(root / 'market.sqlite3')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)

        class TestConfig(Config):
            TESTING = True
            DATA_DIR = str(root / 'data')
            DATABASE_PATH = self.database_target(root)

        self.config = TestConfig
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.prices = b'date,open,high,low,close,volume\n2026-09-10,1,3,1,2,50\n2026-09-11,2,4,2,3,60\n'
        self.flow = ('date,industry_name,close,net_inflow,rank,etf_code,etf_name\n'
                     '20260911,bank,10,,,512800,bankETF\n'
                     '20260911,bank,10,-2,49,512800,bankETF\n').encode()
        self.sources = {
            'stock/000001.csv': self.prices,
            'index/000001_test.csv': self.prices,
            'etf/512800_bankETF.csv': self.prices,
            'core_index/0AMV-2013-2026.csv': self.prices,
            'core_index/candidate_amv_close.csv': b'date,close\n2026-09-11,123.456789012345\n',
            'moneyflow_ind_dc/20260911.csv': self.flow,
            'moneyflow_ind_dc/index.json': b'["20260911.csv"]',
        }
        with connect(TestConfig.DATABASE_PATH) as db:
            for name, content in self.sources.items():
                import_content(db, name, content)

    def tearDown(self):
        self.temp.cleanup()

    def test_lossless_idempotent_import_and_rollback(self):
        with connect(self.config.DATABASE_PATH) as db:
            for name, content in self.sources.items():
                self.assertFalse(import_content(db, name, content))
                verify_file(db, name, content)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM import_events').fetchone()[0], len(self.sources))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM moneyflow_ind_dc').fetchone()[0], 2)
            broken = self.prices + b'2026-09-11,2,4,2,999,60\n'
            with self.assertRaises(self.integrity_error):
                import_content(db, 'stock/000001.csv', broken)
            verify_file(db, 'stock/000001.csv', self.prices)
            if self.config.DATABASE_PATH != 'mysql':
                self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_api_works_without_csv_directory(self):
        self.assertFalse(Path(self.config.DATA_DIR).exists())
        for endpoint in ('/api/amv', '/api/kline/stock/000001', '/api/kline/index/000001'):
            response = self.client.get(endpoint + '?start_date=20260911&limit=1')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['data'][0]['date'], '2026-09-11')
            self.assertEqual(response.json['data'][0]['close'], 3)
        self.assertEqual(self.client.get('/api/sector-data').json['data']['etf_data'][0]['id'], '512800')
        self.assertEqual(self.client.get('/api/list/stock').json['data'][0]['code'], '000001')
        for name, original in self.sources.items():
            if name.endswith('.csv'):
                self.assertEqual(self.client.get('/data/' + name).data, original)
        self.assertEqual(self.client.get('/data/moneyflow_ind_dc/index.json').json, ['20260911.csv'])
        self.assertEqual(self.client.get('/api/kline/stock/000001?start_date=bad').status_code, 400)

    def test_close_only_indicator_preserves_nulls(self):
        items = self.client.get('/api/indicators').json['data']
        indicator = next(item for item in items if item['code'] == 'AMV_EMA20')
        result = self.client.get(f"/api/indicators/{indicator['id']}/data").json
        self.assertTrue(result['meta']['close_only'])
        self.assertEqual(result['data'][0]['close'], 123.456789012345)
        for field in ('open', 'high', 'low', 'volume', 'amount'):
            self.assertIsNone(result['data'][0][field])
        empty = self.client.get(f"/api/indicators/{indicator['id']}/data?start_date=20990101")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json['data'], [])
        self.assertTrue(empty.json['meta']['close_only'])

    def test_flow_dates_duplicates_and_nullable_amounts(self):
        result = self.client.get('/api/moneyflow/ind_dc?start_date=2026-09-11&end_date=20260911').json['data']
        self.assertEqual(len(result), 2)
        self.assertIsNone(result[0]['net_inflow'])
        self.assertEqual(result[1]['rank'], 49)
        self.assertEqual(result[0]['date'], '20260911')
        self.assertEqual(self.client.get('/api/moneyflow/ind_dc?limit=1').json['data'][0]['net_inflow'], -2)

    def test_incremental_update_preserves_history_and_is_immediately_visible(self):
        frame = pd.DataFrame([{'date': '2026-09-11', 'open': 2, 'high': 5, 'low': 2, 'close': 4, 'volume': 70},
                              {'date': '2026-09-12', 'open': 4, 'high': 6, 'low': 4, 'close': 5, 'volume': 80}])
        target = Path(self.config.DATA_DIR) / 'stock/000001.csv'
        for _ in range(2):
            save_dataframe(frame, target, self.config.DATABASE_PATH)
        rows = self.client.get('/api/kline/stock/000001').json['data']
        self.assertEqual([r['close'] for r in rows], [2, 4, 5])
        self.assertEqual(target.read_bytes(), file_content('stock/000001.csv', self.config.DATABASE_PATH))
        with connect(self.config.DATABASE_PATH) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM daily_bars WHERE category="stock"').fetchone()[0], 3)

    def test_exchange_and_asset_identity(self):
        self.assertEqual(instrument_identity('stock', '000001.csv')[:3], ('stock', 'SZ', '000001'))
        self.assertEqual(instrument_identity('index', '000001_test.csv')[:3], ('index', 'SH', '000001'))
        self.assertEqual(instrument_identity('stock', '920001.csv')[1], 'BJ')

    def test_concurrent_fetch_updates_keep_both_dates_and_current_export(self):
        target = Path(self.config.DATA_DIR) / 'stock/000001.csv'
        frames = [pd.DataFrame([{'date': day, 'close': value}])
                  for day, value in [('2026-09-12', 4), ('2026-09-13', 5)]]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda frame: save_dataframe(frame, target, self.config.DATABASE_PATH), frames))
        result = self.client.get('/api/kline/stock/000001').json['data']
        self.assertEqual([row['close'] for row in result], [2, 3, 4, 5])
        self.assertEqual(target.read_bytes(), file_content('stock/000001.csv', self.config.DATABASE_PATH))

    def test_download_script_save_functions_write_database(self):
        # Execute actual save functions with fixture data, without importing network clients or fetching.
        project = Path(__file__).resolve().parents[2]
        frame = pd.DataFrame([{'date': '20260912', 'industry_name': 'fixture', 'net_inflow': 1.25}])
        for folder in ('fetch_data',):
            for kind in ('ind_dc', 'ind_ths', 'cnt_ths'):
                script = project / folder / f'fetch_moneyflow_{kind}.py'
                tree = ast.parse(script.read_text(encoding='utf-8-sig'))
                function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                                and node.name == 'save_moneyflow_by_date')
                namespace = {'pd': pd, 'Path': Path, 'logger': logging.getLogger(__name__),
                             'save_dataframe': lambda df, out, category: save_dataframe(
                                 df, out, self.config.DATABASE_PATH, category=category)}
                exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
                namespace['save_moneyflow_by_date'](frame, Path(self.temp.name) / 'custom-export')
                result = self.client.get(f'/api/moneyflow/{kind}?start_date=20260912').json['data']
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['net_inflow'], 1.25)


if __name__ == '__main__':
    unittest.main()
