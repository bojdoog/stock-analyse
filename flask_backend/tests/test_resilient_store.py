import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_store as store
import resilient_store as resilient
from app import create_app
from config import Config


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'SQLITE_DATABASE_PATH': str(self.root / 'mirror.sqlite3')})
        env.start()
        self.addCleanup(env.stop)
        resilient._retry_at = 0
        self.addCleanup(setattr, resilient, '_retry_at', 0)

    def save(self, date, close):
        store.save_dataframe(pd.DataFrame([{'date': date, 'close': close}]),
                             self.root / 'stock/000001.csv', 'auto')

    def test_missing_driver_keeps_history_csv_and_pending_queue(self):
        with patch('mysql_backend.Connection', side_effect=ModuleNotFoundError('pymysql')):
            self.save('2026-09-18', 10)
            self.save('2026-09-21', 11)
            content = store.file_content('stock/000001.csv', 'auto')
            self.assertEqual(content, (self.root / 'stock/000001.csv').read_bytes())
            self.assertEqual(pd.read_csv(io.BytesIO(content)).close.tolist(), [10, 11])
            files = store.refresh_index(self.root / 'stock', 'auto')
            self.assertEqual(files, ['000001.csv'])
            with store.connect(resilient.sqlite_path()) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM mysql_pending').fetchone()[0], 2)

    def test_login_failure_serves_sqlite_api(self):
        import pymysql
        with patch('mysql_backend.Connection', side_effect=pymysql.OperationalError(1045, 'access denied')):
            self.save('2026-09-18', 10)
            class LocalConfig(Config):
                DATABASE_PATH = 'auto'
                TESTING = True
            client = create_app(LocalConfig).test_client()
            self.assertEqual(client.get('/api/health').json['storage'], 'sqlite')
            self.assertEqual(client.get('/api/kline/stock/000001').json['data'][0]['close'], 10)

    def test_invalid_data_does_not_commit_or_queue(self):
        with patch('mysql_backend.Connection', side_effect=OSError('offline')):
            self.save('2026-09-18', 10)
            original = store.file_content('stock/000001.csv', 'auto')
            with self.assertRaises(ValueError):
                self.save('2026-09-21', float('inf'))
            self.assertEqual(store.file_content('stock/000001.csv', 'auto'), original)

    def test_research_archive_recovers_missing_csv_without_mysql(self):
        import research_storage
        path = self.root / 'back_test_data/ths_daily/example.csv'
        path.parent.mkdir(parents=True)
        content = b'\xef\xbb\xbfdate,close\r\n20260918,12.5\r\n'
        path.write_bytes(content)
        with patch.object(research_storage, 'PROJECT', self.root), \
                patch('mysql_backend.Connection', side_effect=OSError('offline')):
            research_storage.archive_file(path)
            path.unlink()
            self.assertEqual(research_storage.read_file(path), content)


@unittest.skipUnless(os.environ.get('MYSQL_INTEGRATION_TESTS') == '1', 'Opt-in MySQL test')
class RecoveryTest(FallbackTest):
    def test_outage_recovery_and_repeated_sync(self):
        import uuid
        import pymysql
        from mysql_backend import settings
        from contextlib import closing
        options = settings()
        options.pop('database')
        name = 'stock_test_' + uuid.uuid4().hex
        with closing(pymysql.connect(**options, autocommit=True)) as admin:
            with admin.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        def cleanup():
            with closing(pymysql.connect(**options, autocommit=True)) as admin:
                with admin.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE `{name}`')
        self.addCleanup(cleanup)
        with patch.dict(os.environ, {'MYSQL_DATABASE': name}):
            store.initialize('mysql')
            self.save('2026-09-18', 10)
            with patch('mysql_backend.Connection', side_effect=pymysql.OperationalError(2003, 'offline')):
                self.save('2026-09-21', 11)
                with store.connect('auto') as db:
                    self.assertEqual(getattr(db, 'dialect', 'sqlite'), 'sqlite')
            resilient._retry_at = 0
            real_import = store.import_content
            def commit_then_disconnect(*args, **kwargs):
                real_import(*args, **kwargs)
                raise pymysql.OperationalError(2013, 'connection lost after commit')
            with patch.object(store, 'import_content', side_effect=commit_then_disconnect):
                with store.connect('auto') as db:
                    self.assertEqual(getattr(db, 'dialect', 'sqlite'), 'sqlite')
            resilient._retry_at = 0
            with store.connect('auto') as db:
                self.assertEqual(db.dialect, 'mysql')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM daily_bars').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM import_events').fetchone()[0], 2)
            self.save('2026-09-21', 11)
            with store.connect('auto') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM import_events').fetchone()[0], 2)
            with store.connect(resilient.sqlite_path()) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM mysql_pending').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM daily_bars').fetchone()[0], 2)
