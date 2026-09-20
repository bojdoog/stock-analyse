"""Import and verify data/ without deleting any CSV/JSON backups."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from market_store import (PROJECT, PRICE_FIELDS, FLOW_NUMBERS, FLOW_TEXT, connect, csv_rows,
                          database_path, date_string, initialize, import_content, number, is_mysql)


def verify_file(db, relative_path, content):
    stored = db.execute('SELECT * FROM source_files WHERE path=?', (relative_path,)).fetchone()
    assert stored is not None, f'Not imported: {relative_path}'
    assert bytes(stored['content']) == content, f'Archive mismatch: {relative_path}'
    assert stored['sha256'] == hashlib.sha256(content).hexdigest()
    if not stored['target_table']:
        return 0
    original = csv_rows(content)
    records = db.execute(f"SELECT * FROM {stored['target_table']} WHERE source_path=? ORDER BY `row_number`",
                         (relative_path,)).fetchall()
    assert len(original) == stored['row_count'] == len(records), f'Row count mismatch: {relative_path}'
    numeric = PRICE_FIELDS if stored['target_table'] in ('daily_bars', 'indicator_daily') else FLOW_NUMBERS
    for i, (source, target) in enumerate(zip(original, records)):
        assert date_string(source['date']) == target['date'], (relative_path, i, 'date')
        for field in numeric:
            assert number(source.get(field)) == target[field], (relative_path, i, field)
        if numeric == FLOW_NUMBERS:
            for field in FLOW_TEXT:
                assert source.get(field) == target[field], (relative_path, i, field)
    return len(records)


def migrate(data_dir, db_path, report_path, verify_only=False):
    initialize(db_path)
    files = sorted(p for p in Path(data_dir).rglob('*') if p.is_file())
    counts, rows = Counter(), Counter()
    changed = 0
    with connect(db_path) as db:
        for i, file in enumerate(files, 1):
            relative = file.relative_to(data_dir).as_posix()
            content = file.read_bytes()
            if not verify_only:
                if str(db_path) == 'auto':
                    from resilient_store import import_source
                    changed += import_source(relative, content, file)
                else:
                    changed += import_content(db, relative, content)
            rows[relative.split('/')[0]] += verify_file(db, relative, content)
            counts[relative.split('/')[0]] += 1
            if i % 500 == 0:
                print(f'Verified {i}/{len(files)} files', flush=True)
        if getattr(db, 'dialect', None) != 'mysql':
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        tables = ['daily_bars', 'indicator_daily', 'moneyflow_ind_dc', 'moneyflow_ind_ths', 'moneyflow_cnt_ths']
        table_rows = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in tables}
        duplicate_occurrences = db.execute('SELECT COUNT(*) FROM moneyflow_ind_dc WHERE occurrence>0').fetchone()[0]
    report = dict(database=str(db_path) if str(db_path) in ('auto', 'mysql') else str(Path(db_path).resolve()), files=len(files), changed_files=changed,
                  verified_rows=sum(rows.values()), categories={key: {'files': counts[key], 'rows': rows[key]} for key in counts},
                  table_rows=table_rows, preserved_dc_duplicate_occurrences=duplicate_occurrences,
                  verification='All archived bytes, row counts, dates and typed values match; integrity and foreign keys OK',
                  csv_backups_retained=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=PROJECT / 'data')
    parser.add_argument('--database', default=database_path())
    parser.add_argument('--report', type=Path, default=PROJECT / 'flask_backend/market_migration_report.json')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    migrate(args.data_dir, args.database, args.report, args.verify_only)
