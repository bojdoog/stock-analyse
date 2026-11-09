"""Point-in-time THS industry volume features, using the database ETF mappings."""
import csv
import io
import math

from market_store import PROJECT, connect
from research_storage import read_file


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def build_features(days, catalog, mappings, industries, histories):
    """All 20 prior sessions are required; no forward fill, proxies or ETF volume."""
    by_date = {}
    resolved = {}
    for etf in catalog:
        names = {m['sector_name'] for m in mappings if m['etf_code'] == etf['code']}
        resolved[etf['name']] = sorted({i['ts_code'] for i in industries if i['name'] in names})
    universe = sorted({i['ts_code'] for i in industries})
    # 全市场固定行业集合的每日成交额；任一行业缺失即视为不可用。
    market_amounts = []
    for day in days:
        values = [number(histories.get(code, {}).get(day, {}).get('amount')) for code in universe]
        market_amounts.append(sum(values) if values and all(v is not None for v in values) else None)

    # 先按板块汇总每日成交量，再用前缀和取 21 日窗口，避免每天重复遍历 21 天 × 成分股。
    prepared = {}
    for name, codes in resolved.items():
        if not codes:
            continue
        volumes, prefixes, runs = [], [0.0], [0]
        for day in days:
            values = [number(histories.get(code, {}).get(day, {}).get('vol')) for code in codes]
            volume = sum(values) if all(v is not None for v in values) else None
            volumes.append(volume)
            prefixes.append(prefixes[-1] + (volume or 0.0))
            runs.append(runs[-1] + 1 if volume is not None else 0)
        prepared[name] = (volumes, prefixes, runs)

    for index, day in enumerate(days):
        if index < 20:
            continue
        features = {}
        for name, (volumes, prefixes, runs) in prepared.items():
            # runs 记录截至前一天的连续完整天数，加 1 覆盖当天。
            if runs[index] < 20 or volumes[index] is None:
                continue
            prior = prefixes[index] - prefixes[index - 20]
            if prior <= 0:
                continue
            row_amounts = [number(histories.get(code, {}).get(day, {}).get('amount'))
                           for code in resolved[name]]
            share = (sum(row_amounts) / market_amounts[index]
                     if market_amounts[index] and all(v is not None for v in row_amounts) else None)
            features[name] = dict(volumeRatio=volumes[index] / (prior / 20), amountShare=share)
        if features:
            by_date[day] = features
    return dict(byDate=by_date, coverageStart=min(by_date) if by_date else None,
                coverageEnd=max(by_date) if by_date else None,
                amountAvailable=any(v['amountShare'] is not None for f in by_date.values() for v in f.values()),
                mappedNames=[name for name, codes in resolved.items() if codes],
                unmappedNames=[name for name, codes in resolved.items() if not codes],
                mappings=resolved, amountScope='同花顺固定行业集合成交额合计',
                amountFormula='vol × 100 × avg_price', amountUnit='元')


# 行业历史与 ETF 映射只有在数据更新时才会变化，按数据版本缓存，避免每次请求重算。
_CACHE = {}


def _signature(database):
    with connect(database) as db:
        stamp = db.execute('SELECT MAX(imported_at) AS t, COUNT(*) AS n FROM source_files').fetchone()
        amv = db.execute("SELECT MAX(date) AS d FROM indicator_daily"
                         " WHERE indicator_id=(SELECT id FROM indicators WHERE code='0AMV')").fetchone()
    return str(database), f"{stamp['t'] or ''}:{stamp['n']}", amv['d'] if amv else None


def load_sector_volume(database):
    key = _signature(database)
    if key in _CACHE:
        return _CACHE[key]
    root = PROJECT / 'back_test_data'
    def rows(path):
        content = read_file(root / path, database)
        return list(csv.DictReader(io.StringIO(content.decode('utf-8-sig')))) if content else []
    industries = rows('ths_index/research_industries.csv')
    if not industries:
        raise ValueError('尚无同花顺行业日线数据，请先运行数据拉取。')
    histories = {}
    for industry in industries:
        code = industry['ts_code']
        # Only code identifiers from the industry catalog are allowed as file names.
        if not code.endswith('.TI') or not code[:-3].isdigit():
            raise ValueError('同花顺行业代码格式无效')
        history = rows(f'ths_daily/{code}.csv')
        histories[code] = {
            f"{r['trade_date'][:4]}-{r['trade_date'][4:6]}-{r['trade_date'][6:8]}": r
            for r in history
        }
    with connect(database) as db:
        catalog = [dict(r) for r in db.execute('SELECT code,name FROM etf_catalog WHERE enabled=1 ORDER BY sort_order,code')]
        mappings = [dict(r) for r in db.execute("SELECT sector_name,etf_code FROM etf_sector_mapping WHERE flow_type='ind_ths'")]
        days = [r['date'] for r in db.execute("SELECT date FROM indicator_daily WHERE indicator_id=(SELECT id FROM indicators WHERE code='0AMV') ORDER BY date")]
    result = build_features(days, catalog, mappings, industries, histories)
    _CACHE.clear()
    _CACHE[key] = result
    return result
