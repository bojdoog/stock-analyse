"""Causal event-driven execution/risk study. Production strategy is unchanged."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
INPUT=json.loads((ROOT/'robust_execution_inputs.json').read_text(encoding='utf8'))
AMV=pd.DataFrame(INPUT['amv']).set_index('date').sort_index()
DATES=AMV.loc['2019-01-01':'2026-12-31'].index.tolist()
SERIES={s['name']:pd.DataFrame(s['data']).set_index('date').sort_index() for s in INPUT['etfs'] if not s['id'].startswith('sh')}
NAMES=list(SERIES);BANK='银行ETF'
CLOSE=pd.DataFrame({n:f.close for n,f in SERIES.items()}).reindex(AMV.index)
RET=CLOSE.pct_change(fill_method=None)
QUOTES={n:f.to_dict('index') for n,f in SERIES.items()}
ZONES=INPUT['baseline']['zones']
BASE_TRADES={t['start_date']:t for t in INPUT['baseline']['trades']}


def causal_zones(start=4.,end=-2.3):
    prices=AMV.loc[DATES,'close'];ma=prices.rolling(10).mean();ret=prices.pct_change()*100
    state=False;zones=[{'start_date':DATES[0],'type':'bear'}]
    for i,d in enumerate(DATES):
        enter=(ret.iloc[i]>start or (i>1 and ret.iloc[i]>0 and ret.iloc[i-1]>0 and ret.iloc[i]+ret.iloc[i-1]>start)) and prices.iloc[i]>ma.iloc[i]
        if not state and enter:state=True;zones.append({'start_date':d,'type':'bull'})
        elif state and (ret.iloc[i]<end or prices.iloc[i]<ma.iloc[i]):state=False;zones.append({'start_date':d,'type':'bear'})
    return zones


def selection(date,lookback=20,day_weight=.5):
    i=AMV.index.get_loc(date)
    candidates=[]
    for n in NAMES:
        if n==BANK:continue
        p=CLOSE[n].iloc[i]; prev=CLOSE[n].iloc[i-1] if i else np.nan
        old=CLOSE[n].iloc[i-lookback] if i>=lookback else np.nan
        if not(p>0 and prev>0):continue
        candidates.append((n,p/prev-1,p/old-1 if old>0 else None))
    eligible=[r for r in candidates if r[2] is not None]
    def score(r):
        return day_weight*sum(c[1]<r[1] for c in candidates)/max(1,len(candidates)-1)+(1-day_weight)*sum(c[2]<r[2] for c in eligible)/max(1,len(eligible)-1)
    chosen=[r[0] for r in sorted(eligible,key=score,reverse=True)[:5]]
    for r in sorted(candidates,key=lambda r:r[1],reverse=True):
        if len(chosen)<5 and r[0] not in chosen:chosen.append(r[0])
    return chosen


def allocation(names,date,c):
    w=np.full(len(names),.2)
    history=RET.loc[:date,names].iloc[-c.get('window',40):]
    if c.get('invvol') and len(names)==5 and len(history)==c.get('window',40) and history.notna().all().all():
        vol=history.std(ddof=1).to_numpy()
        if (vol>0).all():
            raw=1/vol; free=list(range(len(names))); remain=1.; cap=np.zeros(len(names))
            while free:
                normalized=raw[free]/raw[free].sum()*remain
                over=[j for j,v in zip(free,normalized) if v>.3]
                if not over:
                    cap[free]=normalized;break
                for j in over:cap[j]=.3;remain-=.3;free.remove(j)
            w=.5*w+.5*cap
    exposure=c.get('exposure',1.)
    if c.get('target') and len(history)==c.get('window',40) and history.notna().all().all():
        vol=float((history.to_numpy()@w).std(ddof=1)*np.sqrt(252))
        if vol>0:exposure*=min(1,c['target']/vol)
    return w*exposure


def simulate(config=None,mode='same_close',cost=0.,arm=.135,trail=.022,lookback=20,day_weight=.5):
    c=config or {};plans={}
    for zone in (causal_zones(c.get('start',4.),c.get('end',-2.3)) if 'start' in c or 'end' in c else ZONES):
        d=zone['start_date'];bull=zone['type']=='bull'
        if bull:
            names=selection(d,lookback,day_weight);w=allocation(names,d,c)
        else:
            enabled=int(d[:4])>=2024
            names=[BANK] if enabled else [];w=np.array([c.get('bank_weight',1.)]) if enabled else np.array([])
        plans[d]={'names':names,'weights':w,'bull':bull,'date':d}
    cash=1.;units={};last={};entry={};pending=[];token=0;bull=False
    capital=1.;peak=1.;armed=False;protected=False;acted=set();streak={};age=0
    events=[];curve=[];turnover=0.;fees=0.;last_signal=None
    def quote(n,d,field):
        value=QUOTES[n].get(d,{}).get(field)
        return float(value) if value is not None and np.isfinite(value) and value>0 else None
    def value():return cash+sum(u*last[n] for n,u in units.items())
    def sell(n,fraction,d,field,reason):
        nonlocal cash,turnover,fees
        p=quote(n,d,field)
        if p is None:raise ValueError(('Missing execution quote',n,d,field))
        quantity=units.get(n,0)*fraction;gross=quantity*p
        units[n]=units.get(n,0)-quantity;cash+=gross*(1-cost);turnover+=gross;fees+=gross*cost
        if quantity:events.append({'date':d,'name':n,'reason':reason,'side':'sell','gross':gross})
    def execute(order,d,field):
        nonlocal cash,units,entry,capital,peak,armed,protected,acted,streak,age,bull,token,last_signal,turnover,fees
        if order['kind']=='switch':
            for n in list(units):sell(n,1,d,field,'switch')
            units={};entry={};capital=cash;peak=1.;armed=False;protected=False;acted=set();streak={};age=0
            plan=order['plan'];bull=plan['bull'];token+=1;last_signal=plan['date']
            for n,w in zip(plan['names'],plan['weights']):
                p=quote(n,d,field)
                if p is None:raise ValueError(('Missing entry quote',n,d,field))
                gross=capital*float(w)/(1+cost);units[n]=gross/p;entry[n]=p;last[n]=p
                cash-=gross*(1+cost);turnover+=gross;fees+=gross*cost
                if gross:events.append({'date':d,'name':n,'reason':'switch','side':'buy','gross':gross,'signal':plan['date']})
        elif order['token']==token:
            if order['kind']=='protect':
                for n in list(units):sell(n,.5,d,field,'protection')
            else:
                sell(order['name'],.5,d,field,'relative_weakness')
    for i,d in enumerate(DATES):
        for n in units:
            p=quote(n,d,'open' if mode=='next_open' else 'close')
            if p is not None:last[n]=p
        due=[o for o in pending if o['due']==i];pending=[o for o in pending if o['due']!=i]
        for o in due:execute(o,d,'open' if mode=='next_open' else 'close')
        for n in units:
            p=quote(n,d,'close')
            if p is not None:last[n]=p
        # Close-derived signals act immediately only in the optimistic parity mode.
        order=None
        if d in plans:
            order={'kind':'switch','plan':plans[d]}
            if mode=='same_close':execute(order,d,'close')
            else:pending.append({**order,'due':i+1})
        if bull and units and order is None:
            age+=1;nav=value()/capital;peak=max(peak,nav)
            if nav-1>=arm-1e-12:armed=True
            if c.get('protection',True) and not protected and armed and 1-nav/peak>=trail-1e-12:
                protected=True;o={'kind':'protect','token':token}
                if mode=='same_close':execute(o,d,'close')
                else:pending.append({**o,'due':i+1})
            if c.get('relative') and age>=5:
                gains={n:last[n]/p-1 for n,p in entry.items()};mid=float(np.median(list(gains.values())))
                for n,g in gains.items():
                    if n in acted or units.get(n,0)<=1e-14:continue
                    streak[n]=streak.get(n,0)+1 if g<0 and g<mid-c['relative'] else 0
                    if streak[n]>=3:
                        acted.add(n);o={'kind':'individual','token':token,'name':n}
                        if mode=='same_close':execute(o,d,'close')
                        else:pending.append({**o,'due':i+1})
        nav=value();assert cash>-1e-8 and nav>0 and all(u>=-1e-10 for u in units.values())
        curve.append(nav)
    s=pd.Series(curve,index=pd.to_datetime(DATES));returns=s.pct_change().fillna(s.iloc[0]-1)
    def summary(v):
        before=s.loc[s.index<v.index[0]];start=float(before.iloc[-1]) if len(before) else 1.
        scaled=v/start;dd=1-scaled/np.maximum.accumulate(np.r_[1.,scaled.to_numpy()])[1:]
        years=(v.index[-1]-v.index[0]).days/365.25
        return {'total_pct':float((scaled.iloc[-1]-1)*100),'dd_pct':float(dd.max()*100),
                'cagr_pct':float((scaled.iloc[-1]**(1/years)-1)*100) if years>0 else None}
    stats=summary(s);stats.update(mode=mode,cost_bps=cost*10000,config=c,arm=arm,trail=trail,lookback=lookback,day_weight=day_weight,
        annual={str(y):float(((1+r).prod()-1)*100) for y,r in returns.groupby(returns.index.year)},
        early=summary(s.loc[:'2023-12-31']),recent=summary(s.loc['2024-01-01':]),
        sales=len([e for e in events if e['side']=='sell']),fees_paid=fees,turnover=turnover)
    return stats,s,events


def main():
    mismatch=[]
    for t in INPUT['baseline']['trades']:
        if t['type']=='bull' and selection(t['start_date'])!=[h['name'] for h in t['holdings']]:
            mismatch.append(t['start_date'])
    assert not mismatch,('Future-endpoint eligibility changed selections',mismatch)
    parity,s,_=simulate()
    existing=pd.Series({p['date']:p['nav'] for p in INPUT['baseline']['navSeries']})
    common=existing.index.intersection(DATES)
    err=float(np.max(np.abs(s.reindex(pd.to_datetime(common)).to_numpy()-existing.loc[common].to_numpy())))
    assert err<2e-6,('Baseline parity failed',err,parity['total_pct'])
    configs={'baseline':{},'exposure80':{'exposure':.8},'exposure90':{'exposure':.9},
        'inverse_vol40':{'invvol':True,'window':40},'target20_vol40':{'target':.20,'window':40},
        'target25_vol40':{'target':.25,'window':40},'relative5':{'relative':.05},
        'invvol_target20':{'invvol':True,'target':.20,'window':40},'bank_half':{'bank_weight':.5},
        'bank_cash':{'bank_weight':0.},'no_protection':{'protection':False}}
    results=[];curves={}
    for name,c in configs.items():
        for mode in ['same_close','next_open','next_close']:
            r,v,_=simulate(c,mode,.0005);r['name']=name;results.append(r);curves[name+'_'+mode]=v
    # Neighbourhood, not exhaustive optimization. No winner selected using future years.
    sensitivity=[]
    for name in ['baseline','exposure80','inverse_vol40','target20_vol40','relative5']:
        for arm in [.12,.135,.15]:
            for trail in [.018,.022,.027]:
                r,_,_=simulate(configs[name],'next_open',.0005,arm,trail);r['name']=name;sensitivity.append(r)
    for name in ['baseline','target20_vol40']:
        for lookback in [15,20,30]:
            for day_weight in [.25,.5,.75]:
                r,_,_=simulate(configs[name],'next_open',.0005,lookback=lookback,day_weight=day_weight);r.update(name=name,kind='ranking');sensitivity.append(r)
    for target in [.18,.20,.22,.25]:
        for window in [20,40,60]:
            r,_,_=simulate({'target':target,'window':window},'next_open',.0005);r.update(name='volatility_grid',kind='volatility');sensitivity.append(r)
    stress=[]
    for name,c in configs.items():
        r,_,_=simulate(c,'next_open',.001);r['name']=name;stress.append(r)
    output={'last_date':DATES[-1],'first_date':DATES[0],'same_close_no_cost':parity,
        'checks':{'production_nav_max_abs_error':err,'causal_selection_matches_all_bull_entries':True,'nonnegative_cash_and_positions':True},
        'results':results,'sensitivity':sensitivity,'cost_stress':stress,
        'conventions':['Current database universe; not a reconstructed point-in-time ETF universe.',
        'Ranking uses only signal close and prior data; fixed until next bull interval. Volatility uses returns through signal close.',
        'Same-close is optimistic parity only; next-open/next-close delay all entries, exits and protection sales one AMV session.',
        'Costs 5 bps each side, stress 10 bps; assumed, not calibrated. Cash earns zero, no leverage, no intraday stop fills.',
        'Target volatility scales bull entry weights once per interval; no daily rebalancing. Bank unchanged unless specified.',
        'Inverse volatility blends 50% equal/50% capped inverse-vol weights. Relative weakness: loss AND 5pp behind basket median for 3 closes after 5 held sessions; sell half once.',
        'Annual returns use calendar-year mark-to-market, unlike production entry-year attribution. Drawdown uses daily close NAV.',
        'All years previously inspected. Exploratory comparison, not independent prospective validation; 2026 partial.',
        'Uses stored adjusted ETF OHLC; corporate-action and AMV publication-time provenance not independently audited.']}
    (ROOT/'robust_execution_results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    pd.DataFrame(curves).to_csv(ROOT/'robust_execution_curves.csv',index_label='date')
    print(json.dumps({'baseline':parity,'checks':output['checks'],'results':[{k:r[k] for k in ['name','mode','total_pct','dd_pct','cagr_pct']} for r in results]},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
