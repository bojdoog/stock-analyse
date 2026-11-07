// Factor ablation and robustness checks. Does not change production defaults.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
async function api(url){const r=await fetch('http://localhost:8000/api/'+url);assert(r.ok);const j=await r.json();assert.equal(j.code,0);return j.data;}
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
const wealth=trades=>trades.reduce((v,t)=>v*(1+t.return),1);
const drawdown=points=>{let peak=points[0]?.nav||1,dd=0;for(const p of points){peak=Math.max(peak,p.nav);dd=Math.max(dd,1-p.nav/peak);}return dd*100;};
(async()=>{
 const definitions=await api('indicators?pageSize=100'),definition=definitions.find(x=>x.code==='0AMV');assert(definition);
 const [amv,series,catalog]=await Promise.all([api(`indicators/${definition.id}/data`),api('sector-data'),api('etf-types')]);
 const etfs=[...series.etf_data,...series.index_data],input={amv,etfs,catalog};
 fs.writeFileSync(path.join(__dirname,'generalization_inputs.json'),JSON.stringify(input));
 const source=fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8');
 let lookback=20,dayWeight=.5;
 const patched=source.replace('amvData[entryIndex - 20]','amvData[entryIndex - researchLookback()]')
  .replace('candidates.filter(other => other.gain < row.gain).length / Math.max(1, candidates.length - 1)',
   '2 * researchDayWeight() * candidates.filter(other => other.gain < row.gain).length / Math.max(1, candidates.length - 1)')
  .replace('eligible.filter(other => other.gain20! < row.gain20!).length / Math.max(1, eligible.length - 1)',
   '2 * (1-researchDayWeight()) * eligible.filter(other => other.gain20! < row.gain20!).length / Math.max(1, eligible.length - 1)');
 function compile(s){const m={exports:{}};vm.runInNewContext(ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,
  {module:m,exports:m.exports,researchLookback:()=>lookback,researchDayWeight:()=>dayWeight});return m.exports;}
 const engine=compile(patched),plain=compile(source);
 const params={...plain.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,weights:[20,20,20,20,20],leverageMultiplier:1,
  bearBuyBank:true,bearStartYear:2024,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
 const runs={};
 for(const weighting of ['equal','ranked'])for(const selection of ['day','mix'])for(const protection of [false,true]){
  const p={...params,weights:weighting==='equal'?[20,20,20,20,20]:[30,30,20,10,10],rankingMethod:selection==='day'?'etf_gain':'etf_blend20',profitProtectionEnabled:protection};
  const id=`${weighting}_${selection}_${protection?'on':'off'}`;
  runs[id]=engine.runBacktest(amv,etfs,p);
  assert.equal(JSON.stringify(runs[id]),JSON.stringify(plain.runBacktest(amv,etfs,p)));
 }
 function summary(r){const bull=r.trades.filter(t=>t.type==='bull');return {total_pct:(wealth(r.trades)-1)*100,dd_pct:drawdown(r.navSeries),
  annual:Object.fromEntries(r.yearResults.map(y=>[y.year,y.annual_return])),
  early_pct:(wealth(r.trades.filter(t=>t.start_date<'2024-01-01'))-1)*100,recent_pct:(wealth(r.trades.filter(t=>t.start_date>='2024-01-01'))-1)*100,
  bull_count:bull.length,bull_wins:bull.filter(t=>t.return>0).length,protection_count:bull.filter(t=>t.protection?.trigger_date).length};}
 function compare(a,b){const aa=a.trades.filter(t=>t.type==='bull'),bb=b.trades.filter(t=>t.type==='bull');
  assert.equal(aa.length,bb.length);const rows=aa.map((t,i)=>{assert.equal(t.start_date,bb[i].start_date);return {start:t.start_date,end:t.end_date,
   old_pct:t.return*100,new_pct:bb[i].return*100,delta_pp:(bb[i].return-t.return)*100,log_gain:Math.log((1+bb[i].return)/(1+t.return)),
   protection:bb[i].protection??null};});
  function stats(list){const log=list.reduce((s,t)=>s+t.log_gain,0);return {n:list.length,better:list.filter(t=>t.delta_pp>1e-8).length,worse:list.filter(t=>t.delta_pp< -1e-8).length,
   unchanged:list.filter(t=>Math.abs(t.delta_pp)<=1e-8).length,mean_delta_pp:mean(list.map(t=>t.delta_pp)),relative_wealth_pct:(Math.exp(log)-1)*100,log_gain:log};}
  const sorted=[...rows].sort((a,b)=>b.log_gain-a.log_gain),positive=rows.filter(t=>t.log_gain>0).reduce((s,t)=>s+t.log_gain,0);
  return {all:stats(rows),early:stats(rows.filter(t=>t.start<'2024-01-01')),recent:stats(rows.filter(t=>t.start>='2024-01-01')),
   top3_share_positive_log_gain:positive?sorted.slice(0,3).reduce((s,t)=>s+t.log_gain,0)/positive:null,
   excluding_top3:stats(rows.filter(t=>!sorted.slice(0,3).some(x=>x.start===t.start))),best:sorted.slice(0,5),worst:sorted.slice(-5).reverse(),rows};}
 const contrasts={protection_day:compare(runs.equal_day_off,runs.equal_day_on),protection_mix:compare(runs.equal_mix_off,runs.equal_mix_on),
  selection_unprotected:compare(runs.equal_day_off,runs.equal_mix_off),selection_protected:compare(runs.equal_day_on,runs.equal_mix_on),
  combined:compare(runs.equal_day_off,runs.equal_mix_on),equal_weight:compare(runs.ranked_mix_on,runs.equal_mix_on)};
 const protectionGrid=[],gridRuns=[];
 for(const arm of [10,12,13.5,15,18])for(const trail of [1.5,2,2.2,2.5,3]){
  const r=engine.runBacktest(amv,etfs,{...params,rankingMethod:'etf_blend20',profitProtectionEnabled:true,profitProtectionArmPct:arm,profitProtectionDrawdownPct:trail});
  protectionGrid.push({arm,trail,...summary(r),effect:compare(runs.equal_mix_off,r).all.relative_wealth_pct});gridRuns.push({arm,trail,r});
 }
 const selectionGrid=[];
 for(lookback of [10,15,20,25,30])for(dayWeight of [.25,.5,.75]){
  const r=engine.runBacktest(amv,etfs,{...params,rankingMethod:'etf_blend20',profitProtectionEnabled:false});
  selectionGrid.push({lookback,day_weight:dayWeight,...summary(r),early_effect:compare(runs.equal_day_off,r).early.relative_wealth_pct,recent_effect:compare(runs.equal_day_off,r).recent.relative_wealth_pct});
 }
 lookback=20;dayWeight=.5;
 const walkforward=[];
 for(const year of [2022,2023,2024,2025,2026]){
  const start=`${year}-01-01`,end=`${year+1}-01-01`;
  const train=r=>r.trades.filter(t=>t.type==='bull'&&t.end_date<start&&!t.is_open);
  const chosen=[{arm:null,trail:null,r:runs.equal_mix_off},...gridRuns].sort((a,b)=>wealth(train(b.r))-wealth(train(a.r)))[0];
  const test=r=>r.trades.filter(t=>t.type==='bull'&&t.start_date>=start&&t.start_date<end);
  walkforward.push({year,training_bulls:train(chosen.r).length,arm:chosen.arm,trail:chosen.trail,test_bulls:test(chosen.r).length,
   selected_pct:(wealth(test(chosen.r))-1)*100,no_protection_pct:(wealth(test(runs.equal_mix_off))-1)*100,fixed_pct:(wealth(test(runs.equal_mix_on))-1)*100});
 }
 const coverage=runs.equal_day_off.trades.filter(t=>t.type==='bull').map(t=>{
  const idx=amv.findIndex(x=>x.date===t.start_date),old=amv[idx-20]?.date,prev=amv[idx-1]?.date;
  const candidates=etfs.filter(s=>!s.id.startsWith('sh')&&s.id!=='512800'&&s.data.some(x=>x.date===t.start_date&&x.close>0)&&s.data.some(x=>x.date===prev&&x.close>0));
  return {date:t.start_date,day_candidates:candidates.length,mix_candidates:candidates.filter(s=>s.data.some(x=>x.date===old&&x.close>0)).length};
 });
 const baselineBanks=JSON.stringify(runs.equal_day_off.trades.filter(t=>t.type==='bear'));
 for(const r of Object.values(runs)){assert.equal(JSON.stringify(r.zones),JSON.stringify(runs.equal_day_off.zones));assert.equal(JSON.stringify(r.trades.filter(t=>t.type==='bear')),baselineBanks);}
 const output={last_date:amv.at(-1).date,params,universe:catalog.map(x=>({code:x.code,name:x.name})),summaries:Object.fromEntries(Object.entries(runs).map(([k,r])=>[k,summary(r)])),
  contrasts,protectionGrid,selectionGrid,walkforward,coverage,
  conventions:['Same current enabled universe for all ablations. Frozen input and current engine. No changes to production.',
   'Entry-year attribution, as in UI. 2026 partial. Bank allocation held fixed; contrasts use paired bull trades.',
   'Current universe was chosen after viewing history; no claim of untouched out-of-sample testing.',
   'Walk-forward uses only completed prior-year bull trades to choose protection settings, but the grid itself is retrospective.',
   'Same-close execution and end-quote fallback retained. Fees/slippage not added. Unprotected engine NAV uses existing daily weighting; terminal return uses trade compounding.',
   'Sensitivity grids diagnose stability and are not used to select a replacement production default.'],checks:{production_parity:true,same_signals:true,same_bank_trades:true}};
 fs.writeFileSync(path.join(__dirname,'generalization_results.json'),JSON.stringify(output,null,2));
 console.log(JSON.stringify({last_date:output.last_date,summaries:output.summaries,contrasts:Object.fromEntries(Object.entries(contrasts).map(([k,v])=>[k,{...v,rows:undefined}])),walkforward},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
