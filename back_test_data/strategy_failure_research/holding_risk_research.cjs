// Research only. Fixed selections/signals, causal holding exits and ex-ante weights.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
const input=JSON.parse(fs.readFileSync(path.join(__dirname,'generalization_inputs.json'),'utf8'));
const mod={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:mod,exports:mod.exports});
const engine=mod.exports,params={...engine.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,rankingMethod:'etf_blend20',weights:[20,20,20,20,20],leverageMultiplier:1,bearStartYear:2024,bearBuyBank:true,profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
const base=engine.runBacktest(input.amv,input.etfs,params);
const historyDates=[...new Set(input.etfs.find(x=>x.id==='512800').data.map(x=>x.date))].sort();
const dates=historyDates.filter(d=>d>='2019-01-01'&&d<=input.amv.at(-1).date),sessions=new Set(dates);
const prices=new Map(input.etfs.map(s=>[s.name,new Map(s.data.map(x=>[x.date,x.close]))]));
const get=(name,date)=>{const p=prices.get(name)?.get(date);return p>0?p:null;};
const sum=a=>a.reduce((s,x)=>s+x,0),product=ts=>ts.reduce((v,t)=>v*(1+t.return),1);
const median=a=>{const b=[...a].sort((x,y)=>x-y);return b.length%2?b[(b.length-1)/2]:(b[b.length/2-1]+b[b.length/2])/2;};
function weights(t,config){
 const normal=t.holdings.map(h=>h.weight);if(!config.window)return {weights:normal};
 const history=historyDates.filter(d=>d<t.start_date).slice(-config.window-1);
 const vols=t.holdings.map(h=>{const p=history.map(d=>get(h.name,d));if(p.length!==config.window+1||p.some(x=>x===null))return null;const r=p.slice(1).map((x,i)=>x/p[i]-1),mean=sum(r)/r.length;return Math.sqrt(sum(r.map(x=>(x-mean)**2))/(r.length-1));});
 if(vols.some(x=>!x||!Number.isFinite(x)))return {weights:normal,fallback:true,vols};
 const inverse=vols.map(v=>1/v),raw=inverse.map(v=>v/sum(inverse));
 // Cap inverse-vol weights at 30%, redistributing excess proportionally.
 let free=raw.map((_,i)=>i),remaining=1,capped=raw.map(()=>0);
 while(free.length){const denom=sum(free.map(i=>raw[i])),over=free.filter(i=>remaining*raw[i]/denom>.3+1e-12);if(!over.length){free.forEach(i=>capped[i]=remaining*raw[i]/denom);break;}over.forEach(i=>{capped[i]=.3;remaining-=.3;});free=free.filter(i=>!over.includes(i));}
 const blend=config.blend??1,w=capped.map((v,i)=>blend*v+(1-blend)*normal[i]);assert(Math.abs(sum(w)-1)<1e-10);assert(w.every(v=>v<=.3+1e-10));return {weights:w,vols};
}
function simulate(t,config){
 const ds=input.amv.filter(p=>p.date>=t.start_date&&p.date<=t.end_date).map(p=>p.date);
 const alloc=weights(t,config),entry=t.holdings.map(h=>get(h.name,t.start_date));assert(entry.every(x=>x>0));
 let units=alloc.weights.map((w,i)=>w/entry[i]),cash=1-sum(alloc.weights),last=[...entry],peak=1,armed=false,protectedOnce=false;
 const acted=units.map(()=>false),streak=units.map(()=>0),events=[],curve=[];let age=0;
 for(let k=0;k<ds.length;k++){
  const date=ds[k],fresh=t.holdings.map(h=>get(h.name,date));last=fresh.map((p,i)=>p??last[i]);
  const nav=()=>cash+sum(units.map((u,i)=>u*last[i]));
  const sell=(i,fraction,reason)=>{assert(fresh[i]>0);const quantity=units[i]*fraction,proceeds=quantity*last[i];units[i]-=quantity;cash+=proceeds;events.push({date,name:t.holdings[i].name,reason,fraction,proceeds,entry_return:last[i]/entry[i]-1});};
  const canAct=k>0&&(k<ds.length-1||t.is_open);
  if(sessions.has(date)&&k>0)age++;
  if(!protectedOnce&&fresh.every((p,i)=>alloc.weights[i]===0||p>0)){
   peak=Math.max(peak,nav());if(nav()-1>=.135-1e-12)armed=true;
   if(armed&&1-nav()/peak>=.022-1e-12&&canAct){units.forEach((u,i)=>{if(u>1e-12)sell(i,.5,'portfolio_protection');});protectedOnce=true;}
  }
  if(config.exit&&canAct&&sessions.has(date)){
   const raw=last.map((p,i)=>p/entry[i]-1),mid=median(raw);
   raw.forEach((r,i)=>{
    if(acted[i]||units[i]<1e-12)return;
    let condition=age>=5&&fresh[i]>0&&r<0;
    if(config.exit==='relative')condition=condition&&fresh.every(p=>p>0)&&r<mid-config.gap;
    if(config.exit==='stop')condition=age>0&&fresh[i]>0&&r<=-config.gap;
    streak[i]=condition?streak[i]+1:0;
    if(streak[i]>=(config.persistence??3)){sell(i,config.fraction,'individual_'+config.exit);acted[i]=true;}
   });
  }
  assert(cash>=-1e-10&&units.every(u=>u>=-1e-10));curve.push({date,nav:nav()});
 }
 return {start_date:t.start_date,end_date:t.end_date,year:t.year,type:t.type,return:curve.at(-1).nav-1,curve,events,allocation:alloc,
  names:t.holdings.map(h=>h.name),amv_return:t.amv_return};
}
function run(id,config={}){
 const trades=base.trades.map(t=>t.type==='bull'?simulate(t,config):{...t,curve:dates.filter(d=>d>=t.start_date&&d<=t.end_date).map(date=>({date,nav:1+t.holdings.reduce((s,h)=>s+h.weight*((get(h.name,date)??get(h.name,t.start_date))/get(h.name,t.start_date)-1),0)})),events:[]});
 const values=new Map();let capital=1;
 for(const t of trades){assert(Math.abs(t.curve.at(-1).nav-1-t.return)<1e-6);t.curve.forEach(p=>values.set(p.date,capital*p.nav));capital*=1+t.return;}
 let nav=1,peak=1,dd=0;const curve=dates.map(date=>{nav=values.get(date)??nav;peak=Math.max(peak,nav);dd=Math.max(dd,1-nav/peak);return {date,nav};});assert(Math.abs(nav-capital)<1e-6);
 const annual=Object.fromEntries(Array.from({length:8},(_,i)=>[2019+i,(product(trades.filter(t=>t.year===2019+i))-1)*100]));
 const bull=trades.filter(t=>t.type==='bull'),original=base.trades.filter(t=>t.type==='bull'),changes=bull.map((t,i)=>({start:t.start_date,delta_pp:(t.return-original[i].return)*100,old_pct:original[i].return*100,new_pct:t.return*100}));
 return {id,config,total_pct:(capital-1)*100,dd_pct:dd*100,annual,early_pct:(product(trades.filter(t=>t.year<=2023))-1)*100,recent_pct:(product(trades.filter(t=>t.year>=2024))-1)*100,
  individual_sales:sum(bull.map(t=>t.events.filter(e=>e.reason.startsWith('individual')).length)),fallback_count:bull.filter(t=>t.allocation.fallback).length,
  better:changes.filter(x=>x.delta_pp>1e-8).length,worse:changes.filter(x=>x.delta_pp< -1e-8).length,
  reversals:bull.filter(t=>['2024-02-06','2024-09-24','2025-06-25'].includes(t.start_date)).map(t=>({date:t.start_date,return_pct:t.return*100})),
  best:[...changes].sort((a,b)=>b.delta_pp-a.delta_pp).slice(0,3),worst:[...changes].sort((a,b)=>a.delta_pp-b.delta_pp).slice(0,3),trades,curve};
}
const results=[run('baseline')];
for(const window of [20,40,60])for(const blend of [.5,1])results.push(run(`vol${window}_blend${blend}`,{window,blend}));
for(const fraction of [.5,1]){
 results.push(run(`negative_half${fraction}`,{exit:'negative',fraction}));
 for(const gap of [.03,.05])results.push(run(`relative${gap}_sell${fraction}`,{exit:'relative',gap,fraction}));
 for(const gap of [.05,.08])results.push(run(`stop${gap}_sell${fraction}`,{exit:'stop',gap,fraction,persistence:2}));
}
for(const gap of [.03,.05])results.push(run(`combined40_relative${gap}`,{window:40,blend:.5,exit:'relative',gap,fraction:.5}));
const original=new Map(base.navSeries.map(p=>[p.date,p.nav]));results[0].curve.forEach(p=>assert(Math.abs(p.nav-original.get(p.date))<1e-6,`Baseline NAV parity ${p.date}`));
const b=base.trades.filter(t=>t.type==='bull');results[0].trades.filter(t=>t.type==='bull').forEach((t,i)=>{assert(Math.abs(t.return-b[i].return)<1e-10);assert.equal(t.events.find(e=>e.reason==='portfolio_protection')?.date,b[i].protection?.trigger_date);});
const output={last_date:input.amv.at(-1).date,params,results,checks:{baseline_daily_nav:true,baseline_trade_returns:true,baseline_protection_dates:true,cash_nonnegative:true},conventions:[
 'Same frozen current-universe input, selections and AMV zones as previous study. Retrospective, no untouched holdout.',
 'Initial volatility is sample SD of 20/40/60 returns ending strictly before entry. Inverse volatility capped at 30%; blend0.5 averages equal and capped inverse weights. Missing full history falls back to original equal weights for entire basket.',
 'Negative/relative exits require at least five sessions held then three consecutive qualifying closes. Relative means negative return from entry AND behind median original basket return by gap percentage points. Stop requires two consecutive closes below loss threshold, no minimum age.',
 'Individual exit only once per ETF per interval, sells half/all remaining units. Cash stays idle, no replacement or re-entry. Portfolio protection runs first on same close; its dates are recalculated from actual holdings and cash, not copied from baseline.',
 'Same close execution; no fees/slippage. Signals can overshoot thresholds. Valuation carries prior quotes; trades require exact quotes.',
 'Annual uses entry-year attribution, 2026 partial. Bank rules unchanged, active since2024. Full exposure at entry except pre-existing missing holding slots.' ]};
fs.writeFileSync(path.join(__dirname,'holding_risk_results.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify(results.map(({trades,curve,...r})=>r),null,2));
