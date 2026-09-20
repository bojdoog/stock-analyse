"""Offline integrity and source-data checks for the downloaded research dataset."""
import csv
from collections import Counter
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_rows(relative):
    with (ROOT / relative).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


report = json.loads((ROOT / 'quality_report.json').read_text(encoding='utf-8'))
prices = read_rows('ths_daily/all_industries.csv')
codes = set(json.loads((ROOT / 'metadata/industry_universe.json').read_text(encoding='utf-8'))['codes'])
calendar = {r['cal_date'] for r in read_rows('trade_cal/SSE_20240910_20260911.csv') if r['is_open'] == '1'}
keys = {(r['ts_code'], r['trade_date']) for r in prices}
assert len(keys) == len(prices) == len(codes) * len(calendar), 'Industry price coverage or duplicate error'
assert keys == {(code, day) for code in codes for day in calendar}, 'Unexpected or missing price dates'
numeric_fields = ['open', 'high', 'low', 'close', 'pre_close', 'pct_change', 'vol', 'turnover_rate', 'float_mv', 'total_mv']
assert all(math.isfinite(float(r[k])) for r in prices for k in numeric_fields), 'Invalid numeric field'
price_issues = [r for r in prices if min(float(r[k]) for k in ('open', 'high', 'low', 'close', 'float_mv', 'total_mv')) <= 0
                or float(r['low']) > min(float(r['open']), float(r['close']))
                or float(r['high']) < max(float(r['open']), float(r['close']))
                or float(r['vol']) < 0 or float(r['turnover_rate']) < 0]

flows = read_rows('moneyflow_ind_ths/20240910_20260911.csv')
flow_issues = []
for row in flows:
    difference = float(row['net_buy_amount']) - float(row['net_sell_amount']) - float(row['net_amount'])
    # Tolerance allows independent rounding of the three reported amounts.
    if abs(difference) > 2:
        flow_issues.append({**row, 'buy_minus_sell_minus_net': difference})
(ROOT / 'quality').mkdir(exist_ok=True)
with (ROOT / 'quality/flow_arithmetic_anomalies.csv').open('w', encoding='utf-8-sig', newline='') as f:
    if flow_issues:
        writer = csv.DictWriter(f, fieldnames=list(flow_issues[0]))
        writer.writeheader()
        writer.writerows(flow_issues)

report['offline_verification'] = {
    'industry_cartesian_coverage_pass': True,
    'industry_numeric_fields_finite_pass': True,
    'industry_nonpositive_or_ohlc_issues': len(price_issues),
    'flow_arithmetic_tolerance_in_source_units': 2,
    'flow_arithmetic_anomalies': len(flow_issues),
    'flow_arithmetic_anomalies_by_date': dict(Counter(r['trade_date'] for r in flow_issues)),
    'note': 'Source anomalies are preserved; no automatic decimal/unit repair or missing-value imputation.',
}
(ROOT / 'quality_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
summary = ['# 下载数据检查', '',
    f'- 行业行情：{len(codes)} 个行业 × {len(calendar)} 个交易日 = {len(prices):,} 行；覆盖、唯一键、有限数值检查通过。',
    f'- 行业行情 OHLC、正市值和非负量检查异常：{len(price_issues)} 行。',
    '- 行业资金流：缺 2024-11-04、2025-01-20，单日重查仍无数据。',
    '- 行业资金流：2024-09-10 至 2024-09-27 共 12 个交易日三个资金字段全部为零，不直接解释成无交易。',
    f'- 行业资金流：{len(flow_issues)} 行买入－卖出与净额之差超过 2 个源单位，日期分布见下方；保留原值，未经核实不得用于资金总量计算。',
    '- 深圳统计：缺 2024-11-12；成交量、总股本、流通股本字段全为空。',
    '- 行业成分快照：5578 行，纳入/剔除日期全为空，不能据此还原历史成分。',
    '- 市场统计的部分字段为空，按数据类型逐字段检查，不以日期完整代替字段完整。',
    '', '资金字段算术异常日期：', '',
    json.dumps(report['offline_verification']['flow_arithmetic_anomalies_by_date'], ensure_ascii=False),
    '', '明细：[flow_arithmetic_anomalies.csv](flow_arithmetic_anomalies.csv)',
    '机器可读报告：[quality_report.json](../quality_report.json)', '']
(ROOT / 'quality/README.md').write_text('\n'.join(summary), encoding='utf-8')
print(json.dumps(report['offline_verification'], ensure_ascii=True))
