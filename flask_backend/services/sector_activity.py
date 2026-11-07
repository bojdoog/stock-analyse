"""Sector-level decomposition of the frozen daily AMV proxy (not a trading signal)."""
import csv
import io
import json
import math
from datetime import datetime
from functools import lru_cache

ALPHA = 2 / 21
SCALE = 7.695442042177039


def nonnegative(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


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
        volumes = []
        price_ranges = []
        k = d = 50.0
        previous_q = previous_price = None
        for row in records:
            volume = nonnegative(row.get('vol'))
            prior_volumes = volumes[-20:]
            volume_ratio = None
            if volume is not None and len(prior_volumes) == 20 and all(v is not None for v in prior_volumes):
                mean_volume = sum(prior_volumes) / 20
                if mean_volume > 0:
                    volume_ratio = volume / mean_volume
            volumes.append(volume)
            amount = nonnegative(row.get('amount'))
            avg_price = nonnegative(row.get('avg_price'))
            if amount is None and volume is not None and avg_price is not None and avg_price > 0:
                amount = nonnegative(volume * 100 * avg_price)
            price, mv, turnover = (float(row[key]) for key in ('close', 'float_mv', 'turnover_rate'))
            if not all(math.isfinite(x) for x in (price, mv, turnover)) or price <= 0 or mv <= 0 or turnover < 0:
                raise ValueError('行业行情存在无效数值')
            high, low = nonnegative(row.get('high')), nonnegative(row.get('low'))
            valid_range = high is not None and low is not None and 0 < low <= price <= high
            price_ranges.append((high, low) if valid_range else None)
            window = price_ranges[-9:]
            kdj = {'k': None, 'd': None, 'j': None}
            if len(window) == 9 and all(p is not None for p in window):
                highest = max(p[0] for p in window)
                lowest = min(p[1] for p in window)
                rsv = (price - lowest) / (highest - lowest) * 100 if highest > lowest else 50.0
                k = 2 / 3 * k + rsv / 3
                d = 2 / 3 * d + k / 3
                kdj = {'k': k, 'd': d, 'j': 3 * k - 2 * d}
            else:
                k = d = 50.0
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
                'amount': amount,
                'volume_ratio': volume_ratio,
                'volume': volume,
                **kdj,
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
