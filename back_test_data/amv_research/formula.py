"""Frozen AMV replacement candidate v1. Requires only THS industry history.

The close formula is unchanged. Display OHLC is constructed from consecutive closes,
and volume/amount come from the same-date Shanghai Composite index in the database.
Constants were fitted/selected chronologically. No original AMV values are read here.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

SPAN = 20
ALPHA = 2 / (SPAN + 1)
SCALE = 7.695442042177039
BASE = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE.parent / 'data/core_index/candidate_amv_close.csv'


def calculate(frame: pd.DataFrame, industry_codes: list[str]) -> pd.DataFrame:
    required = {'trade_date', 'ts_code', 'close', 'float_mv', 'turnover_rate'}
    if not required.issubset(frame.columns):
        raise ValueError(f'Missing columns: {sorted(required - set(frame.columns))}')
    data = frame[frame.ts_code.isin(industry_codes)].copy()
    data['date'] = pd.to_datetime(data.trade_date.astype(str), format='%Y%m%d')
    if data.duplicated(['date', 'ts_code']).any():
        raise ValueError('Duplicate industry/date records')
    if data.empty or data.date.min() != pd.Timestamp('2024-09-10'):
        raise ValueError('Provide history from 2024-09-10 to preserve the calibrated EMA initial state')
    close = data.pivot(index='date', columns='ts_code', values='close').reindex(columns=industry_codes).sort_index()
    mv = data.pivot(index='date', columns='ts_code', values='float_mv').reindex(index=close.index, columns=industry_codes)
    turnover = data.pivot(index='date', columns='ts_code', values='turnover_rate').reindex(index=close.index, columns=industry_codes)
    for values in (close, mv, turnover):
        if not np.isfinite(values.to_numpy(float)).all():
            raise ValueError('Missing/non-finite industry observations; do not fill with future data')
    if (close <= 0).any().any() or (mv <= 0).any().any() or (turnover < 0).any().any():
        raise ValueError('Invalid price, capitalization or turnover')
    quantity_proxy = (mv / 1e8) * (turnover / 100) / close
    smoothed = quantity_proxy.ewm(span=SPAN, adjust=False).mean()
    estimate = SCALE * (smoothed * close).sum(axis=1)
    return pd.DataFrame({'date': estimate.index.strftime('%Y-%m-%d'), 'close': estimate.to_numpy()})


def build_daily_bars(closes: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    """Synthetic candle bodies, not observed intraday highs/lows; no future filling."""
    result = closes[['date', 'close']].copy()
    result['date'] = pd.to_datetime(result.date).dt.strftime('%Y-%m-%d')
    result = result.sort_values('date').reset_index(drop=True)
    market = benchmark[['date', 'volume', 'amount']].copy()
    market['date'] = pd.to_datetime(market.date).dt.strftime('%Y-%m-%d')
    if result.empty or result.date.duplicated().any() or market.date.duplicated().any():
        raise ValueError('Empty close series or duplicate dates')
    if not np.isfinite(result.close.to_numpy(float)).all():
        raise ValueError('Missing/non-finite candidate closes')
    result['open'] = result.close.shift(1)
    result.loc[0, 'open'] = result.loc[0, 'close']
    result['high'] = result[['open', 'close']].max(axis=1)
    result['low'] = result[['open', 'close']].min(axis=1)
    result = result.merge(market, on='date', how='left', validate='one_to_one')
    values = result[['volume', 'amount']].to_numpy(float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Shanghai Composite volume/amount missing or invalid; update index data before generating candles')
    return result[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(BASE.parent / 'flask_backend'))
    from market_store import connect, save_dataframe
    from research_storage import read_file
    import io
    codes = json.loads((BASE / 'metadata/industry_universe.json').read_text(encoding='utf-8'))['codes']
    result = calculate(pd.read_csv(io.BytesIO(read_file(BASE / 'ths_daily/all_industries.csv'))), codes)
    with connect() as db:
        benchmark = pd.DataFrame([dict(row) for row in db.execute(
            "SELECT date,volume,amount FROM daily_bars "
            "WHERE category='index' AND exchange='SH' AND code='000001' ORDER BY date")])
    result = build_daily_bars(result, benchmark)
    save_dataframe(result, OUTPUT_FILE)
    print(f'Generated {len(result)} synthetic OHLC bars with Shanghai Composite volume/amount; close formula unchanged')
