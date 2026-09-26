"""Import daily Compass intraday CSVs to SQLite and MySQL; verify every value."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_backend'))
from market_store import connect, csv_rows, import_content, initialize
from intraday_store import records
from resilient_store import local_initialize, replay, sqlite_path


def main():
    folder = ROOT / 'data/core_index/0AMV-intraday'
    sources = []
    for path in sorted(folder.glob('*.csv')):
        content = path.read_bytes()
        expected = records(csv_rows(content), path.name)
        sources.append((path.relative_to(ROOT / 'data').as_posix(), content, expected))
    if not sources:
        raise ValueError('No intraday CSV files')
    print(f'Validated {len(sources)} CSV files', flush=True)
    local_initialize()
    initialize('mysql')
    with connect(sqlite_path()) as local:
        changed = 0
        for index, (path, content, _) in enumerate(sources, 1):
            local.execute('BEGIN IMMEDIATE')
            changed += import_content(local, path, content, pending=True)
            local.commit()
            if index % 200 == 0:
                print(f'SQLite: {index}/{len(sources)} files', flush=True)
    print(f'SQLite committed; changed files={changed}. Replaying pending data to MySQL.', flush=True)
    with connect('mysql') as remote:
        replay(remote)
    results = {}
    for target in (sqlite_path(), 'mysql'):
        count = 0
        with connect(target) as db:
            for path, content, expected in sources:
                archived = db.execute('SELECT content,sha256 FROM source_files WHERE path=?', (path,)).fetchone()
                if archived[0] != content or archived[1] != hashlib.sha256(content).hexdigest():
                    raise ValueError(f'Archive mismatch: {target}: {path}')
                actual = db.execute('''SELECT date,time,amv,volume_candidate,amount_candidate,source_file
                    FROM indicator_intraday WHERE indicator_id=(SELECT id FROM indicators WHERE code=?)
                    AND date=? ORDER BY time''', ('0AMV', expected[0][0])).fetchall()
                if [tuple(row[i] for i in range(6)) for row in actual] != expected:
                    raise ValueError(f'Intraday values mismatch: {target}: {path}')
                count += len(actual)
            results[str(target)] = {'verified_files': len(sources), 'verified_rows': count}
            print(f'Verified {target}: {count} rows and all archived CSV bytes', flush=True)
    report = {'databases': results, 'first_date': sources[0][2][0][0],
              'last_date': sources[-1][2][0][0], 'table': 'indicator_intraday'}
    (folder / 'database_import_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
