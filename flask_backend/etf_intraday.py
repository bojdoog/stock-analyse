"""汇金系宽基 ETF 分时数据（新浪财经 1 分钟线）的建表与读写。"""
import json
import re
import time
import urllib.request
from datetime import date as date_cls, timedelta

SINA_URL = ('https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData'
            '?symbol={symbol}&scale=1&ma=no&datalen=1023')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
           'Referer': 'https://finance.sina.com.cn/'}

FIELDS = ('open', 'high', 'low', 'close', 'volume', 'amount')

# 一个完整交易日约 240 个分钟槽；接口单次只回 1023 根，最早一天会被拦腰截断
MIN_MINUTES = 230
# 新浪只保留最近几个交易日，更早的日期没必要再请求
RECENT_DAYS = 10
# 同一只 ETF 的按需抓取冷却时间（秒），避免连续点击反复打接口
PULL_COOLDOWN = 600

_last_pull = {}


def usable_days(days):
    """保留完整交易日；最新一天允许不完整（盘中实时抓到的当日数据）。"""
    if not days:
        return {}
    latest = max(days)
    return {day: rows for day, rows in days.items() if len(rows) >= MIN_MINUTES or day == latest}


def purge_partial(db, min_minutes=MIN_MINUTES):
    """清理不足一个交易日的残日，保留每只最新一天（可能是当日盘中数据）。"""
    counts = db.execute('SELECT code, date, COUNT(*) FROM etf_intraday GROUP BY code, date').fetchall()
    latest = {row[0]: row[1] for row in
              db.execute('SELECT code, max(date) FROM etf_intraday GROUP BY code').fetchall()}
    stale = [(row[0], row[1]) for row in counts
             if row[2] < min_minutes and row[1] < latest.get(row[0], '')]
    for code, day in stale:
        db.execute('DELETE FROM etf_intraday WHERE code=? AND date=?', (code, day))
    return len(stale)


def pull(db, code, date):
    """库里查不到该日时，就地抓一次新浪最新分钟线入库；返回是否真的发起了抓取。"""
    if date < (date_cls.today() - timedelta(days=RECENT_DAYS)).isoformat():
        return False
    if time.time() - _last_pull.get(code, 0) < PULL_COOLDOWN:
        return False
    _last_pull[code] = time.time()
    try:
        days = usable_days(fetch(code))
    except Exception:
        return False
    rows = [row for day in sorted(days) for row in days[day]]
    if not rows:
        return False
    upsert(db, code, rows)
    db.commit()
    return True


def ensure_schema(db):
    mysql = getattr(db, 'dialect', None) == 'mysql'
    db.execute('''CREATE TABLE IF NOT EXISTS etf_intraday (
        code VARCHAR(20) NOT NULL, date VARCHAR(10) NOT NULL, time VARCHAR(8) NOT NULL,
        open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE NOT NULL, volume DOUBLE, amount DOUBLE,
        PRIMARY KEY(code, date, time))''' +
        (' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin' if mysql else ''))


def symbol(code):
    return ('sh' if code.startswith(('5', '6', '9')) else 'sz') + code


def fetch(code):
    """拉取最近约 5 个交易日的 1 分钟线，返回 {date: [row, ...]}。"""
    url = SINA_URL.format(symbol=symbol(code))
    body = None
    for attempt in range(3):
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20).read().decode()
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    start, end = body.find('['), body.rfind(']')
    if start < 0 or end < start:
        raise ValueError('分时接口返回为空')
    bars = json.loads(body[start:end + 1])
    days = {}
    for bar in bars:
        day, clock = bar['day'].split(' ')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or not re.fullmatch(r'\d{2}:\d{2}:\d{2}', clock):
            raise ValueError(f'非法时间戳 {bar["day"]}')
        # 新浪成交量单位为股，这里统一换算成手，与日线口径一致
        row = (day, clock, *(float(bar[key]) for key in ('open', 'high', 'low', 'close')),
               float(bar['volume']) / 100, float(bar['amount']))
        days.setdefault(day, []).append(row)
    return days


def upsert(db, code, rows):
    if getattr(db, 'dialect', None) == 'mysql':
        sql = ('INSERT INTO etf_intraday (code, date, time, open, high, low, close, volume, amount) '
               'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) '
               'ON DUPLICATE KEY UPDATE open=VALUES(open), high=VALUES(high), low=VALUES(low), '
               'close=VALUES(close), volume=VALUES(volume), amount=VALUES(amount)')
    else:
        sql = ('INSERT OR REPLACE INTO etf_intraday '
               '(code, date, time, open, high, low, close, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
    db.executemany(sql, [(code, *row) for row in rows])


def load(db, code, date):
    rows = db.execute('SELECT time, open, high, low, close, volume, amount FROM etf_intraday '
                      'WHERE code=? AND date=? ORDER BY time', (code, date)).fetchall()
    return [dict(row) for row in rows]
