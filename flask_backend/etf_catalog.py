"""One database registry for ETF selection, downloads and sector mappings.

Catalog edits are archived through the existing SQLite -> MySQL durable queue.
Price imports never enable or register an ETF implicitly.
"""
import argparse
import json
import re
from pathlib import Path

CATALOG_PATH = 'catalog/etfs.json'


def ensure_schema(db):
    suffix = ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin' if getattr(db, 'dialect', None) == 'mysql' else ''
    db.execute('''CREATE TABLE IF NOT EXISTS etf_catalog (
        code VARCHAR(6) PRIMARY KEY, exchange VARCHAR(2) NOT NULL,
        name VARCHAR(191) NOT NULL, source_path VARCHAR(512) NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
        sort_order INTEGER NOT NULL DEFAULT 0)''' + suffix)
    db.execute('''CREATE TABLE IF NOT EXISTS etf_sector_mapping (
        flow_type VARCHAR(16) NOT NULL, sector_name VARCHAR(191) NOT NULL,
        etf_code VARCHAR(6) NOT NULL,
        PRIMARY KEY(flow_type,sector_name),
        FOREIGN KEY(etf_code) REFERENCES etf_catalog(code))''' + suffix)


def validate(payload):
    items, mappings = payload['etfs'], payload['mappings']
    codes, names, paths, keys = set(), set(), set(), set()
    for item in items:
        code, name, path = item['code'], item['name'], item['source_path']
        if not re.fullmatch(r'\d{6}', code) or code in codes or item['exchange'] not in ('SH', 'SZ'):
            raise ValueError('Invalid/duplicate ETF code or exchange')
        if not isinstance(name, str) or not name.strip() or len(name) > 191:
            raise ValueError('Invalid ETF name')
        if not isinstance(path, str) or not path.startswith(f'etf/{code}_') or not path.endswith('.csv') or '/' in path[4:] or '\\' in path or '..' in path or path in paths:
            raise ValueError('Invalid/duplicate ETF source path')
        if item['enabled'] not in (0, 1) or not isinstance(item['sort_order'], int):
            raise ValueError('Invalid ETF enabled/order value')
        if item['enabled'] and name in names:
            raise ValueError('Enabled ETFs must have distinct names for existing backtests')
        codes.add(code)
        paths.add(path)
        if item['enabled']:
            names.add(name)
    for mapping in mappings:
        key = (mapping['flow_type'], mapping['sector_name'])
        if key[0] not in ('ind_dc', 'ind_ths', 'cnt_ths') or not key[1] or len(key[1]) > 191 or key in keys or mapping['etf_code'] not in codes:
            raise ValueError('Invalid/duplicate ETF sector mapping')
        keys.add(key)
    return payload


def apply_snapshot(db, payload):
    from market_store import upsert
    validate(payload)
    # Missing rows become inactive, so old data can never silently re-enter selection.
    db.execute('DELETE FROM etf_sector_mapping')
    db.execute('UPDATE etf_catalog SET enabled=0')
    columns = ('code', 'exchange', 'name', 'source_path', 'enabled', 'sort_order')
    for item in payload['etfs']:
        upsert(db, 'etf_catalog', columns, ('code',), tuple(item[k] for k in columns), columns[1:])
    db.executemany('INSERT INTO etf_sector_mapping(flow_type,sector_name,etf_code) VALUES(?,?,?)',
                   [(m['flow_type'], m['sector_name'], m['etf_code']) for m in payload['mappings']])


def list_etfs(path=None, include_disabled=False):
    from market_store import connect
    with connect(path) as db:
        rows = [dict(row) for row in db.execute('SELECT * FROM etf_catalog ' +
            ('' if include_disabled else 'WHERE enabled=1 ') + 'ORDER BY sort_order,code')]
    return [dict(row, ts_code=f"{row['code']}.{row['exchange']}", file=row['source_path']) for row in rows]


def sector_mapping(flow_type, path=None):
    from market_store import connect
    with connect(path) as db:
        return {row['sector_name']: {'code': row['code'], 'name': row['name']} for row in db.execute(
            '''SELECT m.sector_name,c.code,c.name FROM etf_sector_mapping m
               JOIN etf_catalog c ON c.code=m.etf_code
               WHERE m.flow_type=? AND c.enabled=1''', (flow_type,))}


def snapshot(path=None):
    from market_store import connect
    with connect(path) as db:
        return {'etfs': [dict(r) for r in db.execute('SELECT * FROM etf_catalog ORDER BY sort_order,code')],
                'mappings': [dict(r) for r in db.execute('SELECT * FROM etf_sector_mapping ORDER BY flow_type,sector_name')]}


def save(payload, path=None):
    from market_store import connect, database_path, import_content, initialize
    validate(payload)
    path = path or database_path()
    initialize(path)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    if str(path) == 'auto':
        from resilient_store import import_source
        import_source(CATALOG_PATH, content)
    else:
        with connect(path) as db:
            import_content(db, CATALOG_PATH, content)


def main():
    from market_store import initialize, file_content
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--bootstrap', action='store_true')
    action.add_argument('--export', type=Path)
    action.add_argument('--import-file', type=Path)
    action.add_argument('--disable', nargs='+')
    action.add_argument('--enable', nargs='+')
    parser.add_argument('--database', default=None)
    args = parser.parse_args()
    initialize(args.database)
    if args.bootstrap:
        if file_content(CATALOG_PATH, args.database) is None:
            save(json.loads((Path(__file__).parent / 'migrations/etf_catalog_initial.json').read_text(encoding='utf-8')), args.database)
    elif args.export:
        args.export.write_text(json.dumps(snapshot(args.database), ensure_ascii=False, indent=2), encoding='utf-8')
    elif args.import_file:
        save(json.loads(args.import_file.read_text(encoding='utf-8-sig')), args.database)
    else:
        payload = snapshot(args.database)
        codes = set(args.disable or args.enable)
        if codes - {item['code'] for item in payload['etfs']}:
            raise ValueError('Unknown ETF code')
        for item in payload['etfs']:
            if item['code'] in codes:
                item['enabled'] = int(bool(args.enable))
        save(payload, args.database)
    print(f"Enabled ETFs: {len(list_etfs(args.database))}")


if __name__ == '__main__':
    main()
