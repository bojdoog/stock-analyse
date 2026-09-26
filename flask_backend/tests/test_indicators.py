import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from config import Config
from market_store import connect, import_content, open_connection


class IndicatorApiTest(unittest.TestCase):
    def database_target(self, root):
        return os.path.join(root, 'indicators.sqlite3')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

        class TestConfig(Config):
            TESTING = True
            DATABASE_PATH = self.database_target(self.temp.name)
            DATA_DIR = os.path.join(self.temp.name, 'data')

        self.config = TestConfig
        os.makedirs(os.path.join(self.config.DATA_DIR, 'core_index'))
        with open(os.path.join(self.config.DATA_DIR, 'core_index', '0AMV-2013-2026.csv'), 'w', encoding='utf-8') as fixture:
            fixture.write('date,open,high,low,close,volume,amount\n2026-09-11,100,110,90,105,20,200\n')
        self.app = create_app(self.config)
        with connect(self.config.DATABASE_PATH) as db:
            with open(os.path.join(self.config.DATA_DIR, 'core_index', '0AMV-2013-2026.csv'), 'rb') as fixture:
                import_content(db, 'core_index/0AMV-2013-2026.csv', fixture.read())
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_intraday_dates_previous_close_and_empty_day(self):
        with connect(self.config.DATABASE_PATH) as db:
            indicator_id = db.execute("SELECT id FROM indicators WHERE code='0AMV'").fetchone()[0]
            for day in ('2026-09-14', '2026-09-15'):
                content = ('date,time,amv,volume_candidate,amount_candidate,source_file\n'
                           f'{day},09:30:59,106,1,2,test.fde\n'
                           f'{day},09:31:59,107,3,4,test.fde\n').encode()
                import_content(db, f'core_index/0AMV-intraday/{day}.csv', content)
        url = f'/api/indicators/{indicator_id}/intraday'
        response = self.client.get(url + '?date=2026-09-14')
        self.assertEqual(response.status_code, 200)
        body = response.json
        self.assertEqual(body['data'], [{'time': '09:30:59', 'amv': 106}, {'time': '09:31:59', 'amv': 107}])
        self.assertEqual(body['meta']['previousClose'], 105)
        self.assertEqual(body['meta']['previousCloseDate'], '2026-09-11')
        self.assertIsNone(body['meta']['previousDate'])
        self.assertEqual(body['meta']['nextDate'], '2026-09-15')
        empty = self.client.get(url + '?date=2026-09-13').json
        self.assertEqual(empty['data'], [])
        self.assertEqual(empty['meta']['nextDate'], '2026-09-14')
        early = self.client.get(url + '?date=2018-01-01').json
        self.assertIsNone(early['meta']['previousClose'])
        for day in ('', '2026-02-30', '2026-9-14', "2026-09-14' OR 1=1"):
            self.assertEqual(self.client.get(url, query_string={'date': day}).status_code, 400)
        self.assertEqual(self.client.get('/api/indicators/999999/intraday?date=2026-09-14').status_code, 404)

    def test_default_indicator_and_idempotent_restart(self):
        create_app(self.config)
        result = self.client.get('/api/indicators').get_json()
        self.assertTrue(result['success'])
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['data'][0]['name'], '活跃市值(默认)')
        self.assertEqual(result['data'][0]['code'], '0AMV')
        self.assertIs(result['data'][0]['is_default'], True)

    def test_database_persistence_search_and_pagination(self):
        with closing(open_connection(self.config.DATABASE_PATH)) as db:
            with db:
                db.execute('INSERT INTO indicators (code, name) VALUES (?, ?)', ('AMV_V2', '活跃市值改进版'))
        restarted = create_app(self.config).test_client()
        result = restarted.get('/api/indicators?current=2&pageSize=1').get_json()
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['data'][0]['code'], 'AMV_V2')
        result = restarted.get('/api/indicators', query_string={'name': '改进', 'code': 'V2'}).get_json()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['data'][0]['code'], 'AMV_V2')
        self.assertEqual(restarted.get('/api/indicators?current=3&pageSize=1').get_json()['data'], [])
        self.assertEqual(restarted.get('/api/indicators', query_string={'name': '%'}).get_json()['total'], 0)
        self.assertEqual(restarted.get('/api/indicators', query_string={'code': "' OR 1=1 --"}).get_json()['total'], 0)

    def test_invalid_pagination(self):
        for query in ('current=0', 'current=oops', 'current=2147483648', 'pageSize=-1', 'pageSize=101'):
            with self.subTest(query=query):
                response = self.client.get('/api/indicators?' + query)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()['success'])

    def test_indicator_data_uses_selected_definition(self):
        default_id = self.client.get('/api/indicators').get_json()['data'][0]['id']
        result = self.client.get(f'/api/indicators/{default_id}/data')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()['data'][0]['close'], 105)
        self.assertEqual(result.get_json()['data'][0]['date'], '2026-09-11')
        with closing(open_connection(self.config.DATABASE_PATH)) as db:
            with db:
                custom_id = db.execute(
                    'INSERT INTO indicators (code, name) VALUES (?, ?)', ('CUSTOM', '自定义指标'),
                ).lastrowid
        result = self.client.get(f'/api/indicators/{custom_id}/data')
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.get_json()['message'], '该指标尚未配置行情数据')
        self.assertNotIn('data', result.get_json())
        self.assertEqual(self.client.get('/api/indicators/999999/data').status_code, 404)


if __name__ == '__main__':
    unittest.main()
