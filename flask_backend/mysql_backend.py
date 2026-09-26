"""MySQL 8 connection adapter for the shared market store.

Only query placeholders/row access are adapted; schema and upserts are explicit.
Credentials come from MYSQL_* or the ignored instance/mysql.json file.
"""
import json
import os
import re
from pathlib import Path


def settings():
    path = Path(__file__).parent / 'instance' / 'mysql.json'
    config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    defaults = {'host': '127.0.0.1', 'port': 3306, 'user': 'root',
                'password': '', 'database': 'stock_analyse'}
    result = {key: os.environ.get('MYSQL_' + key.upper(), config.get(key, value))
              for key, value in defaults.items()}
    result['port'] = int(result['port'])
    return result


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, cursor):
        self.lastrowid = cursor.lastrowid
        self.rowcount = cursor.rowcount
        names = [column[0] for column in cursor.description] if cursor.description else []
        self.rows = iter(Row(zip(names, row)) for row in cursor.fetchall()) if names else iter(())

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return self.rows


def placeholders(sql):
    # Preserve quoted literals/identifiers, including literal '%' in LIKE clauses.
    tokens = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`)", sql)
    return ''.join(token.replace('%', '%%') if i % 2 else
                   token.replace('%', '%%').replace('?', '%s')
                   for i, token in enumerate(tokens))


class Connection:
    dialect = 'mysql'

    def __init__(self):
        import pymysql
        self.raw = pymysql.connect(**settings(), charset='utf8mb4', autocommit=False,
                                   connect_timeout=10, read_timeout=120, write_timeout=120)
        with self.raw.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")
            cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED')

    def execute(self, sql, args=()):
        with self.raw.cursor() as cursor:
            cursor.execute(placeholders(sql), args)
            return Result(cursor)

    def executemany(self, sql, args):
        with self.raw.cursor() as cursor:
            cursor.executemany(placeholders(sql), args)
            return Result(cursor)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.rollback() if kind else self.commit()


def ensure_schema(db, flow_numbers, flow_text):
    timestamp = "VARCHAR(20) NOT NULL DEFAULT (DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ'))"
    suffix = ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'
    statements = [
        f'''CREATE TABLE IF NOT EXISTS indicators (
            id BIGINT PRIMARY KEY AUTO_INCREMENT, code VARCHAR(191) NOT NULL UNIQUE,
            name TEXT NOT NULL, source TEXT NOT NULL DEFAULT (''),
            description TEXT NOT NULL DEFAULT (''),
            is_default INT NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
            created_at {timestamp}, updated_at {timestamp})''',
        f'''CREATE TABLE IF NOT EXISTS source_files (
            path VARCHAR(512) PRIMARY KEY, category VARCHAR(64) NOT NULL,
            sha256 VARCHAR(64) NOT NULL, content LONGBLOB NOT NULL, row_count BIGINT NOT NULL,
            min_date VARCHAR(10), max_date VARCHAR(10), target_table VARCHAR(64),
            imported_at {timestamp}, INDEX source_category(category))''',
        f'''CREATE TABLE IF NOT EXISTS import_events (
            id BIGINT PRIMARY KEY AUTO_INCREMENT, path VARCHAR(512) NOT NULL,
            sha256 VARCHAR(64) NOT NULL, row_count BIGINT NOT NULL, imported_at {timestamp})''',
        '''CREATE TABLE IF NOT EXISTS instruments (
            category VARCHAR(64) NOT NULL, exchange VARCHAR(8) NOT NULL, code VARCHAR(64) NOT NULL,
            name TEXT NOT NULL, source_path VARCHAR(512) NOT NULL UNIQUE,
            PRIMARY KEY(category,exchange,code),
            FOREIGN KEY(source_path) REFERENCES source_files(path))''',
        '''CREATE TABLE IF NOT EXISTS daily_bars (
            category VARCHAR(64) NOT NULL, exchange VARCHAR(8) NOT NULL, code VARCHAR(64) NOT NULL,
            date VARCHAR(10) NOT NULL, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE NOT NULL,
            volume DOUBLE, amount DOUBLE, source_path VARCHAR(512) NOT NULL,
            `row_number` BIGINT NOT NULL, PRIMARY KEY(category,exchange,code,date),
            INDEX daily_bars_date(date,category,code),
            FOREIGN KEY(source_path) REFERENCES source_files(path))''',
        '''CREATE TABLE IF NOT EXISTS indicator_daily (
            indicator_id BIGINT NOT NULL, date VARCHAR(10) NOT NULL,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE NOT NULL, volume DOUBLE, amount DOUBLE,
            source_path VARCHAR(512) NOT NULL, `row_number` BIGINT NOT NULL,
            PRIMARY KEY(indicator_id,date), FOREIGN KEY(indicator_id) REFERENCES indicators(id),
            FOREIGN KEY(source_path) REFERENCES source_files(path))''',
    ]
    for kind in ('ind_dc', 'cnt_ths', 'ind_ths'):
        fields = ','.join([f'`{key}` DOUBLE' for key in flow_numbers] +
                          [f'`{key}` TEXT' for key in flow_text])
        statements.append(f'''CREATE TABLE IF NOT EXISTS moneyflow_{kind} (
            date VARCHAR(10) NOT NULL, sector_key VARCHAR(191) NOT NULL, occurrence INT NOT NULL,
            {fields}, source_path VARCHAR(512) NOT NULL, `row_number` BIGINT NOT NULL,
            PRIMARY KEY(date,sector_key,occurrence), INDEX sector_date(sector_key,date),
            FOREIGN KEY(source_path) REFERENCES source_files(path))''')
    for sql in statements:
        db.execute(sql + suffix)
    from intraday_store import ensure_schema as intraday_schema
    intraday_schema(db)
    db.commit()
