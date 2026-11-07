"""Chronological SW-only reconstruction study. Never overwrites production indicators.

Replaces the THS capitalization/turnover quantity proxy with traded value / index
level from SW candles. This is a different estimator, not the old formula with a
new scale. Complete observations from every industry are required.
"""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'flask_backend'))
from market_store import connect


def main():
    universe = json.loads((ROOT/'data/sw_metadata/universe.json').read_text(encoding='utf-8'))
    frames = [pd.read_csv(p) for p in sorted((ROOT/'data/sw_index').glob('[0-9]'*8 + '.csv'))]
    if not frames:
        raise ValueError('No daily SW CSV exports')
    frame = pd.concat(frames,ignore_index=True)
    codes = [item['index_code'] for item in universe]
    frame = frame[frame.ts_code.isin(codes)]
    prices = frame.pivot(index='date',columns='ts_code',values='close').reindex(columns=codes).sort_index()
    amount = frame.pivot(index='date',columns='ts_code',values='amount').reindex_like(prices)
    if prices.isna().any().any() or amount.isna().any().any():
        raise ValueError('Incomplete SW inputs; repair missing industry-days before fitting')
    with connect() as db:
        target = pd.DataFrame([dict(r) for r in db.execute(
            "SELECT d.date,d.close FROM indicator_daily d JOIN indicators i ON d.indicator_id=i.id WHERE i.code='0AMV' ORDER BY d.date")])
    target = target.set_index('date').close.reindex(prices.index)
    if target.isna().any():
        raise ValueError('Missing original AMV validation targets')
    train = (prices.index >= '2024-12-10') & (prices.index <= '2025-06-30')
    valid = (prices.index >= '2025-07-01') & (prices.index <= '2025-12-31')
    test = prices.index >= '2026-01-01'
    candidates = []
    predictions = pd.DataFrame({'date':prices.index,'original':target.to_numpy()})
    for span in [10,15,20,25,30,40,60]:
        unscaled = (prices * (amount / 1e8 / prices).ewm(span=span,adjust=False).mean()).sum(axis=1)
        scale = float(np.median(target[train] / unscaled[train]))
        estimate = unscaled * scale
        def metrics(mask):
            return {'n':int(mask.sum()),'mape_pct':float(np.mean(abs(estimate[mask]/target[mask]-1))*100),
                'return_corr':float(estimate.pct_change()[mask].corr(target.pct_change()[mask])),
                'return_mae_pp':float(np.mean(abs(estimate.pct_change()[mask]-target.pct_change()[mask]))*100)}
        candidates.append({'span':span,'scale':scale,'train':metrics(train),'validation':metrics(valid),'test':metrics(test)})
        predictions[f'sw_{span}'] = estimate.to_numpy()
    best = min(candidates,key=lambda r:r['validation']['mape_pct'])
    output = ROOT/'back_test_data/amv_sw_research'
    output.mkdir(exist_ok=True)
    predictions.to_csv(output/'predictions.csv',index=False)
    result = {'formula':'scale * sum(P * EMA_span((SW amount in yuan / 1e8) / P))',
        'uses_original_amv_in_daily_calculation':False,'initial_date':prices.index[0],
        'last_date':prices.index[-1],'industries':len(prices.columns),'rows':len(prices),
        'selection':'minimum 2025 H2 validation MAPE; scale fitted only through 2025-06-30',
        'candidates':candidates,'selected':best,'production_changed':False}
    (output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
