"""Screenshot-inspired sector log-linear reconstruction; not an exact replication.

Trade memory is explicitly defined here as trailing arithmetic mean of aggregate
float-cap * turnover. Free float cap is unavailable and omitted. All predictors
are industry inputs; target and scaling parameters are fitted only through 2025.
"""
from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'flask_backend'))
from market_store import connect


def features(frame):
    if frame.duplicated(['trade_date','ts_code']).any():
        raise ValueError('Duplicate industry/day')
    prices=frame.pivot(index='trade_date',columns='ts_code',values='close').sort_index()
    cap=frame.pivot(index='trade_date',columns='ts_code',values='float_mv').reindex_like(prices)/1e8
    turnover=frame.pivot(index='trade_date',columns='ts_code',values='turnover_rate').reindex_like(prices)/100
    if not (np.isfinite(prices).all().all() and np.isfinite(cap).all().all() and np.isfinite(turnover).all().all()):
        raise ValueError('Incomplete industry inputs')
    if (prices<=0).any().any() or (cap<=0).any().any() or (turnover<0).any().any():
        raise ValueError('Invalid industry inputs')
    activity=(cap*turnover).sum(axis=1)
    out=pd.DataFrame({'cap':cap.sum(axis=1),'activity':activity})
    for n in [90,120,250]:
        out[f'memory{n}']=activity.rolling(n,min_periods=n).mean()
    base=7.695442042177039*(prices*(cap*turnover/prices).ewm(span=20,adjust=False).mean()).sum(axis=1)
    out.index=pd.to_datetime(out.index.astype(str))
    base.index=out.index
    return out,base


def main():
    frame=pd.read_csv(ROOT/'back_test_data/ths_daily/all_industries.csv')
    x,base=features(frame)
    # Prefix invariance: adding future rows cannot revise earlier features.
    prefix,_=features(frame[frame.trade_date<=20251231])
    pd.testing.assert_frame_equal(x.loc[prefix.index],prefix)
    with connect() as db:
        target=pd.DataFrame([dict(r) for r in db.execute("SELECT d.date,d.close FROM indicator_daily d JOIN indicators i ON i.id=d.indicator_id WHERE i.code='0AMV' ORDER BY d.date")])
    target.index=pd.to_datetime(target.date)
    y=target.close.reindex(x.index)
    usable=x.notna().all(axis=1)&y.notna()&(x>0).all(axis=1)&y.gt(0)
    x=x.loc[usable];y=y.loc[usable];base=base.loc[usable]
    train=x.index<=pd.Timestamp('2025-12-31')
    if train.sum()<30:raise ValueError('Insufficient training after 250-day warmup')
    logs=np.log(x)
    mean=logs.loc[train].mean();std=logs.loc[train].std(ddof=0)
    if (std<=0).any():raise ValueError('Constant training input')
    z=(logs-mean)/std
    model=Ridge(alpha=1.0).fit(z.loc[train],np.log(y.loc[train]))
    pred=pd.Series(np.exp(model.predict(z)),index=x.index)
    baseline_scale=float(np.exp(np.log(y.loc[train]/base.loc[train]).mean()))
    predictions={'original':y,'THS_EMA20':base,'THS_EMA20_rescaled':base*baseline_scale,'log_memory':pred}
    out=pd.DataFrame(predictions)
    def metric(p,mask):
        actual_ret=y.pct_change(fill_method=None); pred_ret=p.pct_change(fill_method=None)
        rmask=mask&actual_ret.notna()&pred_ret.notna()
        return {'rows':int(mask.sum()),'mape_pct':float((p[mask]/y[mask]-1).abs().mean()*100),
            'return_corr':float(pred_ret[rmask].corr(actual_ret[rmask])),
            'return_mae_pp':float((pred_ret[rmask]-actual_ret[rmask]).abs().mean()*100),
            'direction_accuracy_pct':float((np.sign(pred_ret[rmask])==np.sign(actual_ret[rmask])).mean()*100)}
    periods={'train':train,'test_2026':~train,'test_2026_H1':(~train)&(x.index<'2026-07-01'),'test_2026_H2':x.index>='2026-07-01'}
    results={'input_first_date':str(frame.trade_date.min()),'input_last_date':str(frame.trade_date.max()),
        'first_prediction':str(x.index[0].date()),'industries':int(frame.ts_code.nunique()),
        'train_end':'2025-12-31','ridge_alpha':1.0,'intercept':float(model.intercept_),
        'coefficients':dict(zip(x.columns,model.coef_.tolist())),
        'log_training_mean':mean.to_dict(),'log_training_std':std.to_dict(),
        'power_exponents':dict(zip(x.columns,(model.coef_/std).tolist())),
        'baseline_rescale':baseline_scale,
        'metrics':{name:{period:metric(p,mask) for period,mask in periods.items()} for name,p in predictions.items() if name!='original'},
        'limitations':['Screenshot lacks memory definition, standardization, intercept and full coefficients; this is a new approximation.',
            'Free float cap unavailable and omitted; cap * turnover is a trading-value proxy, not observed turnover amount.',
            'Industry aggregation can differ from stock aggregation and constituent overlap was not deduplicated.',
            'Only 498 industry trading days; 250-day warmup leaves a short training period.',
            '2026 is chronological out-of-fit data but has been inspected in prior project research.',
            'No strategy return claim and no intraday/pre-close availability assumed.'],
        'checks':{'prefix_invariance':True,'train_only_scaling_and_fit':True,'no_original_amv_predictors':True,'production_unchanged':True}}
    folder=ROOT/'back_test_data/amv_log_memory';folder.mkdir(exist_ok=True)
    (folder/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    out.to_csv(folder/'predictions.csv',index_label='date')
    x.to_csv(folder/'features.csv',index_label='date')
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
    out[['original','THS_EMA20','log_memory']].plot(ax=axes[0],color=['black','orange','royalblue'])
    for col,color in [('THS_EMA20','orange'),('log_memory','royalblue')]:
        ((out[col]/y-1)*100).plot(ax=axes[1],label=col,color=color)
    axes[0].set_title('Screenshot-inspired log-memory model vs THS EMA20')
    axes[1].set_ylabel('Relative error (%)');axes[1].axhline(0,color='grey');axes[1].legend()
    for ax in axes:ax.axvline(pd.Timestamp('2026-01-01'),color='grey',linestyle='--');ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(folder/'comparison.png',dpi=150);plt.close(fig)
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
