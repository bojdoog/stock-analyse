"""Sector-level decomposition of the frozen daily AMV proxy (not a trading signal)."""
import csv
import io
import json
import math
from datetime import datetime
from functools import lru_cache

ALPHA = 2 / 21
SCALE = 7.695442042177039


def calculate(rows, codes, names):
    groups = {code: [] for code in codes}
    for row in rows:
        if row['ts_code'] in groups:
            groups[row['ts_code']].append(row)
    result = {}
    common_dates = None
    for code, records in groups.items():
        records.sort(key=lambda row: str(row['trade_date']))
        dates = [str(row['trade_date']) for row in records]
        if not dates or dates[0] != '20240910' or len(set(dates)) != len(dates):
            raise ValueError('行业历史缺失或重复，需保留2024-09-10起的完整数据')
        if common_dates is not None and dates != common_dates:
            raise ValueError('行业交易日不一致，暂不生成可比较的排名')
        common_dates = dates
        series = []
        previous_q = previous_price = None
        for row in records:
            price, mv, turnover = (float(row[key]) for key in ('close', 'float_mv', 'turnover_rate'))
            if not all(math.isfinite(x) for x in (price, mv, turnover)) or price <= 0 or mv <= 0 or turnover < 0:
                raise ValueError('行业行情存在无效数值')
            proxy = mv / 1e8 * turnover / 100 / price
            q = proxy if previous_q is None else ALPHA * proxy + (1 - ALPHA) * previous_q
            value = price * q
            if not series and value <= 0:
                raise ValueError('首日活跃量为零，无法归一化')
            prev_value = previous_price * previous_q if series else None
            point = {
                'date': datetime.strptime(str(row['trade_date']), '%Y%m%d').strftime('%Y-%m-%d'),
                'value': value,
                'amv': value / (series[0]['value'] if series else value) * 100,
                'price': price,
                'quantity': q,
                'turnover': turnover,
                'change': (value / prev_value - 1) * 100 if series else None,
                'price_change': (price / previous_price - 1) * 100 if series else None,
                'quantity_change': (q / previous_q - 1) * 100 if series else None,
                'price_contribution': (price - previous_price) * previous_q / prev_value * 100 if series else None,
                'activity_contribution': price * (q - previous_q) / prev_value * 100 if series else None,
            }
            series.append(point)
            point['ma10'] = sum(x['amv'] for x in series[-10:]) / 10 if len(series) >= 10 else None
            point['change5'] = (value / series[-6]['value'] - 1) * 100 if len(series) >= 6 else None
            previous_price, previous_q = price, q
        result[code] = {'code': code, 'name': names.get(code, code), 'series': series}
    totals = [sum(item['series'][i]['value'] for item in result.values()) for i in range(len(common_dates))]
    for item in result.values():
        for i, point in enumerate(item['series']):
            point['market'] = totals[i] / totals[0] * 100
            point['weight'] = point['value'] / totals[i] * 100
            point['market_contribution'] = ((point['value'] - item['series'][i-1]['value']) / totals[i-1] * 100) if i else None
    return result


@lru_cache(maxsize=2)
def from_bytes(history, universe, names):
    rows = csv.DictReader(io.StringIO(history.decode('utf-8-sig')))
    name_map = {row['ts_code']: row['name'] for row in csv.DictReader(io.StringIO(names.decode('utf-8-sig')))}
    return calculate(rows, json.loads(universe.decode('utf-8-sig'))['codes'], name_map)
