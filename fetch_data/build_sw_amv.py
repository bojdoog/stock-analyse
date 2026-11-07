"""Build the SW-only AMV candidate from the accepted daily data snapshot.

The scale is frozen after initial chronological calibration. Missing industry-day
observations retain the industry's last valid contribution, never zero or a
future observation. Original AMV is used only for initial fitting/evaluation.
"""
import argparse
import io
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'flask_backend'))
from market_store import connect, file_content
from resilient_store import import_source,save_dataframe

MODEL_PATH='sw_metadata/amv_model.json'


def contributions(frame,codes,span=20):
    if frame.duplicated(['date','ts_code']).any():
        raise ValueError('Duplicate SW industry/day rows')
    p=frame.pivot(index='date',columns='ts_code',values='close').reindex(columns=codes).sort_index()
    amount=frame.pivot(index='date',columns='ts_code',values='amount').reindex_like(p)
    valid=p.gt(0)&amount.ge(0)&np.isfinite(p)&np.isfinite(amount)
    p=p.where(valid)
    q=(amount/1e8/p).where(valid)
    smooth=q.ewm(span=span,adjust=False,ignore_na=True).mean()
    # An absent contribution is carried only from earlier observations.
    parts=(p*smooth).ffill()
    total=parts.sum(axis=1,min_count=len(codes)).dropna()
    return total,valid.sum(axis=1).reindex(total.index)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refit',action='store_true',help='Explicitly replace the frozen scale')
    args=parser.parse_args()
    with connect() as db:
        sources=db.execute("SELECT content FROM source_files WHERE category='sw_index' ORDER BY path").fetchall()
        target=pd.DataFrame([dict(r) for r in db.execute("SELECT d.date,d.close FROM indicator_daily d JOIN indicators i ON i.id=d.indicator_id WHERE i.code='0AMV' ORDER BY d.date")])
    if not sources:
        print('[SKIP] SW AMV: no daily data')
        return 3
    frame=pd.concat([pd.read_csv(io.BytesIO(r['content'])) for r in sources],ignore_index=True)
    stored=file_content(MODEL_PATH)
    model=json.loads(stored) if stored and not args.refit else None
    if model:
        codes=model['codes']
        frame=frame[frame.date>=model['initial_date']]
    else:
        universe=json.loads(file_content('sw_metadata/universe.json'))
        codes=sorted(row['index_code'] for row in universe)
    raw,coverage=contributions(frame,codes)
    if raw.empty:
        raise ValueError('No day with all SW industries initialized')
    if model and raw.index[0]!=model['initial_date']:
        raise ValueError('Missing initial SW history; refusing to change EMA state')
    original=target.set_index('date').close.reindex(raw.index)
    if model is None:
        train=(raw.index>='2024-12-10')&(raw.index<='2025-06-30')&original.notna()&raw.gt(0)
        if train.sum()<30:
            raise ValueError('Insufficient calibration observations through 2025-06-30')
        model={'code':'AMV_SW_EMA20','span':20,'scale':float(np.median(original[train]/raw[train])),
            'codes':codes,'initial_date':raw.index[0],'fit_start':'2024-12-10','fit_end':'2025-06-30',
            'formula':'scale * sum(close * EMA20((amount_yuan / 1e8) / close))',
            'missing_policy':'carry last valid industry contribution; no future filling'}
        import_source(MODEL_PATH,json.dumps(model,indent=2).encode(),ROOT/'data'/MODEL_PATH)
    estimate=raw*model['scale']
    bars=pd.DataFrame({'date':estimate.index,'close':estimate.to_numpy()})
    bars['open']=bars.close.shift(1).fillna(bars.close)
    bars['high']=bars[['open','close']].max(axis=1)
    bars['low']=bars[['open','close']].min(axis=1)
    totals=frame[frame.ts_code.isin(codes)].groupby('date')[['volume','amount']].sum(min_count=1)
    bars=bars.merge(totals,on='date',how='left',validate='one_to_one')
    save_dataframe(bars,ROOT/'data/core_index/candidate_amv_sw_close.csv',category='core_index')
    metrics={}
    for name,a,b in [('train','2024-12-10','2025-06-30'),('validation','2025-07-01','2025-12-31'),('test','2026-01-01','9999-12-31')]:
        mask=(raw.index>=a)&(raw.index<=b)&original.notna()
        metrics[name]={'rows':int(mask.sum()),'mape_pct':float((estimate[mask]/original[mask]-1).abs().mean()*100)}
    report={'code':model['code'],'rows':len(bars),'last_date':bars.date.iloc[-1],
        'scale':model['scale'],'industries':len(codes),'days_with_carried_contributions':int((coverage<len(codes)).sum()),
        'missing_industry_days':int((len(codes)-coverage).sum()),'metrics':metrics,
        'synthetic_ohlc':True,'volume_amount':'sum of available SW industry bars; shares/yuan'}
    import_source('sw_metadata/amv_report.json',json.dumps(report,indent=2).encode(),ROOT/'data/sw_metadata/amv_report.json')
    print(json.dumps(report),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
