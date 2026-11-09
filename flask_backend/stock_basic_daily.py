"""个股每日指标（Tushare daily_basic）：市值、股本、估值、换手率、量比。

同一张表里也保存个股基础信息（名称、地区、行业），取代本地 stocklist.csv：
抓取脚本的股票池与页面个股信息都从这里读取。
数据由 fetch_data/fetch_daily_basic.py 写入。
"""
import datetime as dt

TABLE = 'stock_daily_basic'
COLUMNS = ('date', 'code', 'close', 'turnover_rate', 'pe_ttm', 'pb',
           'total_mv', 'circ_mv', 'float_share', 'volume_ratio',
           'name', 'area', 'industry')
NUMBERS = COLUMNS[2:10]
TEXT_COLUMNS = ('name', 'area', 'industry')


def _column_names(db):
    if getattr(db, 'dialect', None) == 'mysql':
        rows = db.execute(
            'SELECT COLUMN_NAME AS name FROM information_schema.columns'
            ' WHERE table_schema=DATABASE() AND table_name=?', (TABLE,))
    else:
        rows = db.execute(f'PRAGMA table_info({TABLE})')
    return {row['name'] for row in rows}


def ensure_schema(db):
    mysql = getattr(db, 'dialect', None) == 'mysql'
    # 以 (code,date) 为主键：单只股票按日期取最近一条是最常见查询。
    db.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        code VARCHAR(12) NOT NULL, date VARCHAR(10) NOT NULL,
        close DOUBLE, turnover_rate DOUBLE, pe_ttm DOUBLE, pb DOUBLE,
        total_mv DOUBLE, circ_mv DOUBLE, float_share DOUBLE, volume_ratio DOUBLE,
        name VARCHAR(32), area VARCHAR(16), industry VARCHAR(32),
        PRIMARY KEY(code,date))''' +
        (' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin' if mysql else ''))
    # 老表补上后加的基础信息列。
    existing = _column_names(db)
    for column in TEXT_COLUMNS:
        if column not in existing:
            db.execute(f'ALTER TABLE {TABLE} ADD COLUMN {column} VARCHAR(32)')
    # 按日期取最新交易日/区间过滤都很频繁，单列索引避免全表扫描。
    if not _has_index(db, 'stock_daily_basic_date'):
        db.execute(f'CREATE INDEX stock_daily_basic_date ON {TABLE}(date)')
    db.commit()


def _has_index(db, name):
    if getattr(db, 'dialect', None) == 'mysql':
        rows = db.execute('SELECT INDEX_NAME AS name FROM information_schema.statistics'
                          ' WHERE table_schema=DATABASE() AND table_name=? AND index_name=?',
                          (TABLE, name))
    else:
        rows = db.execute(f'PRAGMA index_list({TABLE})')
    return any(row['name'] == name for row in rows)


def save_rows(db, rows, chunk=90):
    """批量写入每日指标，rows 为 COLUMNS 顺序的元组；主键相同则覆盖。"""
    rows = list(rows)
    if not rows:
        return 0
    ensure_schema(db)
    names = ','.join(COLUMNS)
    marks = '(' + ','.join('?' for _ in COLUMNS) + ')'
    if getattr(db, 'dialect', None) == 'mysql':
        tail = ' ON DUPLICATE KEY UPDATE ' + ','.join(f'{name}=VALUES({name})' for name in NUMBERS + TEXT_COLUMNS)
    else:
        tail = ' ON CONFLICT(code,date) DO UPDATE SET ' + ','.join(f'{name}=excluded.{name}' for name in NUMBERS + TEXT_COLUMNS)
    for start in range(0, len(rows), chunk):
        part = rows[start:start + chunk]
        # 多行 VALUES 用单次 execute：pymysql 的 executemany 只支持单行模板。
        values = [value for row in part for value in row]
        db.execute(f'INSERT INTO {TABLE}({names}) VALUES {",".join(marks for _ in part)}{tail}', values)
    db.commit()
    return len(rows)


def existing_dates(db, start, end):
    """已入库的交易日集合，供抓取脚本跳过重复日期。"""
    ensure_schema(db)
    return {row['date'] for row in db.execute(
        f'SELECT DISTINCT date FROM {TABLE} WHERE date BETWEEN ? AND ?', (start, end))}


def pool(db, days=120):
    """股票池：近 days 天出现过的个股，含停牌股、排除早已退市的代码。"""
    ensure_schema(db)
    latest = db.execute(f'SELECT MAX(date) AS date FROM {TABLE}').fetchone()['date']
    if not latest:
        return []
    threshold = (dt.date.fromisoformat(latest) - dt.timedelta(days=days)).isoformat()
    return [dict(row) for row in db.execute(
        f'SELECT code, MAX(name) AS name, MAX(industry) AS industry FROM {TABLE}'
        ' WHERE date>=? GROUP BY code ORDER BY code', (threshold,))]


def latest(db, code, date=None):
    """该股票不晚于指定日期的最新一条指标；无数据返回 None。"""
    ensure_schema(db)
    sql = f'SELECT {",".join(COLUMNS)} FROM {TABLE} WHERE code=?'
    args = [code]
    if date:
        sql += ' AND date<=?'
        args.append(date)
    row = db.execute(sql + ' ORDER BY date DESC LIMIT 1', tuple(args)).fetchone()
    return dict(row) if row else None
