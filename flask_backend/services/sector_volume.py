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
    for index, day in enumerate(days):
        if index < 20:
            continue
        window = days[index - 20:index + 1]
        # Saved amount is vol (hands) * 100 * avg_price, in yuan. Require the
        # complete fixed industry universe so missing sectors cannot inflate shares.
        market_amounts = [number(histories.get(code, {}).get(day, {}).get('amount')) for code in universe]
        total_amount = sum(market_amounts) if market_amounts and all(v is not None for v in market_amounts) else None
        features = {}
        for name, codes in resolved.items():
            if not codes:
                continue
            totals = []
            for date in window:
                values = [number(histories.get(code, {}).get(date, {}).get('vol')) for code in codes]
                if any(v is None for v in values):
                    break
                totals.append(sum(values))
            if len(totals) != 21 or sum(totals[:-1]) <= 0:
                continue
            amounts = [number(histories.get(code, {}).get(day, {}).get('amount')) for code in codes]
            share = (sum(amounts) / total_amount if total_amount and all(v is not None for v in amounts) else None)
            features[name] = dict(volumeRatio=totals[-1] / (sum(totals[:-1]) / 20), amountShare=share)
        if features:
            by_date[day] = features
    return dict(byDate=by_date, coverageStart=min(by_date) if by_date else None,
                coverageEnd=max(by_date) if by_date else None,
                amountAvailable=any(v['amountShare'] is not None for f in by_date.values() for v in f.values()),
                mappedNames=[name for name, codes in resolved.items() if codes],
                unmappedNames=[name for name, codes in resolved.items() if not codes],
                mappings=resolved, amountScope='同花顺固定行业集合成交额合计',
                amountFormula='vol × 100 × avg_price', amountUnit='元')


def load_sector_volume(database):
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
    return build_features(days, catalog, mappings, industries, histories)
