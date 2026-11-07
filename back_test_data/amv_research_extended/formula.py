"""Frozen research candidate: original EMA20 plus smooth main-flow correction.

No target AMV observations needed. Daily after-close inputs only.
Display candles use consecutive estimated closes, not observed intraday OHLC.
"""
from pathlib import Path
import importlib.util
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('original_amv_formula',ROOT.parent/'amv_research/formula.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
FLOW_SPAN=40
FLOW_MEAN=-2.163271807211645
FLOW_STD=0.35290158113635006
COEFFICIENT=0.01703745581667001
def calculate(industry, codes, flows):
    old=original.calculate(industry,codes).set_index('date')
    f=flows.copy();f['date']=pd.to_datetime(f.trade_date.astype(str)).dt.strftime('%Y-%m-%d')
    if f.date.duplicated().any():raise ValueError('Duplicate flow dates')
    rate=f.set_index('date').net_amount_rate.reindex(old.index)
    if rate.isna().any() or not np.isfinite(rate).all():raise ValueError('Missing flow observations; refresh source rather than forward-fill')
    smooth=rate.ewm(span=FLOW_SPAN,adjust=False).mean()
    corrected=old.close*np.exp(COEFFICIENT*(smooth-FLOW_MEAN)/FLOW_STD)
    return pd.DataFrame({'date':old.index,'close':corrected.to_numpy()})
if __name__=='__main__':
    import argparse
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-db',action='store_true',help='Import as an independent indicator with synthetic daily candles')
    args=parser.parse_args()
    industry=pd.read_csv(ROOT.parent/'ths_daily/all_industries.csv')
    codes=json.loads((ROOT.parent/'metadata/industry_universe.json').read_text(encoding='utf8'))['codes']
    flow=pd.read_csv(max((ROOT.parent/'moneyflow_mkt_dc').glob('20240910_*.csv')))
    result=calculate(industry,codes,flow)
    predictions=pd.read_csv(ROOT/'predictions.csv')
    parity=result.merge(predictions[['date','selected']],on='date')
    assert len(parity)==len(predictions), 'Frozen predictions must remain a prefix of the extension'
    assert np.allclose(parity.close,parity.selected,rtol=1e-12,atol=1e-8)
    # A prefix must be unchanged when later observations are supplied.
    cutoff=20251231
    prefix=calculate(industry[industry.trade_date<=cutoff],codes,flow[flow.trade_date<=cutoff])
    assert np.allclose(prefix.close,result.close.iloc[:len(prefix)],rtol=1e-12,atol=1e-8)
    result.to_csv(ROOT/'candidate_amv_flow40_close.csv',index=False,encoding='utf-8-sig')
    if args.import_db:
        sys.path.insert(0,str(ROOT.parents[1]/'flask_backend'))
        from market_store import save_dataframe, connect
        with connect() as db:
            benchmark=pd.DataFrame([dict(row) for row in db.execute(
                "SELECT date,volume,amount FROM daily_bars "
                "WHERE category='index' AND exchange='SH' AND code='000001' ORDER BY date")])
        # The research MCP snapshot may extend beyond the application's index table.
        snapshot=json.loads((ROOT/'raw/index_000001.SH.json').read_text(encoding='utf8'))
        if snapshot.get('tool')!='index_daily' or snapshot['arguments'].get('ts_code')!='000001.SH':
            raise ValueError('Unexpected benchmark snapshot')
        supplement=pd.DataFrame(snapshot['rows'])
        supplement['date']=pd.to_datetime(supplement.trade_date.astype(str)).dt.strftime('%Y-%m-%d')
        supplement=supplement.rename(columns={'vol':'volume'})[['date','volume','amount']]
        benchmark['date']=pd.to_datetime(benchmark.date).dt.strftime('%Y-%m-%d')
        benchmark=benchmark.set_index('date').combine_first(supplement.set_index('date')).reset_index()
        bars=original.build_daily_bars(result,benchmark)
        assert np.allclose(bars.close,result.close,rtol=1e-12,atol=1e-8)
        save_dataframe(bars,ROOT.parents[1]/'data/core_index/candidate_amv_flow40_close.csv')
    print(json.dumps({'rows':len(result),'last_date':result.date.iloc[-1],'research_prediction_parity':True,'prefix_invariance':True,'uses_target_amv':False}))
