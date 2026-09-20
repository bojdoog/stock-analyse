"""Extend the frozen AMV formula using complete THS industry observations."""
import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back_test_data" / "amv_research"))

from formula import BASE, OUTPUT_FILE, calculate, build_daily_bars

sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / 'flask_backend'))
try:
    from .download_amv_research import query, redact
except ImportError:
    from download_amv_research import query, redact
from market_store import connect, file_content, save_dataframe
from research_storage import archive_file, read_file


def update(end):
    codes = json.loads((BASE / 'metadata/industry_universe.json').read_text(encoding='utf-8'))['codes']
    source_path = BASE / 'ths_daily/all_industries.csv'
    old = pd.read_csv(io.BytesIO(read_file(source_path)))
    old['trade_date'] = old.trade_date.astype(str)
    start = (pd.to_datetime(old.trade_date.max()) + pd.Timedelta(days=1)).strftime('%Y%m%d')
    if start > end:
        print('Industry inputs already cover requested date; regenerating from existing inputs', flush=True)
        incoming = []
        days = []
    else:
        calendar = query('trade_cal', {'exchange': 'SSE', 'start_date': start, 'end_date': end},
                         'amv_update_' + start + '_' + end)
        days = sorted(str(row['cal_date']) for row in calendar if str(row['is_open']) == '1')
        if not days or days[-1] != end:
            raise ValueError('Requested end date is not covered by the trading calendar')
        fields = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
                  'pct_change', 'vol', 'turnover_rate', 'float_mv', 'total_mv']
        incoming = []
        for day in days:
            batch = query('ths_daily', {'trade_date': day, 'fields': fields}, 'amv_update_' + day)
            relevant = [row for row in batch if row['ts_code'] in codes]
            present = {row['ts_code'] for row in relevant}
            for code in sorted(set(codes) - present):
                relevant.extend(query('ths_daily', {'ts_code': code, 'trade_date': day, 'fields': fields},
                                      'amv_update_' + day + '_' + code))
            if len(relevant) != len(codes) or {row['ts_code'] for row in relevant} != set(codes):
                raise ValueError(f'Incomplete/duplicate industry observations on {day}')
            if any(str(row['trade_date']) != day for row in relevant):
                raise ValueError(f'Unexpected industry date for {day}')
            incoming.extend(relevant)
            print(f'Industry coverage {day}: {len(relevant)}/{len(codes)}', flush=True)
    merged = pd.concat([old, pd.DataFrame(incoming)], ignore_index=True) if incoming else old
    merged['trade_date'] = merged.trade_date.astype(str)
    merged = merged.sort_values(['trade_date', 'ts_code']).reset_index(drop=True)
    closes = calculate(merged, codes)
    previous = pd.read_csv(io.BytesIO(file_content('core_index/candidate_amv_close.csv')))
    overlap = previous.merge(closes, on='date', suffixes=('_old', '_new'), validate='one_to_one')
    if len(overlap) != len(previous):
        raise ValueError('Recalculation would lose existing candidate dates')
    np.testing.assert_allclose(overlap.close_old, overlap.close_new, rtol=1e-12, atol=0)
    if closes.date.iloc[-1].replace('-', '') < end:
        raise ValueError('Candidate did not reach requested date')

    with connect() as db:
        index_path = db.execute("SELECT source_path FROM instruments WHERE category='index' "
                                "AND exchange='SH' AND code='000001'").fetchone()[0]
        benchmark = pd.DataFrame([dict(row) for row in db.execute(
            "SELECT date,volume,amount FROM daily_bars WHERE category='index' "
            "AND exchange='SH' AND code='000001' ORDER BY date")])
    needed = closes[~closes.date.isin(benchmark.dropna(subset=['volume', 'amount']).date)].date
    if len(needed):
        rows = query('index_daily', {'ts_code': '000001.SH', 'start_date': needed.min().replace('-', ''),
                                    'end_date': end}, 'amv_benchmark_' + needed.min().replace('-', '') + '_' + end)
        index = pd.DataFrame(rows).rename(columns={'trade_date': 'date', 'vol': 'volume'})
        index['date'] = pd.to_datetime(index.date.astype(str), format='%Y%m%d').dt.strftime('%Y-%m-%d')
        index = index[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']].sort_values('date')
        if not set(needed).issubset(set(index.date)):
            raise ValueError('Shanghai Composite benchmark is incomplete')
        if not np.isfinite(index.drop(columns='date').to_numpy(float)).all():
            raise ValueError('Invalid Shanghai Composite observations')
        save_dataframe(index, BASE.parent / 'data' / index_path)
        benchmark = pd.concat([benchmark, index[['date','volume','amount']]]).drop_duplicates('date', keep='last')
    bars = build_daily_bars(closes, benchmark)
    backup = BASE.parent / 'flask_backend/instance' / ('amv_sync_' + end)
    backup.mkdir(exist_ok=True)
    if not (backup / 'all_industries.csv').exists():
        (backup / 'all_industries.csv').write_bytes(source_path.read_bytes())
    # Save only new dates: existing published values retain their exact float representation.
    new_bars = bars[~bars.date.isin(previous.date)]
    if len(new_bars):
        save_dataframe(new_bars, OUTPUT_FILE)
    merged.to_csv(source_path, index=False, encoding='utf-8-sig')
    archive_file(source_path)
    for code, group in merged.groupby('ts_code'):
        group.to_csv(BASE / 'ths_daily' / (code + '.csv'), index=False, encoding='utf-8-sig')
        archive_file(BASE / 'ths_daily' / (code + '.csv'))
    stored = pd.read_csv(io.BytesIO(file_content('core_index/candidate_amv_close.csv')))
    pd.testing.assert_frame_equal(previous, stored[stored.date.isin(previous.date)].reset_index(drop=True))
    assert stored.date.max() == bars.date.max()
    np.testing.assert_allclose(stored.tail(len(new_bars)).close, new_bars.close, rtol=1e-12) if len(new_bars) else None
    report = {'end_date': stored.date.max(), 'new_days': days, 'industry_count': len(codes),
              'new_industry_rows': len(incoming), 'new_indicator_rows': len(new_bars),
              'historical_candidate_values_unchanged': True, 'latest': stored.tail(5).to_dict('records')}
    (backup / 'candidate_update_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end', required=True, help='Last trading date, YYYYMMDD')
    args = parser.parse_args()
    try:
        update(args.end)
    except Exception as exc:
        print(redact(exc), file=sys.stderr)
        sys.exit(1)
