"""Neighbourhood and equal-capital ensembles; no production changes."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from robust_execution_research import ROOT,simulate,causal_zones,ZONES

assert [(x['start_date'],x['type']) for x in causal_zones()]==[(x['start_date'],x['type']) for x in ZONES]

def summary(v):
    years=(v.index[-1]-v.index[0]).days/365.25
    dd=1-v/np.maximum.accumulate(np.r_[1.,v.to_numpy()])[1:]
    returns=v.pct_change().fillna(v.iloc[0]-1)
    return {'total_pct':float((v.iloc[-1]-1)*100),'dd_pct':float(dd.max()*100),'cagr_pct':float((v.iloc[-1]**(1/years)-1)*100),
            'worst_dd_date':str(dd.idxmax().date()),'annual':{str(y):float(((1+r).prod()-1)*100) for y,r in returns.groupby(returns.index.year)}}

results=[];curves={};grid=[]
for mode in ['same_close','next_open','next_close']:
    for name,c in [('baseline',{}),('target20_vol60',{'target':.2,'window':60}),('inverse_vol40',{'invvol':True,'window':40})]:
        r,v,_=simulate(c,mode,.0005);r['name']=name;results.append(r);curves[name+'_'+mode]=v
    for name,configs in [('ranking_ensemble',[(15,.5),(20,.5),(30,.5)]),('ranking_weight_ensemble',[(20,.25),(20,.5),(20,.75)])]:
        vs=[simulate({},mode,.0005,lookback=n,day_weight=w)[1] for n,w in configs]
        v=sum(vs)/len(vs);r=summary(v);r.update(name=name,mode=mode);results.append(r);curves[name+'_'+mode]=v
    # Three risk budgets, equal initial capital, each has independent protection.
    vs=[simulate({'target':t,'window':60},mode,.0005)[1] for t in [.18,.20,.22]]
    v=sum(vs)/3;r=summary(v);r.update(name='risk_budget_ensemble',mode=mode);results.append(r);curves['risk_budget_ensemble_'+mode]=v
for base in [{},{'target':.2,'window':60}]:
    for start in [3.5,4.,4.5]:
        for end in [-2.,-2.3,-2.6]:
            r,_,_=simulate({**base,'start':start,'end':end},'next_open',.0005);grid.append(r)
stress=[]
for c in [{},{'target':.2,'window':60},{'invvol':True,'window':40}]:
    r,_,_=simulate(c,'next_open',.001);stress.append(r)
out={'results':results,'signal_grid':grid,'cost_stress':stress,'ensemble_convention':'Equal initial capital across independent strategies; no daily cross-sleeve rebalancing; costs included in each sleeve.'}
(ROOT/'robust_execution_followup.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
pd.DataFrame(curves).to_csv(ROOT/'robust_execution_followup_curves.csv',index_label='date')
fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
for name,color in [('baseline_next_open','black'),('baseline_next_close','grey'),('target20_vol60_next_open','royalblue'),('target20_vol60_next_close','orange')]:
    v=curves[name];axes[0].plot(v.index,v,label=name,color=color)
    dd=(v/np.maximum.accumulate(np.r_[1.,v.to_numpy()])[1:]-1)*100;axes[1].plot(v.index,dd,color=color)
axes[0].set_ylabel('NAV');axes[0].legend();axes[1].set_ylabel('Drawdown (%)')
axes[0].set_title('Execution and risk control: 5 bps per side, 2019 to 2026-10-08')
for ax in axes:ax.grid(alpha=.2)
fig.tight_layout();fig.savefig(ROOT/'robust_execution_comparison.png',dpi=150);plt.close(fig)
print(json.dumps([{k:r[k] for k in ['name','mode','total_pct','dd_pct','cagr_pct']} for r in results],ensure_ascii=False))
