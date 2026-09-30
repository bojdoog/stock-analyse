// Research only: daily cash/share ledger, no production strategy changes.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
const input=JSON.parse(fs.readFileSync(path.join(__dirname,'allocation_inputs.json'),'utf8'));
const source=fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8');
const mod={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:mod,exports:mod.exports});
const engine=mod.exports,lastDate=input.amv.at(-1).date;
// Bank ETF has the long trading-session history; do not turn stray dates in
// another series into an extra trading day (some archived series have weekends).
const dates=input.etfs.find(x=>x.id==='512800').data.map(x=>x.date).filter(d=>d>='2019-01-01'&&d<=lastDate).sort();
const quotes=new Map(input.etfs.map(s=>[s.name,new Map(s.data.map(r=>[r.date,r.close]))]));
const bank=input.etfs.find(x=>x.id==='512800').name;
const price=(name,date)=>{const p=quotes.get(name)?.get(date);assert(p>0,`Missing quote ${name} ${date}`);return p;};
const mark=(name,date)=>{const data=quotes.get(name);if(data.get(date)>0)return data.get(date);const prior=[...data].filter(([d,p])=>d<=date&&p>0).sort((a,b)=>a[0].localeCompare(b[0])).at(-1);assert(prior);return prior[1];};
const params={...engine.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,rankingMethod:'etf_blend20',weights:[20,20,20,20,20],
 leverageMultiplier:1,bearStartYear:2024,bearBuyBank:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
function simulate(base,mode){
 let cash=1,bankUnits=0,bull=null;const nav=[],closed=[],bankTrades=base.trades.filter(t=>t.type==='bear');
 const entries=new Map(base.trades.filter(t=>t.type==='bull').map(t=>[t.start_date,t]));
 const endMap=new Map(base.trades.filter(t=>t.type==='bull'&&!t.is_open).map(t=>[t.end_date,t]));
 const finish=date=>{closed.push({start:bull.trade.start_date,signal:bull.trade.end_date,exit:date,signal_return:bull.trade.return,
   actual_return:bull.realized/bull.capital-1,amv_return:bull.trade.amv_return,staged:bull.staged,protected:!!bull.trade.protection?.trigger_date});bull=null;};
 const sell=(h,qty,date)=>{qty=Math.min(h.units,qty);const proceeds=qty*price(h.name,date);h.units-=qty;cash+=proceeds;bull.realized+=proceeds;};
 const value=date=>cash+bankUnits*(bankUnits?mark(bank,date):0)+(bull?bull.holdings.reduce((s,h)=>s+h.units*mark(h.name,date),0):0);
 for(let i=0;i<dates.length;i++){
  const date=dates[i];
  if(bull?.trade.protection?.trigger_date===date)for(const h of bull.holdings)sell(h,h.units/2,date);
  if(endMap.has(date)){
   assert(bull && bull.trade===endMap.get(date));
   const successful=bull.trade.return>0;
   bull.staged=mode==='all_thirds'||(successful&&mode!=='immediate');
   const fractions=!bull.staged?[1]:mode==='winners_half'?[.5,.25,.25]:[1/3,1/3,1/3];
   bull.plan=fractions.map((fraction,j)=>({date:dates[i+j],fraction}));
   bull.holdings.forEach(h=>h.exitUnits=h.units);
  }
  if(bull?.plan){
   const due=bull.plan.find(p=>p.date===date);
   if(due)for(const h of bull.holdings)sell(h,h.exitUnits*due.fraction,date);
   if(bull.holdings.every(h=>h.units<1e-12))finish(date);
  }
  if(entries.has(date)){
   // New bull signal takes precedence over an unfinished old exit; never borrow.
   if(bull){for(const h of bull.holdings)sell(h,h.units,date);finish(date);}
   if(bankUnits){cash+=bankUnits*price(bank,date);bankUnits=0;}
   const trade=entries.get(date),capital=cash;
   bull={trade,capital,realized:capital*(1-trade.holdings.reduce((s,h)=>s+h.weight,0)),staged:false,
    holdings:trade.holdings.map(h=>({name:h.name,units:capital*h.weight/price(h.name,date)}))};
   cash-=capital*trade.holdings.reduce((s,h)=>s+h.weight,0);
  }
  const inBank=bankTrades.some(t=>date>=t.start_date&&(date<t.end_date||t.is_open&&date===t.end_date));
  if(inBank){bankUnits+=cash/price(bank,date);cash=0;}
  else if(bankUnits){cash+=bankUnits*price(bank,date);bankUnits=0;}
  assert(cash>=-1e-9);
  nav.push({date,nav:value(date)});
 }
 let peak=1,maxDD=0;for(const p of nav){peak=Math.max(peak,p.nav);maxDD=Math.max(maxDD,1-p.nav/peak);}
 const annual={};let prior=1;for(const y of [...new Set(nav.map(p=>p.date.slice(0,4)))]){const end=nav.filter(p=>p.date.startsWith(y)).at(-1).nav;annual[y]=(end/prior-1)*100;prior=end;}
 return {total_pct:(nav.at(-1).nav-1)*100,dd_pct:maxDD*100,annual,closed,nav};
}
const results={};
for(const protectedMode of [true,false]){
 const base=engine.runBacktest(input.amv,input.etfs,{...params,profitProtectionEnabled:protectedMode});
 const group={};for(const mode of ['immediate','winners_thirds','winners_half','all_thirds'])group[mode]=simulate(base,mode);
 const rawReturn=(base.trades.reduce((v,t)=>v*(1+t.return),1)-1)*100;
 assert(Math.abs(group.immediate.total_pct-rawReturn)<1e-7,'Immediate-exit ledger must match engine wealth');
 if(protectedMode){const baseNav=new Map(base.navSeries.map(p=>[p.date,p.nav]));for(const p of group.immediate.nav)assert(Math.abs(p.nav-baseNav.get(p.date))<1e-6,`Daily NAV parity ${p.date}`);}
 for(const [mode,r] of Object.entries(group)){
  const changes=r.closed.map(t=>({...t,delta_pp:100*(t.actual_return-t.signal_return)}));
  const stats=rows=>({count:rows.length,better:rows.filter(t=>t.delta_pp>1e-8).length,worse:rows.filter(t=>t.delta_pp< -1e-8).length,
   mean_delta_pp:rows.reduce((s,t)=>s+t.delta_pp,0)/rows.length,profit_to_loss:rows.filter(t=>t.signal_return>0&&t.actual_return<0).length});
  r.stats={all:stats(changes),successful:stats(changes.filter(t=>t.signal_return>0)),failed:stats(changes.filter(t=>t.signal_return<=0)),
   amv_successful:stats(changes.filter(t=>t.amv_return>0))};
  r.best=changes.sort((a,b)=>b.delta_pp-a.delta_pp).slice(0,5);r.worst=changes.sort((a,b)=>a.delta_pp-b.delta_pp).slice(0,5);
 }
 results[protectedMode?'protection_on':'protection_off']=group;
}
const output={last_date:dates.at(-1),params,universe:input.catalog.map(x=>x.code),results,
 conventions:['Success means portfolio total return (including protection sales) > 0 at the exit signal, not future profits.',
 'Sell remaining units in thirds on signal close / next session close / second next session close; half variant is 50/25/25.',
 'Protection cash remains cash until exit signal. Sale proceeds enter bank during eligible bear zones; no overlapping full allocations.',
 'Any new bull signal forces remaining old units sold before new entries. No fees/slippage; exact closes required for trades; valuation carries the last known quote.',
 'Annual numbers use calendar-year daily NAV, unlike UI entry-year grouping. 2026 is partial.',
 'Same-close signal and execution convention retained; this is not a verified pre-close execution study.',
 'Retrospective current-universe analysis; not untouched out-of-sample validation.'],checks:{immediate_exit_wealth_parity:true,protected_daily_nav_parity:true,no_borrowing:true,exact_quotes:true}};
fs.writeFileSync(path.join(__dirname,'exit_results.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify({...output,results:Object.fromEntries(Object.entries(results).map(([k,g])=>[k,Object.fromEntries(Object.entries(g).map(([m,r])=>[m,{...r,nav:undefined,closed:undefined}]))]))},null,2));
