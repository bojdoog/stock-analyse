"""Chronological AMV reconstruction with independent indicators, no AMV input lags."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
def raw(name):
    j=json.loads((ROOT/'raw'/f'{name}.json').read_text(encoding='utf8'))
    f=pd.DataFrame(j['rows']);f['date']=pd.to_datetime(f.trade_date.astype(str));return f
f=pd.read_csv(BASE/'ths_daily/all_industries.csv');f['date']=pd.to_datetime(f.trade_date.astype(str))
assert not f.duplicated(['date','ts_code']).any()
close=f.pivot(index='date',columns='ts_code',values='close').sort_index();dates=close.index
mv=f.pivot(index='date',columns='ts_code',values='float_mv').reindex(dates)/1e8
tau=f.pivot(index='date',columns='ts_code',values='turnover_rate').reindex(dates)/100
assert np.isfinite(close).all().all() and np.isfinite(mv).all().all() and np.isfinite(tau).all().all()
snapshot=json.loads((BASE/'strategy_failure_research/generalization_inputs.json').read_text(encoding='utf8'))
target=pd.DataFrame(snapshot['amv']);target['date']=pd.to_datetime(target.date)
y=target.set_index('date').close.reindex(dates);assert y.notna().all()
train=(dates>='2024-12-10')&(dates<='2025-06-30');valid=(dates>='2025-07-01')&(dates<='2025-12-31');test=dates>='2026-01-01'
periods={'train':train,'validation':valid,'test':test,'test_H1':test&(dates<'2026-07-01'),'test_H2':dates>='2026-07-01'}
q=mv*tau/close;base=7.695442042177039*(q.ewm(span=20,adjust=False).mean()*close).sum(axis=1)
X=pd.DataFrame(index=dates);groups={}
def add(group,name,series):
    X[name]=series.reindex(dates);groups.setdefault(group,[]).append(name)
ret=close.pct_change(fill_method=None)
for window in [5,20]:
    add('breadth',f'up_fraction_ema{window}',(ret>0).mean(axis=1).ewm(span=window,adjust=False).mean())
    add('breadth',f'above_ma{window}',(close>close.rolling(window).mean()).mean(axis=1))
add('breadth','industry_dispersion',ret.std(axis=1).ewm(span=20,adjust=False).mean())
add('activity','log_turnover_shock',np.log((mv*tau).sum(axis=1)/(mv*tau).sum(axis=1).ewm(span=20,adjust=False).mean()))
add('activity','log_cap_over_activity',np.log(mv.sum(axis=1)/base))
add('activity','turnover_concentration',((mv*tau).div((mv*tau).sum(axis=1),axis=0)**2).sum(axis=1).ewm(span=20,adjust=False).mean())
market=pd.concat([raw('market_'+s) for s in ['20240910','20250101','20260101']]);assert not market.duplicated(['date','ts_code']).any()
mp=market.pivot(index='date',columns='ts_code',values='amount').reindex(dates)
amount=mp[['SH_A','SH_STAR','SZ_MAIN','SZ_GEM']].sum(axis=1,min_count=4)
add('activity','log_market_amount_over_base',np.log(amount.ewm(span=20,adjust=False).mean()/base))
indices={code:raw('index_'+code).set_index('date').close.reindex(dates) for code in ['000300.SH','000905.SH','000852.SH','932000.CSI','399006.SZ','000001.SH']}
for code in ['000905.SH','000852.SH','932000.CSI','399006.SZ']:
    add('style','log_style_'+code,np.log(indices[code]/indices['000300.SH']))
for code in ['000001.SH','399001.SZ','000905.SH','399006.SZ']:
    b=raw('basic_'+code).set_index('date').reindex(dates)
    add('valuation','log_pb_'+code,np.log(b.pb))
    add('free_float','free_float_ratio_'+code,b.free_share/b.float_share)
    add('free_float','turnover_free_ratio_'+code,b.turnover_rate_f/b.turnover_rate)
margin=raw('margin');margin=margin[margin.exchange_id.isin(['SSE','SZSE'])]
counts=margin.groupby('date').size()
mg=margin.groupby('date')[['rzye','rzmre','rzche','rqye']].sum()
mg.loc[counts.ne(2),:]=np.nan
mg=mg.reindex(dates).shift(1)
add('margin','log_margin_balance_over_cap_lag1',np.log(mg.rzye/(mv.sum(axis=1)*1e8)))
add('margin','margin_buy_intensity_lag1',mg.rzmre/(amount.shift(1)*1e8))
add('margin','margin_net_change_lag1',(mg.rzmre-mg.rzche)/mg.rzye)
add('margin','short_balance_ratio_lag1',mg.rqye/mg.rzye)
# Live endpoint denied access; use explicitly identified already archived research data.
flow=pd.read_csv(BASE/'moneyflow_mkt_dc/20240910_20261001.csv');flow['date']=pd.to_datetime(flow.trade_date.astype(str));flow=flow.set_index('date').reindex(dates)
for field in ['net_amount_rate','buy_elg_amount_rate']:
    for span in [5,20]:add('flow',f'{field}_ema{span}',flow[field].ewm(span=span,adjust=False).mean())
for span in [10,20,40]:
    add('flow_simple'+str(span),'net_rate_only_ema'+str(span),flow.net_amount_rate.ewm(span=span,adjust=False).mean())
for col in groups['flow']:
    add('flow_lag1',col+'_lag1',X[col].shift(1))
X=X.replace([np.inf,-np.inf],np.nan)
quality={col:{'missing_total':int(X[col].isna().sum()),'missing_train':int(X.loc[train,col].isna().sum()),'missing_test':int(X.loc[test,col].isna().sum())} for col in X}
# Missing values use TRAIN medians only, never future observations.
med=X.loc[train].median();assert med.notna().all();filled=X.fillna(med);mean=filled.loc[train].mean();std=filled.loc[train].std().replace(0,1);Z=(filled-mean)/std
residual=np.log(y/base)
def metrics(p,mask):
    yr=y.pct_change(fill_method=None);pr=p.pct_change(fill_method=None);err=p[mask]/y[mask]-1
    return {'n':int(mask.sum()),'mape_pct':float(err.abs().mean()*100),'log_rmse':float(np.sqrt(np.mean(np.log(p[mask]/y[mask])**2))),
      'return_corr':float(yr[mask].corr(pr[mask])),'return_mae_pp':float((yr[mask]-pr[mask]).abs().mean()*100),
      'direction_pct':float((np.sign(yr[mask])==np.sign(pr[mask])).mean()*100)}
predictions={'old_ema20':base};models=[]
def record(name,p,extra):
    predictions[name]=p;models.append({'name':name,**extra,'metrics':{period:metrics(p,mask) for period,mask in periods.items()}})
record('old_ema20',base,{'group':'baseline'})
record('ema20_recalibrated',base*np.exp(residual[train].mean()),{'group':'baseline'})
for group,cols in {**groups,'all':list(X.columns)}.items():
    for alpha in [1,10,100]:
        model=Ridge(alpha=alpha).fit(Z.loc[train,cols],residual[train]);p=base*np.exp(model.predict(Z[cols]));name=f'{group}_ridge{alpha}'
        record(name,p,{'group':group,'alpha':alpha,'features':cols,'intercept':float(model.intercept_),'coefficients':dict(zip(cols,model.coef_.tolist()))})
chosen=min(models,key=lambda m:m['metrics']['validation']['log_rmse']);winner=chosen['name']
families=[min([m for m in models if m['group']==g],key=lambda m:m['metrics']['validation']['log_rmse']) for g in ['baseline',*groups,'all']]
correlations=[]
for col in X:
    correlations.append({'feature':col,'group':next(g for g,c in groups.items() if col in c),**{p:float(X.loc[mask,col].corr(residual[mask])) for p,mask in periods.items()}})
def signals(s):
    r=s.pct_change(fill_method=None)*100;ma=s.rolling(10).mean();enter=(r.gt(4)|(r.gt(0)&r.shift(1).gt(0)&(r+r.shift(1)).gt(4)))&s.gt(ma);leave=r.lt(-2.3)|s.lt(ma)
    state=False;states=[];entries=[];exits=[]
    for e,x in zip(enter,leave):
        a=b=False
        if not state and e:state=True;a=True
        elif state and x:state=False;b=True
        states.append(state);entries.append(a);exits.append(b)
    return np.array(states),np.array(entries),np.array(exits)
truth=signals(y);signal_metrics=[]
for name in ['old_ema20',winner]:
    state,entry,exit=signals(predictions[name])
    for period,mask in [('validation',valid),('test',test)]:
        signal_metrics.append({'name':name,'period':period,'state_agreement_pct':float((state[mask]==truth[0][mask]).mean()*100),'actual_entries':int(truth[1][mask].sum()),'predicted_entries':int(entry[mask].sum()),'same_day_entries':int((entry&truth[1]&mask).sum()),'actual_exits':int(truth[2][mask].sum()),'same_day_exits':int((exit&truth[2]&mask).sum()),'extra_entry_dates':dates[entry&~truth[1]&mask].strftime('%Y-%m-%d').tolist()})
out=pd.DataFrame({'amv':y,'old_ema20':base,'selected':predictions[winner]});out.to_csv(ROOT/'predictions.csv',index_label='date',encoding='utf-8-sig')
X.to_csv(ROOT/'features.csv',index_label='date',encoding='utf-8-sig')
output={'winner':winner,'last_date':str(dates[-1].date()),'target_count':len(y),'train_start':'2024-12-10','train_end':'2025-06-30','validation_end':'2025-12-31','test_start':'2026-01-01',
 'families':families,'models':models,'residual_correlations':correlations,'signal_metrics':signal_metrics,'feature_quality':quality,
 'formula':{'description':'old_ema20 * exp(intercept + sum(coef * ((feature-training_mean)/training_std))); coefficients chosen on validation only','selected':chosen,'training_mean':mean.to_dict(),'training_std':std.to_dict(),'training_fill_median':med.to_dict()},
 'limitations':['Reconstruction only, not return forecasting or recovery of proprietary formula. No AMV lags/volume/amount used as predictors.',
 'Daily industry and basic statistics are published after close: not verified intraday or pre-close executable.',
 'Margin variables shifted one exchange session for next-day disclosure. Northbound fields excluded due to unresolved post-2024 disclosure semantics.',
 'Moneyflow endpoint currently denies access; flow features from named local archive, not a successful fresh fetch.',
 'Index and SW historical minute probes denied permission. No claim to have reconstructed independent intraday OHLC.',
 '2026 is chronologically held out for this fit but has been inspected in prior project research; not an untouched prospective holdout.',
 'Training imputation only. Fixed contemporary industry classification may embed historical universe issues.'],
 'checks':{'unique_industry_dates':True,'finite_original_features':True,'target_aligned':True,'no_target_predictors':True,'train_only_scaler_and_fit':True}}
(ROOT/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
fig,axes=plt.subplots(2,1,figsize=(13,7),sharex=True)
out.loc[dates>='2024-12-10'].plot(ax=axes[0],color=['black','orange','royalblue'],linewidth=1);axes[0].set_title('AMV reconstruction: original / old EMA20 / validation-selected model')
for name,color in [('old_ema20','orange'),(winner,'royalblue')]:((predictions[name]/y-1)*100).loc[dates>='2024-12-10'].plot(ax=axes[1],label=name,color=color)
for ax in axes:ax.axvline(pd.Timestamp('2026-01-01'),color='grey',linestyle='--');ax.grid(alpha=.2)
axes[1].axhline(0,color='black',linewidth=.5);axes[1].set_ylabel('Error (%)');axes[1].legend();fig.tight_layout();fig.savefig(ROOT/'comparison.png',dpi=150);plt.close(fig)
print(json.dumps({'winner':winner,'families':[{'name':m['name'],'metrics':m['metrics']} for m in families],'signals':signal_metrics},indent=2))
