"""B1 选股：把 StockTradebyZ 的 BBIKDJSelector 规则迁移到本地库。

规则（与原 Selector.py 保持一致）：
  1. 当日过滤：|涨跌幅| < 4%，振幅（H-L)/L < 8%；
  2. 最近 120 根收盘价波动 (high/low - 1) <= 100%；
  3. KDJ：J < 15，或 J <= 最近 120 根 J 的 10% 分位；
  4. 收盘 >= MA60，且最近 120 根内存在有效上穿 MA60；
  5. MACD：DIF > 0；
  6. 知行约束：收盘 > 知行多空线，且知行短期趋势线 > 知行多空线。
原代码里 BBI 上升判断被注释掉，这里同样不启用。

计算全部用纯 Python，避免 Flask 运行环境额外依赖 numpy/pandas。
"""
import math
import time

PARAMS = {
    'j_threshold': 15.0,
    'j_q_threshold': 0.10,
    'max_window': 120,
    'price_range_pct': 1.0,
    'pct_limit': 0.04,
    'amp_limit': 0.08,
    'm1': 14,
    'm2': 28,
    'm3': 57,
    'm4': 114,
}
BARS = PARAMS['max_window'] + 20


def _ensure_schema(db):
    mysql = getattr(db, 'dialect', None) == 'mysql'
    # 每次选股的结果连同当时的条件一起存，同一天再次选股会整体覆盖。
    db.execute('''CREATE TABLE IF NOT EXISTS b1_results (
        date VARCHAR(10) NOT NULL, code VARCHAR(12) NOT NULL, close DOUBLE, change_pct DOUBLE,
        j_value DOUBLE, volume DOUBLE, j_threshold DOUBLE, boards VARCHAR(32), created_at VARCHAR(20),
        PRIMARY KEY(date,code))''' +
        (' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin' if mysql else ''))


def ema(values, span):
    """通达信 EMA(X,N)：等价于 pandas ewm(span=N, adjust=False)。"""
    k = 2 / (span + 1)
    result, previous = [], values[0]
    for index, value in enumerate(values):
        previous = value if index == 0 else previous + k * (value - previous)
        result.append(previous)
    return result


def rolling_mean(values, window, min_periods=None):
    """滚动均值，样本不足 min_periods 时返回 None。"""
    min_periods = window if min_periods is None else min_periods
    result, total = [], 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        result.append(total / window if index >= min_periods - 1 else None)
    return result


def kdj_j(highs, lows, closes, n=9):
    """通达信 KDJ 的 J 值（K/D 初值 50）。"""
    js, k, d = [], 50.0, 50.0
    for index, close in enumerate(closes):
        start = max(0, index - n + 1)
        low_n = min(lows[start:index + 1])
        high_n = max(highs[start:index + 1])
        rsv = (close - low_n) / (high_n - low_n + 1e-9) * 100
        if index == 0:
            k = d = 50.0
        else:
            k = 2 / 3 * k + 1 / 3 * rsv
            d = 2 / 3 * d + 1 / 3 * k
        js.append(3 * k - 2 * d)
    return js


def quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    lower, upper = int(math.floor(position)), int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def zx_lines(closes):
    """知行短期趋势线 EMA(EMA(C,10),10) 与知行多空线 (MA14+MA28+MA57+MA114)/4。"""
    short = ema(ema(closes, 10), 10)
    parts = [rolling_mean(closes, window) for window in
             (PARAMS['m1'], PARAMS['m2'], PARAMS['m3'], PARAMS['m4'])]
    long_line = [None if None in (p[i] for p in parts) else sum(p[i] for p in parts) / 4
                 for i in range(len(closes))]
    return short, long_line


def passes_day_constraints(highs, lows, closes):
    if len(closes) < 2:
        return False
    previous, close = closes[-2], closes[-1]
    if previous <= 0 or lows[-1] <= 0:
        return False
    pct = abs(close / previous - 1.0)
    amplitude = (highs[-1] - lows[-1]) / lows[-1]
    return pct < PARAMS['pct_limit'] and amplitude < PARAMS['amp_limit']


def last_cross_up(close, ma):
    """最近 120 根内「前一日收盘 < MA、当日收盘 >= MA」的位置。"""
    start = max(1, len(close) - PARAMS['max_window'])
    for i in range(len(close) - 1, start - 1, -1):
        a, b, c, d = close[i - 1], close[i], ma[i - 1], ma[i]
        if None not in (a, c, d) and a < c and b >= d:
            return i
    return None


def _board_of(code):
    """按代码前缀识别板块：gem=创业板(300/301) star=科创板(688)。"""
    code = str(code)
    if code.startswith(('300', '301')):
        return 'gem'
    if code.startswith('688'):
        return 'star'
    return None


def passes(highs, lows, closes, j_threshold=PARAMS['j_threshold']):
    window = PARAMS['max_window']
    if len(closes) < BARS or not passes_day_constraints(highs, lows, closes):
        return False

    segment = closes[-window:]
    low, high = min(segment), max(segment)
    if low <= 0 or high / low - 1 > PARAMS['price_range_pct']:
        return False

    js = kdj_j(highs, lows, closes)
    j_window = [value for value in js[-window:] if value is not None]
    if not j_window:
        return False
    j_today = js[-1]
    if not (j_today < j_threshold or j_today <= quantile(j_window, PARAMS['j_q_threshold'])):
        return False

    ma60 = rolling_mean(closes, 60, min_periods=1)
    if closes[-1] < ma60[-1]:
        return False
    if last_cross_up(closes, ma60) is None:
        return False

    dif = [fast - slow for fast, slow in zip(ema(closes, 12), ema(closes, 26))]
    if dif[-1] <= 0:
        return False

    short, long_line = zx_lines(closes)
    long_value = long_line[-1]
    if long_value is None or not math.isfinite(long_value) or not math.isfinite(short[-1]):
        return False
    return closes[-1] > long_value and short[-1] > long_value


def _load_bars(db, date):
    """一次取每只股票最近 BARS 根日线（date 及以前），按代码分组。"""
    rows = db.execute('''SELECT code, date, open, high, low, close, volume FROM (
            SELECT code, date, open, high, low, close, volume,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
            FROM daily_bars WHERE category='stock' AND date<=?) t
        WHERE rn<=? ORDER BY code, date''', (date, BARS)).fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row[0], []).append((row[1], float(row[2] or 0), float(row[3] or 0),
                                               float(row[4] or 0), float(row[5] or 0), row[6]))
    return grouped


def compute(db, date, progress=None, exclude_boards=None, j_threshold=None):
    """按 B1 规则筛出 date 当天的个股，返回 [{code, close, change_pct, j_value, volume}]。

    progress(percent, message) 用于页面控制台回显进度，可为 None。
    exclude_boards 可传 {'gem','star'}，用于跳过创业板/科创板；j_threshold 为 KDJ 的 J 上限。
    """
    exclude_boards = set(exclude_boards or [])
    j_threshold = PARAMS['j_threshold'] if j_threshold is None else float(j_threshold)
    if progress:
        progress(1, '正在从库里载入全部个股日线…')
    bars_by_code = _load_bars(db, date)
    if exclude_boards:
        bars_by_code = {code: bars for code, bars in bars_by_code.items()
                        if _board_of(code) not in exclude_boards}
    total = len(bars_by_code)
    if progress:
        progress(2, f'已载入 {total} 只股票的日线，开始逐只计算')
    picks = []
    step = max(1, total // 20)
    for index, (code, bars) in enumerate(bars_by_code.items(), start=1):
        if progress and index % step == 0:
            # 只推进底部进度条，不逐批打印日志，避免控制台刷屏。
            progress(5 + 85 * index / max(total, 1), '')
        if bars[-1][0] != date:
            continue
        highs = [bar[2] for bar in bars]
        lows = [bar[3] for bar in bars]
        closes = [bar[4] for bar in bars]
        if not passes(highs, lows, closes, j_threshold):
            continue
        previous = closes[-2]
        js = kdj_j(highs, lows, closes)
        pick = {
            'code': code,
            'close': round(closes[-1], 3),
            'change_pct': round((closes[-1] / previous - 1) * 100, 2) if previous else None,
            'j_value': round(js[-1], 2),
            'volume': bars[-1][5],
        }
        picks.append(pick)
    # 结果按股票代码升序排列。
    picks.sort(key=lambda item: item['code'])
    return picks


def load(db, date):
    rows = db.execute('SELECT code, close, change_pct, j_value, volume FROM b1_results '
                      'WHERE date=? ORDER BY code', (date,)).fetchall()
    return [dict(row) for row in rows]


def save(db, date, picks, j_threshold=None, exclude_boards=None):
    """保存某一天的选股结果；先删掉当天旧结果，再写入本次条件与股票。"""
    boards = ','.join(sorted(exclude_boards or []))
    created = time.strftime('%Y-%m-%d %H:%M:%S')
    db.execute('DELETE FROM b1_results WHERE date=?', (date,))
    upsert = ('INSERT INTO b1_results '
              '(date,code,close,change_pct,j_value,volume,j_threshold,boards,created_at) '
              'VALUES (?,?,?,?,?,?,?,?,?) '
              'ON DUPLICATE KEY UPDATE close=VALUES(close), change_pct=VALUES(change_pct), '
              'j_value=VALUES(j_value), volume=VALUES(volume), j_threshold=VALUES(j_threshold), '
              'boards=VALUES(boards), created_at=VALUES(created_at)') if getattr(db, 'dialect', None) == 'mysql' \
        else 'INSERT OR REPLACE INTO b1_results ' \
             '(date,code,close,change_pct,j_value,volume,j_threshold,boards,created_at) VALUES (?,?,?,?,?,?,?,?,?)'
    for item in picks:
        db.execute(upsert, (date, item['code'], item['close'], item['change_pct'],
                            item['j_value'], item['volume'], j_threshold, boards, created))


def history(db):
    """历史选股记录：按日期由近到远，附带当天使用的条件与股票数。"""
    _ensure_schema(db)
    rows = db.execute('SELECT date, count(*), max(j_threshold), max(boards), max(created_at) '
                      'FROM b1_results GROUP BY date ORDER BY date DESC').fetchall()
    return [{'date': row[0], 'count': int(row[1]), 'j_threshold': row[2],
             'boards': [item for item in (row[3] or '').split(',') if item],
             'created_at': row[4]} for row in rows]


def picks_for(date=None, refresh=False, progress=None, exclude_boards=None, j_threshold=None):
    """返回 (日期, 选股结果, 是否新算)；结果连同条件按日期缓存进 b1_results 表。

    传了自定义条件（板块/J 阈值）时忽略缓存，按条件重新计算并覆盖当天结果。
    """
    from market_store import connect
    custom = bool(exclude_boards) or (j_threshold is not None
                                      and float(j_threshold) != PARAMS['j_threshold'])
    with connect() as db:
        day = date or db.execute("SELECT max(date) FROM daily_bars WHERE category='stock'").fetchone()[0]
        if not day:
            return None, [], False
        if not refresh and not custom:
            _ensure_schema(db)
            cached = load(db, day)
            if cached:
                if progress:
                    progress(100, f'{day} 使用已缓存的选股结果（{len(cached)} 只）')
                return day, cached, False
        _ensure_schema(db)
        picks = compute(db, day, progress, exclude_boards=exclude_boards, j_threshold=j_threshold)
        effective_j = PARAMS['j_threshold'] if j_threshold is None else float(j_threshold)
        save(db, day, picks, effective_j, exclude_boards)
        db.commit()
        return day, picks, True
