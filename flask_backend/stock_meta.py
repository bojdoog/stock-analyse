"""个股静态信息：名称、行业与所属板块。

数据来源是 fetch_data/stocklist.csv（ts_code,symbol,name,area,industry），按文件修改时间缓存。
"""
import csv
from pathlib import Path

STOCKLIST = Path(__file__).resolve().parents[1] / 'fetch_data' / 'stocklist.csv'
_cache = {'mtime': None, 'rows': {}}


def _board(code):
    if code.startswith(('300', '301')):
        return '创业板'
    if code.startswith('688'):
        return '科创板'
    if code.startswith(('4', '8', '92')):
        return '北交所'
    return '主板'


def _load():
    try:
        mtime = STOCKLIST.stat().st_mtime
    except OSError:
        return {}
    if _cache['mtime'] == mtime:
        return _cache['rows']
    rows = {}
    with STOCKLIST.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            code = (row.get('symbol') or '').strip()
            if code:
                rows[code] = {'name': (row.get('name') or '').strip(),
                              'industry': (row.get('industry') or '').strip()}
    _cache.update(mtime=mtime, rows=rows)
    return rows


def describe(code):
    code = str(code).zfill(6)
    info = _load().get(code, {})
    return {
        'name': info.get('name') or code,
        'board': _board(code),
        'industry': info.get('industry') or '',
    }
