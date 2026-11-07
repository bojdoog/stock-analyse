// Isolate AMV +4% triggers below MA10. Production rules/defaults unchanged.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
async function api(url){const r=await fetch('http://localhost:8000/api/'+url);assert(r.ok);const j=await r.json();assert.equal(j.code,0);return j.data;}
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
function stats(a,key){const v=a.map(t=>t[key]);return {n:v.length,wins:v.filter(x=>x>1e-10).length,losses:v.filter(x=>x< -1e-10).length,flat:v.filter(x=>Math.abs(x)<=1e-10).length,win_pct:v.length?v.filter(x=>x>1e-10).length/v.length*100:null,mean_pct:mean(v),median_pct:v.length?[...v].sort((a,b)=>a-b).slice(Math.floor((v.length-1)/2),Math.floor(v.length/2)+1).reduce((s,x,_,b)=>s+x/b.length,0):null,best_pct:v.length?Math.max(...v):null,worst_pct:v.length?Math.min(...v):null};}
(async()=>{
 const def=(await api('indicators?pageSize=100')).find(x=>x.code==='0AMV');assert(def);
 const [amv,s,catalog]=await Promise.all([api(`indicators/${def.id}/data`),api('sector-data'),api('etf-types')]);const etfs=[...s.etf_data,...s.index_data];
 fs.writeFileSync(path.join(__dirname,'ma10_rejected_inputs.json'),JSON.stringify({amv,etfs,catalog}));
 const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:m,exports:m.exports});const engine=m.exports;
 const params={...engine.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,rankingMethod:'etf_blend20',weights:[20,20,20,20,20],leverageMultiplier:1,profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2,bearBuyBank:true,bearStartYear:2024};
 const data=amv.filter(x=>x.date>='2019-01-01'),ma=data.map((_,i)=>i<9?null:mean(data.slice(i-9,i+1).map(x=>x.close))),r=data.map((x,i)=>i?100*(x.close/data[i-1].close-1):0);
 const normal=engine.runBacktest(amv,etfs,{...params,bullStartUseMA10:true}),relaxed=engine.runBacktest(amv,etfs,{...params,bullStartUseMA10:false}),unprotected=engine.runBacktest(amv,etfs,{...params,bullStartUseMA10:false,profitProtectionEnabled:false});
 function row(t){const i=data.findIndex(x=>x.date===t.start_date),j=data.findIndex(x=>x.date===t.end_date);assert(i>=0&&j>=i);return {start:t.start_date,end:t.end_date,is_open:!!t.is_open,type:r[i]>4?'single':'two_day',day_pct:r[i],two_day_sum_pct:r[i]+(r[i-1]||0),close:data[i].close,ma10:ma[i],below_pct:ma[i]===null?null:(data[i].close/ma[i]-1)*100,holding_days:j-i,amv_pct:t.amv_return*100,etf_pct:t.return*100,etf_unprotected_pct:(unprotected.trades.find(x=>x.type==='bull'&&x.start_date===t.start_date)?.return??null)*100,peak_amv_pct:100*(Math.max(...data.slice(i,j+1).map(x=>x.close))/data[i].close-1),holdings:t.holdings,forward:Object.fromEntries([1,3,5,10,20].map(n=>[n,data[i+n]?100*(data[i+n].close/data[i].close-1):null]))};}
 const all=relaxed.trades.filter(t=>t.type==='bull').map(row),rejected=all.filter(t=>t.ma10!==null&&t.close<=t.ma10),closed=rejected.filter(t=>!t.is_open),controls=normal.trades.filter(t=>t.type==='bull'&&!t.is_open).map(row);
 const events=[];
 for(let i=9;i<data.length;i++){
  if(!(r[i]>4||(r[i]>0&&r[i-1]>0&&r[i]+r[i-1]>4))||data[i].close>ma[i])continue;
  const date=data[i].date,alreadyBull=normal.zones.some(z=>z.type==='bull'&&date>z.start_date&&date<=z.end_date);
  events.push({date,alreadyBull,in_relaxed_wave:rejected.some(t=>t.start===date)});
 }
 const group=a=>({amv:stats(a,'amv_pct'),etf:stats(a,'etf_pct'),mean_holding_days:mean(a.map(t=>t.holding_days)),one_day_exits:a.filter(t=>t.holding_days===1).length});
 const output={last_date:amv.at(-1).date,params,rows:rejected,raw_events:events,summary:group(closed),normal:group(controls),by_trigger:Object.fromEntries(['single','two_day'].map(k=>[k,group(closed.filter(t=>t.type===k))])),by_year:Object.fromEntries(Array.from({length:8},(_,i)=>[2019+i,group(closed.filter(t=>t.start.startsWith(String(2019+i))))])),forward:Object.fromEntries([1,3,5,10,20].map(n=>[n,stats(rejected.filter(t=>t.forward[n]!==null).map(t=>({value:t.forward[n]})),'value')])),
  conventions:['MA10 condition means close strictly above MA10, not necessarily a same-day cross from below.',
   'Strict >4%; two-day trigger requires both days positive and sums percentage changes, not compounded return.',
   'Disable entry MA10 only. Original exits unchanged: next/future close below MA10 OR single-day decline below -2.3%. Signals while already long do not open duplicate positions.',
   'Trade return excludes trigger-day rise: entry close to exit close. Success means strictly positive return; flat separate. Open waves excluded from wave summary.',
   'Forward returns ignore exit signals and are AMV diagnostic event returns, not executable portfolio strategy returns.',
   'Current enabled ETF universe and existing same-close execution retained; no fees/slippage. ETF protection enabled at13.5/2.2, weights equal20%.' ]};
 fs.writeFileSync(path.join(__dirname,'ma10_rejected_results.json'),JSON.stringify(output,null,2));console.log(JSON.stringify({...output,rows:rejected.map(({holdings,...t})=>t)},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
