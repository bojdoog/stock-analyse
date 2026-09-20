"""Bootstrap the SQLite mirror from a consistent MySQL snapshot, with verification."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from market_store import connect
from resilient_store import sqlite_path, local_initialize
from migrate_sqlite_to_mysql import TABLES, verify


def main():
    import pymysql
    local_initialize()
    target = sqlite_path()
    backup = target.with_name(target.stem + '.before_mirror_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.sqlite3')
    with connect(target) as local, connect('mysql') as remote:
        if local.execute('SELECT 1 FROM mysql_pending LIMIT 1').fetchone():
            raise RuntimeError('Pending offline data exists. Replay it before bootstrapping the mirror.')
        copy = sqlite3.connect(backup)
        try:
            local.backup(copy)
        finally:
            copy.close()
        remote.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        remote.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        local.execute('BEGIN IMMEDIATE')
        try:
            if local.execute('SELECT 1 FROM mysql_pending LIMIT 1').fetchone():
                raise RuntimeError('A concurrent writer queued data; aborting mirror bootstrap')
            for table in reversed(TABLES):
                local.execute(f'DELETE FROM `{table}`')
            for table in TABLES:
                with remote.raw.cursor(pymysql.cursors.SSCursor) as cursor:
                    cursor.execute(f'SELECT * FROM `{table}`')
                    columns = ','.join('`' + column[0] + '`' for column in cursor.description)
                    placeholders = ','.join('?' for _ in cursor.description)
                    count = 0
                    while batch := cursor.fetchmany(500):
                        local.executemany(f'INSERT INTO `{table}`({columns}) VALUES({placeholders})', batch)
                        count += len(batch)
                    print(f'Copied {table}: {count}', flush=True)
            # verify() expects plain tuples rather than sqlite3.Row.
            local.row_factory = None
            counts = verify(local, remote)
            assert not local.execute('PRAGMA foreign_key_check').fetchall()
            local.commit()
        except Exception:
            local.rollback()
            raise
    report = {'tables': counts, 'total_rows': sum(counts.values()), 'backup': str(backup),
              'verification': 'Every row and column matches MySQL, including archived file bytes'}
    (target.parent / 'sqlite_mirror_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
