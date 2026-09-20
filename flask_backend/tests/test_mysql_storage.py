"""Opt-in integration tests: MYSQL_INTEGRATION_TESTS=1 uses disposable databases."""
import os
import unittest
import uuid
from contextlib import closing
from unittest.mock import patch

import test_indicators
import test_market_storage


class MySQLFixture:
    def database_target(self, root):
        return 'mysql'

    def setUp(self):
        import pymysql
        from mysql_backend import settings
        self.integrity_error = pymysql.IntegrityError
        options = settings()
        options.pop('database')
        self.test_database = 'stock_test_' + uuid.uuid4().hex
        with closing(pymysql.connect(**options, autocommit=True)) as db:
            with db.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE `{self.test_database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        def cleanup():
            with closing(pymysql.connect(**options, autocommit=True)) as db:
                with db.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE `{self.test_database}`')
        self.addCleanup(cleanup)
        env = patch.dict(os.environ, {'MYSQL_DATABASE': self.test_database})
        env.start()
        self.addCleanup(env.stop)
        super().setUp()


@unittest.skipUnless(os.environ.get('MYSQL_INTEGRATION_TESTS') == '1', 'Opt-in MySQL integration test')
class MySQLMarketTest(MySQLFixture, test_market_storage.MarketStorageTest):
    pass


@unittest.skipUnless(os.environ.get('MYSQL_INTEGRATION_TESTS') == '1', 'Opt-in MySQL integration test')
class MySQLIndicatorTest(MySQLFixture, test_indicators.IndicatorApiTest):
    pass
