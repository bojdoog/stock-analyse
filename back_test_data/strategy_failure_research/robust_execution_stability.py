import json
from robust_execution_research import ROOT,simulate
import numpy as np
import pandas as pd

def summary(v):
    return {'total_pct':float((v.iloc[-1]-1)*100),'dd_pct':float((1-v/np.maximum.accumulate(np.r_[1.,v.to_numpy()])[1:]).max()*100),
            'cagr_pct':float((v.iloc[-1]**(365.25/(v.index[-1]-v.index[0]).days)-1)*100)}

rows=[];curves={}
for mode in ['same_close','next_open','next_close']:
    for name,cs in [('vol_window_ensemble',[{'target':.2,'window':w} for w in [20,40,60]]),
                    ('signal_ensemble',[{'start':s} for s in [3.5,4.,4.5]]),
                    ('vol_signal_ensemble',[{'start':s,'target':.2,'window':40} for s in [3.5,4.,4.5]])]:
        v=sum(simulate(c,mode,.0005)[1] for c in cs)/len(cs)
        r=summary(v);r.update(name=name,mode=mode);rows.append(r);curves[name+'_'+mode]=v
grid=[]
for target in [.18,.20,.22]:
    for window in [20,40,60]:
        r,_,_=simulate({'target':target,'window':window},'next_close',.0005);grid.append(r)
signals=[]
for start in [3.5,4.,4.5]:
    for end in [-2.,-2.3,-2.6]:
        r,_,_=simulate({'target':.2,'window':40,'start':start,'end':end},'next_open',.0005);signals.append(r)
r,_,_=simulate({'target':.2,'window':40},'next_open',.001)
out={'ensembles':rows,'next_close_grid':grid,'signal_grid40':signals,'cost_stress40':r}
(ROOT/'robust_execution_stability.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
pd.DataFrame(curves).to_csv(ROOT/'robust_execution_ensemble_curves.csv',index_label='date')
print(json.dumps(rows))
print('next close grid',[(x['config'],round(x['total_pct'],1),round(x['dd_pct'],2)) for x in grid])
