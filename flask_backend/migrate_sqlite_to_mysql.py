"""Copy SQLite to MySQL without overwriting populated tables; verify every value."""
import argparse
import json
import re
import sqlite3
from contextlib import closing
from itertools import zip_longest
from pathlib import Path

from market_store import DEFAULT_DATABASE, FLOW_NUMBERS, FLOW_TEXT, connect, writer_guard
from mysql_backend import ensure_schema, settings

TABLES = ('indicators', 'source_files', 'import_events', 'instruments', 'daily_bars',
          'indicator_daily', 'moneyflow_ind_dc', 'moneyflow_cnt_ths', 'moneyflow_ind_ths')


def layout(source, table):
    info = source.execute(f'PRAGMA table_info(`{table}`)').fetchall()
    columns = ','.join(f'`{row[1]}`' for row in info)
    primary = ','.join(f'`{row[1]}`' for row in sorted(info, key=lambda row: row[5]) if row[5])
    if not columns or not primary:
        raise ValueError(f'Missing source table or primary key: {table}')
    return columns, primary, len(info)


def verify(source, target):
    import pymysql
    counts = {}
    for table in TABLES:
        columns, primary, _ = layout(source, table)
        query = f'SELECT {columns} FROM `{table}` ORDER BY {primary}'
        # SQLite BINARY and MySQL utf8mb4_bin both preserve case and Unicode identity.
        count = 0
        with target.raw.cursor(pymysql.cursors.SSCursor) as cursor:
            cursor.execute(query)
            for index, (left, right) in enumerate(zip_longest(source.execute(query), cursor)):
                if left != right:
                    raise ValueError(f'Value mismatch in {table}, ordered row {index}; migration not verified')
                count += 1
        counts[table] = count
        print(f'Verified {table}: {count} rows', flush=True)
    return counts


def migrate(source_path, report_path, verify_only=False):
    import pymysql
    source_path = Path(source_path).resolve(strict=True)
    config = settings()
    database = config.pop('database')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,56}', database):
        raise ValueError('MYSQL_DATABASE must use 1–56 letters, digits or underscores')
    if not verify_only:
        with closing(pymysql.connect(**config, charset='utf8mb4', autocommit=True)) as admin:
            with admin.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
    with closing(sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)) as source:
        source.execute('BEGIN')  # Stable source snapshot throughout copy and verification.
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        if source.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite foreign key check failed')
        with connect('mysql') as target, writer_guard(target):
            if not verify_only:
                ensure_schema(target, FLOW_NUMBERS, FLOW_TEXT)
                populated = [table for table in TABLES if target.execute(
                    f'SELECT EXISTS(SELECT 1 FROM `{table}` LIMIT 1)').fetchone()[0]]
                if populated:
                    raise ValueError('Target already contains data; use --verify-only or a new database. '
                                     'No existing data overwritten: ' + ', '.join(populated))
                with target:
                    for table in TABLES:
                        columns, primary, size = layout(source, table)
                        rows = source.execute(f'SELECT {columns} FROM `{table}` ORDER BY {primary}')
                        sql = f"INSERT INTO `{table}`({columns}) VALUES({','.join('?' for _ in range(size))})"
                        count = 0
                        while batch := rows.fetchmany(100):
                            target.executemany(sql, batch)
                            count += len(batch)
                        print(f'Copied {table}: {count} rows', flush=True)
                    counts = verify(source, target)
            else:
                counts = verify(source, target)
    report = dict(source=str(source_path), database=database, tables=counts,
                  total_rows=sum(counts.values()), verified='Every column of every row matches, including archived bytes',
                  sqlite_retained=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_DATABASE)
    parser.add_argument('--report', type=Path, default=Path(__file__).parent / 'instance/mysql_migration_report.json')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    migrate(args.source, args.report, args.verify_only)
