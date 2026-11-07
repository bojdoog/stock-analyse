// Retrospective weak-market diagnostics. No changes to production parameters.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
const input=JSON.parse(fs.readFileSync(path.join(__dirname,'generalization_inputs.json'),'utf8'));
const source=fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8');
const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:m,exports:m.exports});
const engine=m.exports,amv=input.amv;
const params={...engine.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,rankingMethod:'etf_blend20',weights:[20,20,20,20,20],leverageMultiplier:1,bearStartYear:2024,bearBuyBank:true,profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
const base=engine.runBacktest(amv,input.etfs,params);
const dates=[...new Set(input.etfs.find(s=>s.id==='512800').data.map(x=>x.date))].filter(d=>d>='2019-01-01'&&d<=amv.at(-1).date).sort();
const sessions=new Set(dates),quotes=new Map(input.etfs.map(s=>[s.name,s.data.filter(x=>x.close>0).sort((a,b)=>a.date.localeCompare(b.date))]));
function price(name,date){const p=quotes.get(name).find(x=>x.date===date)?.close;assert(p>0,`Missing execution ${name} ${date}`);return p;}
function mark(name,date){const p=quotes.get(name).filter(x=>x.date<=date).at(-1)?.close;assert(p>0);return p;}
function curve(t){return t.relative_nav?t.relative_nav.filter(p=>sessions.has(p.date)):dates.filter(d=>d>=t.start_date&&d<=t.end_date).map(date=>({date,nav:1+t.holdings.reduce((s,h)=>s+h.weight*(mark(h.name,date)/price(h.name,t.start_date)-1),0)}));}
const ma=(i,n)=>i>=n-1?amv.slice(i-n+1,i+1).reduce((s,x)=>s+x.close,0)/n:null;
function weak(t,n){const i=amv.findIndex(x=>x.date===t.start_date),now=ma(i,n),old=ma(i-5,n);return now!==null&&old!==null&&amv[i].close<now&&now<old;}
const product=trades=>trades.reduce((v,t)=>v*(1+t.return),1);
function evaluate(id,run=base,rule={}){
 const trades=run.trades.map(t=>{
  const original=curve(t);assert(original.length);assert(Math.abs(original.at(-1).nav-1-t.return)<1e-6,`Curve P&L ${t.start_date}`);
  let exposure=1,exit=null;
  if(t.type==='bull'){
   if(rule.ma&&weak(t,rule.ma))exposure=rule.exposure;
   if(rule.stop)exit=original.find((p,i)=>i>0&&p.nav<=1-rule.stop);
   if(rule.timeout&&original.length>rule.timeout){const p=original[rule.timeout];if(p.nav<=1)exit=p;}
   if(exit){for(const h of t.holdings)price(h.name,exit.date);}
  }
  const altered=original.map(p=>({date:p.date,nav:1+exposure*((exit&&p.date>=exit.date?exit.nav:p.nav)-1)}));
  return {...t,return:altered.at(-1).nav-1,curve:altered,exposure,early_exit:exit?.date};
 });
 const marks=new Map();let capital=1;
 for(const t of trades){for(const p of t.curve)marks.set(p.date,capital*p.nav);capital*=1+t.return;}
 let value=1,peak=1,dd=0;const nav=dates.map(date=>{value=marks.get(date)??value;peak=Math.max(peak,value);dd=Math.max(dd,1-value/peak);return {date,nav:value};});
 assert(Math.abs(value-capital)<1e-6);
 const annual={},calendar={};let last=1;for(let y=2019;y<=2026;y++){annual[y]=(product(trades.filter(t=>t.year===y))-1)*100;const e=nav.filter(p=>p.date.startsWith(String(y))).at(-1).nav;calendar[y]=(e/last-1)*100;last=e;}
 const bull=trades.filter(t=>t.type==='bull');
 return {id,total_pct:(capital-1)*100,dd_pct:dd*100,annual,calendar,changed:bull.filter((t,i)=>Math.abs(t.return-base.trades.filter(x=>x.type==='bull')[i].return)>1e-8).length,
  reversal2024:bull.filter(t=>['2024-02-06','2024-09-24'].includes(t.start_date)).map(t=>({date:t.start_date,return_pct:t.return*100,exposure:t.exposure,early_exit:t.early_exit})),
  trades:trades.map(({curve,...t})=>({...t,peak_pct:(Math.max(...curve.map(x=>x.nav))-1)*100,trough_pct:(Math.min(...curve.map(x=>x.nav))-1)*100})),nav};
}
const results=[evaluate('baseline')];
for(const ma of [60,120])for(const exposure of [0,.5,.75])results.push(evaluate(`weak_ma${ma}_exposure${exposure}`,base,{ma,exposure}));
for(const stop of [.03,.05,.07])results.push(evaluate(`stop${stop}`,base,{stop}));
for(const timeout of [3,5,10])results.push(evaluate(`timeout${timeout}`,base,{timeout}));
for(const arm of [3,4,6,8,10])results.push(evaluate(`protect_arm${arm}`,engine.runBacktest(amv,input.etfs,{...params,profitProtectionArmPct:arm})));
results.push(evaluate('bank_from2019',engine.runBacktest(amv,input.etfs,{...params,bearStartYear:2019})));
const diagnostic=results[0].trades.filter(t=>t.type==='bull'&&[2022,2023].includes(t.year)).map(t=>({...t,weak60:weak(t,60),weak120:weak(t,120)}));
const baselineNav=new Map(base.navSeries.map(p=>[p.date,p.nav]));
for(const p of results[0].nav)assert(Math.abs(p.nav-baselineNav.get(p.date))<1e-6,`Baseline NAV ${p.date}`);
const output={last_date:amv.at(-1).date,params,diagnostic,results,checks:{baseline_daily_nav_parity:true,curve_pnl_parity:true,exact_stop_execution_quotes:true},
 conventions:['Current ETF universe and frozen generalization inputs. Retrospective research, not unseen validation.',
 'Annual uses UI entry-year attribution; calendar contains actual year-end NAV returns. Bank rules unchanged, starting 2024.',
 'Weak: entry AMV close below trailing MA and MA below its value five AMV sessions earlier. Reduced exposure stays fixed for entire bull interval; unused money stays cash.',
 'Protection is measured on full selected basket before exposure scaling, so reduction does not change protection dates.',
 'Stop: basket close NAV from entry breaches threshold. Timeout: at Nth bank-ETF trading session after entry, close NAV <= 1. Exit at that close and hold cash until original bull interval ends, with no re-entry.',
 'All modes retain original close-signal/close-execution assumptions. No fees/slippage; thresholds can be overshot.',
 'Existing bank calendar used; valuation carries last quotes. Original engine selection/exit quote availability conventions retained.']};
fs.writeFileSync(path.join(__dirname,'bear_market_results.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify({...output,results:results.map(({trades,nav,...r})=>r)},null,2));
