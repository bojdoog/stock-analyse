"""Market storage shared by Flask, importers and standalone research scripts.

CSV/JSON bytes are also archived for lossless export and compatibility URLs.
Queries use typed tables, never the backup files on disk.
"""
import csv
import hashlib
import io
import json
import math
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT / 'flask_backend/instance/stock_analyse.sqlite3'
FLOW_TABLES = {kind: 'moneyflow_' + kind for kind in ('ind_dc', 'cnt_ths', 'ind_ths')}
PRICE_FIELDS = ('open', 'high', 'low', 'close', 'volume', 'amount')
AMV_EMA20_DESCRIPTION = (
    '基于90个同花顺行业的流通市值、换手率与指数收盘价，估算近期活跃交易对应的市值。\n'
    '公式：AMV(t) = 7.695442042177039 × Σᵢ[P(i,t) × Q(i,t)]。\n'
    '其中 M=行业流通市值float_mv÷10⁸（亿元），h=行业换手率turnover_rate÷100，'
    'P=行业指数收盘点位，q=M×h÷P（换手量代理值，不是真实股数）。\n'
    'Q=EMA20(q)：Q(t)=(2/21)×q(t)+(19/21)×Q(t−1)，首日Q=q；'
    '从2024-09-10初始化，span=20、adjust=False，并非20日简单平均。'
    '先逐行业平滑q，再乘当日P，最后汇总90个行业。\n'
    '7.695442042177039为训练期标定系数；输出沿用原AMV数值尺度，不确认单位为亿元。'
    '这是反推的替代公式，尚未证明为指南针原公式；独立续算不使用原AMV值，资金流数据未纳入公式。'
)


def amv_ema20_description(synthetic):
    return AMV_EMA20_DESCRIPTION + ('\n图表口径：close为公式估算值；open取前一交易日close（首日取自身close），'
        'high/low取open与close的最大/最小值；volume/amount取同日上证指数000001.SH（手/千元）。'
        '合成K线不代表真实盘中高低价。' if synthetic else '\n图表口径：仅有每日收盘估算值。')

FLOW_NUMBERS = ('pct_change', 'close', 'close_price', 'industry_index', 'company_num',
                'pct_change_stock', 'net_buy_amount', 'net_sell_amount', 'net_inflow',
                'net_amount_rate', 'super_large_inflow', 'large_inflow', 'rank')
FLOW_TEXT = ('ts_code', 'industry_name', 'lead_stock', 'etf_code', 'etf_name')


def database_path():
    target = os.environ.get('DATABASE_PATH', 'auto')
    return target if target in ('mysql', 'auto') else Path(target).resolve()


def is_mysql(path=None):
    return str(path or database_path()) == 'mysql'


def open_connection(path=None):
    if str(path or database_path()) == 'auto':
        from resilient_store import open_connection as automatic_connection
        return automatic_connection()
    if is_mysql(path):
        from mysql_backend import Connection
        return Connection()
    db = sqlite3.connect(str(path or database_path()), timeout=60)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


@contextmanager
def connect(path=None):
    db = open_connection(path)
    try:
        yield db
    finally:
        db.close()


def ensure_schema(db):
    if getattr(db, 'dialect', None) == 'mysql':
        from mysql_backend import ensure_schema as mysql_schema
        mysql_schema(db, FLOW_NUMBERS, FLOW_TEXT)
        seed_indicator(db)
        return
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE IF NOT EXISTS source_files (
            path TEXT PRIMARY KEY, category TEXT NOT NULL, sha256 TEXT NOT NULL,
            content BLOB NOT NULL, row_count INTEGER NOT NULL,
            min_date TEXT, max_date TEXT, target_table TEXT,
            imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE IF NOT EXISTS import_events (
            id INTEGER PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL,
            row_count INTEGER NOT NULL, imported_at TEXT NOT NULL
            DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE TABLE IF NOT EXISTS instruments (
            category TEXT NOT NULL, exchange TEXT NOT NULL, code TEXT NOT NULL,
            name TEXT NOT NULL, source_path TEXT NOT NULL UNIQUE REFERENCES source_files(path),
            PRIMARY KEY(category,exchange,code)
        );
        CREATE TABLE IF NOT EXISTS daily_bars (
            category TEXT NOT NULL, exchange TEXT NOT NULL, code TEXT NOT NULL,
            date TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL NOT NULL,
            volume REAL, amount REAL, source_path TEXT NOT NULL REFERENCES source_files(path),
            row_number INTEGER NOT NULL,
            PRIMARY KEY(category,exchange,code,date)
        );
        CREATE INDEX IF NOT EXISTS daily_bars_date ON daily_bars(date,category,code);
        CREATE INDEX IF NOT EXISTS daily_bars_source ON daily_bars(source_path);
        CREATE TABLE IF NOT EXISTS indicator_daily (
            indicator_id INTEGER NOT NULL REFERENCES indicators(id), date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL, amount REAL,
            source_path TEXT NOT NULL REFERENCES source_files(path), row_number INTEGER NOT NULL,
            PRIMARY KEY(indicator_id,date)
        );
        CREATE INDEX IF NOT EXISTS indicator_daily_source ON indicator_daily(source_path);
    ''')
    for table in FLOW_TABLES.values():
        fields = ','.join([f'{key} REAL' for key in FLOW_NUMBERS] + [f'{key} TEXT' for key in FLOW_TEXT])
        # Some upstream snapshots contain multiple records for a sector/date.
        # Preserve their occurrence rather than silently dropping data.
        db.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
            date TEXT NOT NULL, sector_key TEXT NOT NULL, occurrence INTEGER NOT NULL,
            {fields}, source_path TEXT NOT NULL REFERENCES source_files(path),
            row_number INTEGER NOT NULL, PRIMARY KEY(date,sector_key,occurrence))''')
        db.execute(f'CREATE INDEX IF NOT EXISTS {table}_source ON {table}(source_path)')
        db.execute(f'CREATE INDEX IF NOT EXISTS {table}_sector ON {table}(sector_key,date)')
    from intraday_store import ensure_schema as intraday_schema
    intraday_schema(db)
    seed_indicator(db)


def upsert(db, table, columns, keys, values, updates=(), timestamp=None):
    names = ','.join(f'`{name}`' for name in columns)
    sql = f"INSERT INTO {table}({names}) VALUES({','.join('?' for _ in columns)})"
    if getattr(db, 'dialect', None) == 'mysql':
        assignments = [f'`{name}`=VALUES(`{name}`)' for name in updates]
        if timestamp:
            assignments.append(f"`{timestamp}`=DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')")
        sql += ' ON DUPLICATE KEY UPDATE ' + ','.join(assignments or [f'`{keys[0]}`=`{keys[0]}`'])
    else:
        sql += f" ON CONFLICT({','.join(keys)}) DO "
        assignments = [f'{name}=excluded.{name}' for name in updates]
        if timestamp:
            assignments.append(f"{timestamp}=strftime('%Y-%m-%dT%H:%M:%SZ','now')")
        sql += 'UPDATE SET ' + ','.join(assignments) if assignments else 'NOTHING'
    return db.execute(sql, values)


def seed_indicator(db):
    upsert(db, 'indicators', ('code', 'name', 'source', 'description', 'is_default'), ('code',),
           ('0AMV', '活跃市值(默认)', '指南针',
            '指南针原始活跃市值指标，用于市场状态判断和资金跟随策略回测。', 1))
    db.commit()


def initialize(path=None):
    path = path or database_path()
    if str(path) == 'auto':
        from resilient_store import initialize as automatic_initialize
        return automatic_initialize()
    if not is_mysql(path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        ensure_schema(db)


def decode(content):
    for encoding in ('utf-8-sig', 'gbk'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError('Unsupported text encoding')


def csv_rows(content):
    reader = csv.DictReader(io.StringIO(decode(content)))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('CSV headers missing or duplicated')
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError('CSV row has more fields than its header')
    return rows


def number(value):
    if value is None or str(value).strip().lower() in ('', 'nan', 'none', 'null'):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'Non-finite number: {value}')
    return result


def date_string(value):
    value = str(value).strip()
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, '%Y%m%d').strftime('%Y-%m-%d')
    return datetime.strptime(value[:10], '%Y-%m-%d').strftime('%Y-%m-%d')


def instrument_identity(category, filename):
    code, _, name = Path(filename).stem.partition('_')
    exchange = ('BJ' if category == 'stock' and code.startswith(('4', '8', '92')) else
                'SH' if category == 'index' or code.startswith(('5', '6', '9')) else 'SZ')
    return category, exchange, code, name or code


@contextmanager
def writer_guard(db):
    """Serialize writers, including first inserts and the subsequent CSV export."""
    mysql = getattr(db, 'dialect', None) == 'mysql'
    if mysql:
        if db.execute("SELECT GET_LOCK(CONCAT('market:', DATABASE()),60)").fetchone()[0] != 1:
            raise TimeoutError('Timed out waiting for the market database writer')
    try:
        yield
    finally:
        if mysql:
            db.execute("SELECT RELEASE_LOCK(CONCAT('market:', DATABASE()))")


def import_content(db, relative_path, content, pending=False):
    with writer_guard(db):
        return _import_content(db, relative_path, content, pending)


def _import_content(db, relative_path, content, pending=False):
    """Atomically replace one changed source snapshot; identical imports are no-ops."""
    relative_path = Path(relative_path).as_posix()
    parts = relative_path.split('/')
    intraday = len(parts) == 3 and parts[:2] == ['core_index', '0AMV-intraday'] and parts[-1].endswith('.csv')
    if (len(parts) != 2 and not intraday) or '..' in parts:
        raise ValueError(f'Expected category/filename: {relative_path}')
    category, filename = ('indicator_intraday', parts[-1]) if intraday else parts
    digest = hashlib.sha256(content).hexdigest()
    previous = db.execute('SELECT sha256 FROM source_files WHERE path=?', (relative_path,)).fetchone()
    if previous and previous['sha256'] == digest:
        return False
    rows = csv_rows(content) if filename.endswith('.csv') else []
    table = None
    if filename.endswith('.csv'):
        if intraday:
            table = 'indicator_intraday'
        elif category in ('stock', 'etf', 'index'):
            table = 'daily_bars'
        elif category == 'core_index':
            table = 'indicator_daily'
        elif category in FLOW_TABLES.values():
            table = category
        else:
            raise ValueError(f'Unsupported data category: {category}')
    elif filename.endswith('.json'):
        json.loads(decode(content))
    else:
        raise ValueError(f'Unsupported source file: {relative_path}')
    dates = [date_string(row['date']) for row in rows]
    if intraday:
        from intraday_store import records as intraday_records
        snapshots = intraday_records(rows, filename)
    with db:
        upsert(db, 'source_files',
            ('path','category','sha256','content','row_count','min_date','max_date','target_table'), ('path',),
            (relative_path, category, digest, content, len(rows), min(dates) if dates else None,
             max(dates) if dates else None, table),
            ('sha256','content','row_count','min_date','max_date','target_table'), 'imported_at')
        if table:
            db.execute(f'DELETE FROM {table} WHERE source_path=?', (relative_path,))
        if table == 'indicator_intraday':
            indicator_id = db.execute('SELECT id FROM indicators WHERE code=?', ('0AMV',)).fetchone()[0]
            db.executemany('INSERT INTO indicator_intraday VALUES(?,?,?,?,?,?,?,?)',
                           [(indicator_id, *record, relative_path) for record in snapshots])
        elif table == 'daily_bars':
            cat, exchange, code, name = instrument_identity(category, filename)
            upsert(db, 'instruments', ('category','exchange','code','name','source_path'),
                   ('category','exchange','code'), (cat, exchange, code, name, relative_path),
                   ('name','source_path'))
            db.executemany('INSERT INTO daily_bars VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', [
                (cat, exchange, code, day, *(number(row.get(key)) for key in PRICE_FIELDS), relative_path, i)
                for i, (day, row) in enumerate(zip(dates, rows))])
        elif table == 'indicator_daily':
            if filename == '0AMV-2013-2026.csv':
                code = '0AMV'
            elif filename == 'candidate_amv_close.csv':
                code = 'AMV_EMA20'
                description = amv_ema20_description(
                    bool(rows) and all(row.get('open') not in (None, '') for row in rows))
                upsert(db, 'indicators', ('code','name','source','description'), ('code',),
                       (code, '活跃市值(反推EMA20)', '本地公式', description), ('description',), 'updated_at')
            else:
                raise ValueError(f'Indicator mapping not configured: {filename}')
            indicator_id = db.execute('SELECT id FROM indicators WHERE code=?', (code,)).fetchone()[0]
            db.executemany('INSERT INTO indicator_daily VALUES(?,?,?,?,?,?,?,?,?,?)', [
                (indicator_id, day, *(number(row.get(key)) for key in PRICE_FIELDS), relative_path, i)
                for i, (day, row) in enumerate(zip(dates, rows))])
        elif table in FLOW_TABLES.values():
            occurrences = Counter()
            records = []
            for i, (day, row) in enumerate(zip(dates, rows)):
                key = row.get('ts_code') or row.get('industry_name')
                if not key:
                    raise ValueError('Missing sector identifier')
                occurrence = occurrences[day, key]
                occurrences[day, key] += 1
                records.append((day, key, occurrence, *(number(row.get(k)) for k in FLOW_NUMBERS),
                                *(row.get(k) for k in FLOW_TEXT), relative_path, i))
            placeholders = ','.join('?' for _ in range(5 + len(FLOW_NUMBERS) + len(FLOW_TEXT)))
            db.executemany(f'INSERT INTO {table} VALUES({placeholders})', records)
        db.execute('INSERT INTO import_events(path,sha256,row_count) VALUES(?,?,?)',
                   (relative_path, digest, len(rows)))
        if pending:
            db.execute('INSERT OR REPLACE INTO mysql_pending(path) VALUES(?)', (relative_path,))
    return True


def file_content(relative_path, path=None):
    with connect(path) as db:
        row = db.execute('SELECT content FROM source_files WHERE path=?', (Path(relative_path).as_posix(),)).fetchone()
        return row[0] if row else None


def list_files(category, path=None):
    with connect(path) as db:
        return [row[0].split('/')[-1] for row in db.execute(
            "SELECT path FROM source_files WHERE category=? AND path LIKE '%.csv' ORDER BY path", (category,))]


def save_dataframe(frame, output_path, path=None, category=None, _pending=False):
    """Upsert fetched dates in the database, then refresh the optional CSV export.

    Each flow file is a complete daily snapshot (duplicate occurrences retained).
    Price fetches can be partial histories; dates outside the fetched range survive.
    """
    if str(path or database_path()) == 'auto':
        from resilient_store import save_dataframe as automatic_save
        return automatic_save(frame, output_path, category)
    output_path = Path(output_path)
    category = category or output_path.parent.name
    relative_path = f'{category}/{output_path.name}'
    initialize(path)
    content = frame.to_csv(index=False).encode('utf-8-sig')
    if category in ('stock', 'etf', 'index', 'core_index'):
        dates = [date_string(row['date']) for row in csv_rows(content)]
        if len(dates) != len(set(dates)):
            raise ValueError('Duplicate dates in fetched price data')
    with connect(path) as db, writer_guard(db):
        # Reserve the writer before reading/merging, so concurrent updates cannot be lost.
        db.execute('START TRANSACTION' if is_mysql(path) else 'BEGIN IMMEDIATE')
        previous = db.execute('SELECT content FROM source_files WHERE path=?', (relative_path,)).fetchone()
        if category in ('stock', 'etf', 'index', 'core_index') and previous:
            old, new = csv_rows(previous[0]), csv_rows(content)
            merged = {date_string(row['date']): row for row in old}
            merged.update({date_string(row['date']): row for row in new})
            columns = list(dict.fromkeys([*(old[0].keys() if old else []), *frame.columns]))
            buffer = io.StringIO(newline='')
            writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            writer.writerows(merged[day] for day in sorted(merged))
            content = buffer.getvalue().encode('utf-8-sig')
        import_content(db, relative_path, content, pending=_pending)
        db.commit()
        # Export the latest committed snapshot while holding the writer lock.
        # Otherwise a slower concurrent fetch could overwrite the backup with older data.
        db.execute('START TRANSACTION' if is_mysql(path) else 'BEGIN IMMEDIATE')
        content = db.execute('SELECT content FROM source_files WHERE path=?', (relative_path,)).fetchone()[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        db.commit()


def refresh_index(out_dir, path=None, category=None):
    if str(path or database_path()) == 'auto':
        from resilient_store import refresh_index as automatic_index
        return automatic_index(out_dir, category)
    out_dir = Path(out_dir)
    category = category or out_dir.name
    files = list_files(category, path)
    content = json.dumps(files, ensure_ascii=False).encode('utf-8')
    with connect(path) as db:
        import_content(db, f'{category}/index.json', content)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'index.json').write_bytes(content)
    return files
