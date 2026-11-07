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
import time
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
        CREATE INDEX IF NOT EXISTS daily_bars_code ON daily_bars(category,code,date);
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
    from etf_intraday import ensure_schema as etf_intraday_schema
    etf_intraday_schema(db)
    from etf_catalog import ensure_schema as catalog_schema
    catalog_schema(db)
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
    # 高频路径：直接切片拼接，避免每行都走 strptime（整轮抓取会调用上百万次）。
    if len(value) == 8 and value.isdigit():
        return f'{value[:4]}-{value[4:6]}-{value[6:]}'
    if len(value) >= 10 and value[4] == '-' and value[7] == '-':
        return value[:10]
    return datetime.strptime(value[:10], '%Y-%m-%d').strftime('%Y-%m-%d')


def exchange_for(category, code):
    """代码所属交易所；与导入时的 instrument_identity 保持一致。

    daily_bars 主键是 (category,exchange,code,date)，查询时带上 exchange
    才能命中主键前缀，否则 MySQL 会退化成大范围扫描。
    """
    if category == 'sw_index':
        return 'SI'
    return ('BJ' if category == 'stock' and code.startswith(('4', '8', '92')) else
            'SH' if category == 'index' or code.startswith(('5', '6', '9')) else 'SZ')


def instrument_identity(category, filename):
    code, _, name = Path(filename).stem.partition('_')
    if category == 'sw_index':
        return category, 'SI', code.removesuffix('.SI'), name or code
    return category, exchange_for(category, code), code, name or code


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


@contextmanager
def _transaction(db, commit=True):
    """commit=False 时复用外层事务，让批量入库只提交一次。"""
    if commit:
        with db:
            yield
    else:
        yield


def _chunks(items, size=400):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def import_content(db, relative_path, content, pending=False, commit=True, previous=None, previous_rows=None):
    with writer_guard(db):
        return _import_content(db, relative_path, content, pending, commit, previous, previous_rows)


def _import_content(db, relative_path, content, pending=False, commit=True, previous=None, previous_rows=None):
    """Atomically replace one changed source snapshot; identical imports are no-ops.

    previous / previous_rows 由调用方传入已有的旧快照（及其解析结果），避免重复读库与解析。
    """
    relative_path = Path(relative_path).as_posix()
    parts = relative_path.split('/')
    intraday = len(parts) == 3 and parts[:2] == ['core_index', '0AMV-intraday'] and parts[-1].endswith('.csv')
    if (len(parts) != 2 and not intraday) or '..' in parts:
        raise ValueError(f'Expected category/filename: {relative_path}')
    category, filename = ('indicator_intraday', parts[-1]) if intraday else parts
    digest = hashlib.sha256(content).hexdigest()
    if previous is None:
        previous = db.execute('SELECT sha256, content FROM source_files WHERE path=?',
                              (relative_path,)).fetchone()
    if previous and previous['sha256'] == digest:
        return False
    rows = csv_rows(content) if filename.endswith('.csv') else []
    table = None
    if filename.endswith('.csv'):
        if intraday:
            table = 'indicator_intraday'
        elif category in ('stock', 'etf', 'index', 'sw_index', 'etf_hj'):
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
    with _transaction(db, commit):
        if relative_path == 'catalog/etfs.json':
            from etf_catalog import apply_snapshot
            apply_snapshot(db, json.loads(decode(content)))
        upsert(db, 'source_files',
            ('path','category','sha256','content','row_count','min_date','max_date','target_table'), ('path',),
            (relative_path, category, digest, content, len(rows), min(dates) if dates else None,
             max(dates) if dates else None, table),
            ('sha256','content','row_count','min_date','max_date','target_table'), 'imported_at')
        if table and table != 'daily_bars':
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
            # 只重写本次变化/新增/删除的日期，避免把整段历史（数千行）删掉再插回。
            changed_days = set(dates)
            removed_days = []
            if previous is not None:
                old_by_day = {date_string(row['date']): row
                              for row in (previous_rows or csv_rows(previous['content']))}
                new_by_day = dict(zip(dates, rows))
                changed_days = {day for day, row in new_by_day.items() if old_by_day.get(day) != row}
                removed_days = [day for day in old_by_day if day not in new_by_day]
            days = sorted(changed_days | set(removed_days))
            for chunk in _chunks(days):
                placeholders = ','.join('?' for _ in chunk)
                db.execute(f'DELETE FROM daily_bars WHERE source_path=? AND date IN ({placeholders})',
                           (relative_path, *chunk))
            insert_rows = [
                (cat, exchange, code, day, *(number(row.get(key)) for key in PRICE_FIELDS), relative_path, i)
                for i, (day, row) in enumerate(zip(dates, rows)) if day in changed_days]
            if insert_rows:
                db.executemany('INSERT INTO daily_bars VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', insert_rows)
        elif table == 'indicator_daily':
            if filename == '0AMV-2013-2026.csv':
                code = '0AMV'
            elif filename == 'candidate_amv_close.csv':
                code = 'AMV_EMA20'
                description = amv_ema20_description(
                    bool(rows) and all(row.get('open') not in (None, '') for row in rows))
                upsert(db, 'indicators', ('code','name','source','description'), ('code',),
                       (code, '活跃市值(THS反推EMA20)', '本地公式', description), ('name','description'), 'updated_at')
            elif filename == 'candidate_amv_log_memory_close.csv':
                code = 'AMV_THS_LOG_MEMORY'
                description = (
                    '基于90个THS行业的对数成交记忆研究模型。M=Σ行业流通市值/10⁸，'
                    'A=Σ(行业流通市值/10⁸×换手率/100)，H90/H120/H250为A的90/120/250交易日简单均值。'
                    'Z(X)=(ln(X)-训练均值)/训练标准差。'
                    '估算收盘=exp(12.081280012936546+0.014788830094259063×Z(M)'
                    '+0.012871150784723276×Z(A)-0.03857201780319821×Z(H90)'
                    '-0.048533873581396686×Z(H120)+0.012525385797847465×Z(H250))。'
                    '标准化参数保存于amv_log_memory/model.json；参数在2025-09-19至2025-12-31拟合并固定。'
                    '使用满250日历史后输出，不使用自由流通市值；这是截图思路的板块近似版，不是其原公式。'
                    '2026年历史检验弱于THS EMA20，仅作为研究对照。'
                    '日K为合成：开盘取前收（首日取自身），高低取两者极值，不代表盘中高低。'
                    '成交量/额借用同日上证指数000001.SH（手/千元），并非指标自身成交。')
                upsert(db, 'indicators', ('code','name','source','description'), ('code',),
                       (code, '活跃市值(THS对数成交记忆)', '本地研究公式', description),
                       ('name','source','description'), 'updated_at')
            elif filename == 'candidate_amv_flow40_close.csv':
                code = 'AMV_EMA20_FLOW40'
                description = (
                    '以活跃市值(THS反推EMA20)为基础，加入主力净流入净占比的40日指数平滑修正。\n'
                    '公式：新值=旧EMA20反推值×exp(0.01703745581667001×Z)，'
                    'Z=(EMA40(net_amount_rate)+2.163271807211645)/0.35290158113635006。'
                    'net_amount_rate使用东方财富大盘资金流接口返回的百分数数值；'
                    'EMA从2024-09-10初始化，adjust=False。\n'
                    '参数在2024-12-10至2025-06-30拟合，2025年下半年选择模型；'
                    '独立计算不使用原AMV值。该版本改善数值拟合，但未证明为原始公式，'
                    '也未证明择时效果更好。\n'
                    '依赖盘后行业与资金流数据，不能作为盘中实时指标。'
                )
                synthetic = bool(rows) and all(row.get('open') not in (None, '') for row in rows)
                description += (
                    '\n图表口径：close为公式估算值；open取前一交易日close（首日取自身close），'
                    'high/low取open与close的最大/最小值；volume/amount取同日上证指数000001.SH（手/千元）。'
                    '合成K线不代表真实盘中高低价。' if synthetic else '\n图表口径：仅有每日收盘估算值。'
                )
                upsert(db, 'indicators', ('code','name','source','description'), ('code',),
                       (code, '活跃市值(THS反推EMA20＋资金流修正)', '本地研究公式', description),
                       ('name','source','description'), 'updated_at')
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
        return available_files(db, category)


def available_files(db, category):
    if category == 'etf':
        rows = db.execute('''SELECT c.source_path FROM etf_catalog c
            JOIN source_files f ON f.path=c.source_path WHERE c.enabled=1 ORDER BY c.sort_order,c.code''')
    else:
        rows = db.execute("SELECT path FROM source_files WHERE category=? AND path LIKE '%.csv' ORDER BY path", (category,))
    return [row[0].split('/')[-1] for row in rows]


def save_dataframe(frame, output_path, path=None, category=None, _pending=False):
    """Upsert fetched dates in the database, then refresh the optional CSV export.

    Each flow file is a complete daily snapshot (duplicate occurrences retained).
    Price fetches can be partial histories; dates outside the fetched range survive.
    """
    if str(path or database_path()) == 'auto':
        from resilient_store import save_dataframe as automatic_save
        return automatic_save(frame, output_path, category)
    initialize(path)
    with connect(path) as db:
        _save_frame(db, frame, output_path, category, _pending)


def save_frames(frames, path=None, category=None, _pending=False, progress=None):
    """批量入库：整批共用一个事务，逐只保存后再统一导出备份文件。

    frames 为 (CSV 路径, frame) 的可迭代对象；progress(已处理数) 用于回显进度。
    """
    if str(path or database_path()) == 'auto':
        from resilient_store import save_frames as automatic_save
        return automatic_save(frames, category, progress)
    initialize(path)
    count = 0
    exports = []

    def begin():
        db.execute('START TRANSACTION' if getattr(db, 'dialect', None) == 'mysql' else 'BEGIN IMMEDIATE')

    with connect(path) as db:
        begin()
        try:
            for output_path, frame in frames:
                cat = category or Path(output_path).parent.name
                relative_path = f'{cat}/{Path(output_path).name}'
                _save_frame(db, frame, output_path, cat, _pending, batch=True)
                exports.append((Path(output_path), relative_path))
                count += 1
                if progress:
                    progress(count)
                # 分段提交：兼顾速度（不再每只提交）与中断/取消时已入库的数据不丢。
                if count % 200 == 0:
                    db.commit()
                    begin()
            db.commit()
        except Exception:
            db.rollback()
            raise
        # 事务提交后再落盘，保证导出的始终是已提交的快照。
        for output_path, relative_path in exports:
            content = db.execute('SELECT content FROM source_files WHERE path=?',
                                 (relative_path,)).fetchone()[0]
            export_file(output_path, content)
    return count


def _save_frame(db, frame, output_path, category, pending=False, batch=False):
    mysql = getattr(db, 'dialect', None) == 'mysql'
    output_path = Path(output_path)
    relative_path = f'{category}/{output_path.name}'
    content = frame.to_csv(index=False).encode('utf-8-sig')
    if category in ('stock', 'etf', 'index', 'sw_index', 'core_index', 'etf_hj'):
        dates = [date_string(row['date']) for row in csv_rows(content)]
        if len(dates) != len(set(dates)):
            raise ValueError('Duplicate dates in fetched price data')
    with writer_guard(db):
        # Reserve the writer before reading/merging, so concurrent updates cannot be lost.
        if not batch:
            db.execute('START TRANSACTION' if mysql else 'BEGIN IMMEDIATE')
        previous = db.execute('SELECT sha256, content FROM source_files WHERE path=?', (relative_path,)).fetchone()
        old_rows = None
        if category in ('stock', 'etf', 'index', 'sw_index', 'core_index', 'etf_hj') and previous:
            old, new = csv_rows(previous['content']), csv_rows(content)
            old_rows = old
            merged = {date_string(row['date']): row for row in old}
            merged.update({date_string(row['date']): row for row in new})
            columns = list(dict.fromkeys([*(old[0].keys() if old else []), *frame.columns]))
            buffer = io.StringIO(newline='')
            writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            writer.writerows(merged[day] for day in sorted(merged))
            content = buffer.getvalue().encode('utf-8-sig')
        # 批量模式下不提交，由 save_frames 在整批结束时统一 commit。
        import_content(db, relative_path, content, pending=pending, commit=not batch,
                       previous=previous, previous_rows=old_rows)
        if batch:
            return content
        db.commit()
        # Export the latest committed snapshot while holding the writer lock.
        # Otherwise a slower concurrent fetch could overwrite the backup with older data.
        db.execute('START TRANSACTION' if mysql else 'BEGIN IMMEDIATE')
        content = db.execute('SELECT content FROM source_files WHERE path=?', (relative_path,)).fetchone()[0]
        export_file(output_path, content)
        db.commit()


def export_file(output_path, content, attempts=8, delay=0.5):
    """Write a backup export, retrying transient Windows file locks.

    Indexers and antivirus hooks briefly memory-map these files, which makes
    an in-place rewrite or replace fail with EINVAL/1224. The committed
    database copy is authoritative, so retry with backoff and fall back to
    writing a temporary file and renaming it over the destination.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.name + '.exporting')
    last = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay * attempt)
        try:
            output_path.write_bytes(content)
            temp.unlink(missing_ok=True)
            return
        except OSError as exc:
            last = exc
        try:
            temp.write_bytes(content)
            os.replace(temp, output_path)
            return
        except OSError as exc:
            last = exc
    temp.unlink(missing_ok=True)
    raise last


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
    export_file(out_dir / 'index.json', content)
    return files
