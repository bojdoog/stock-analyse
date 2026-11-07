"""Publish the frozen THS log-memory research model as an independent indicator."""
import io
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'flask_backend'))
from market_store import connect,file_content
from resilient_store import save_dataframe,import_source
from back_test_data.amv_log_memory_research import features


def main():
    model_path='amv_log_memory/model.json'
    stored=file_content(model_path)
    if stored:
        model=json.loads(stored)
    else:
        research=json.loads((ROOT/'back_test_data/amv_log_memory/results.json').read_text(encoding='utf-8'))
        model={key:research[key] for key in ['intercept','coefficients','log_training_mean','log_training_std','train_end','first_prediction','industries']}
        model['code']='AMV_THS_LOG_MEMORY'
        import_source(model_path,json.dumps(model,ensure_ascii=False,indent=2).encode(),ROOT/'data'/model_path)
    source=ROOT/'back_test_data/ths_daily/all_industries.csv'
    frame=pd.read_csv(source)
    if frame.ts_code.nunique()!=model['industries']:
        raise ValueError('THS industry universe changed; review before publishing')
    x,_=features(frame)
    x=x.dropna()
    if x.empty or (x<=0).any().any():
        raise ValueError('Insufficient or invalid THS inputs')
    cols=list(model['coefficients'])
    z=(np.log(x[cols])-pd.Series(model['log_training_mean']))/pd.Series(model['log_training_std'])
    close=np.exp(model['intercept']+z.mul(pd.Series(model['coefficients'])).sum(axis=1))
    if not np.isfinite(close).all():raise ValueError('Nonfinite prediction')
    bars=pd.DataFrame({'date':close.index.strftime('%Y-%m-%d'),'close':close.to_numpy()})
    bars['open']=bars.close.shift(1).fillna(bars.close)
    bars['high']=bars[['open','close']].max(axis=1)
    bars['low']=bars[['open','close']].min(axis=1)
    with connect() as db:
        benchmark=pd.DataFrame([dict(r) for r in db.execute("SELECT date,volume,amount FROM daily_bars WHERE category='index' AND code='000001' AND exchange='SH' ORDER BY date")],columns=['date','volume','amount'])
    bars=bars.merge(benchmark,on='date',how='left',validate='one_to_one')
    save_dataframe(bars,ROOT/'data/core_index/candidate_amv_log_memory_close.csv',category='core_index')
    report={'code':model['code'],'rows':len(bars),'start':bars.date.iloc[0],'end':bars.date.iloc[-1],
            'missing_benchmark_rows':int(bars.volume.isna().sum()),'synthetic_ohlc':True,'parameters_refitted':False}
    import_source('amv_log_memory/publish_report.json',json.dumps(report,indent=2).encode(),ROOT/'data/amv_log_memory/publish_report.json')
    print(json.dumps(report))


if __name__=='__main__':main()
