"""Registry changes propagate to selection/flows without deleting price history."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from config import Config
from etf_catalog import CATALOG_PATH, list_etfs, save, sector_mapping, snapshot
from market_store import connect, import_content


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'market.sqlite3')
        class TestConfig(Config):
            TESTING = True
            DATABASE_PATH = self.path
        self.client = create_app(TestConfig).test_client()
        self.payload = {'etfs': [dict(code=code, name=name, exchange='SH',
            source_path=f'etf/{code}_{name}.csv', enabled=enabled, sort_order=i)
            for i, (code, name, enabled) in enumerate([('512800', 'bank', 1), ('512660', 'military', 0)])],
            'mappings': [dict(flow_type='ind_dc', sector_name=name, etf_code=code)
                         for code, name in [('512800', 'bank'), ('512660', 'military')]]}
        save(self.payload, self.path)
        with connect(self.path) as db:
            for item in self.payload['etfs']:
                import_content(db, item['source_path'], b'date,close\n2026-09-30,10\n')
            import_content(db, 'moneyflow_ind_dc/20260930.csv',
                b'date,industry_name,etf_code,etf_name\n20260930,military,512660,military\n20260930,bank,512800,old_name\n')

    def test_api_and_reimport_never_reenable_disabled_etf(self):
        self.assertEqual([r['code'] for r in self.client.get('/api/etf-types').json['data']], ['512800'])
        self.assertEqual([r['code'] for r in self.client.get('/api/list/etf').json['data']], ['512800'])
        self.assertEqual(self.client.get('/data/etf/index.json').json, ['512800_bank.csv'])
        self.assertEqual([r['id'] for r in self.client.get('/api/sector-data').json['data']['etf_data']], ['512800'])
        self.assertEqual(self.client.get('/api/kline/etf/512660').json['data'][0]['close'], 10)
        with connect(self.path) as db:
            import_content(db, 'etf/512660_military.csv', b'date,close\n2026-09-30,11\n')
        self.assertNotIn('512660', [i['code'] for i in list_etfs(self.path)])
        self.assertNotIn('military', sector_mapping('ind_dc', self.path))
        rows = self.client.get('/api/moneyflow/ind_dc').json['data']
        self.assertEqual(rows[0]['etf_code'], '')
        self.assertEqual(rows[1]['etf_name'], 'bank')

    def test_enable_rename_and_invalid_snapshot_are_atomic(self):
        self.payload['etfs'][1].update(enabled=1, name='renamed')
        save(self.payload, self.path)
        self.assertEqual(sector_mapping('ind_dc', self.path)['military']['name'], 'renamed')
        before = snapshot(self.path)
        self.payload['etfs'][1]['name'] = 'bank'
        with self.assertRaises(ValueError):
            save(self.payload, self.path)
        self.assertEqual(snapshot(self.path), before)

    def test_offline_catalog_commit_queues_snapshot_for_mysql(self):
        import resilient_store
        with patch.dict('os.environ', {'SQLITE_DATABASE_PATH': self.path}), \
                patch('mysql_backend.Connection', side_effect=OSError('offline')):
            self.addCleanup(setattr, resilient_store, '_retry_at', 0)
            save(self.payload, 'auto')
            self.payload['etfs'][0]['enabled'] = 0
            save(self.payload, 'auto')
            self.assertEqual(list_etfs('auto'), [])
            with connect(self.path) as db:
                self.assertIsNotNone(db.execute('SELECT path FROM mysql_pending WHERE path=?', (CATALOG_PATH,)).fetchone())
                archived = json.loads(db.execute('SELECT content FROM source_files WHERE path=?', (CATALOG_PATH,)).fetchone()[0])
                self.assertEqual(archived, self.payload)


if __name__ == '__main__':
    unittest.main()
