// Entry-selection experiments only. Production strategy is never modified.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'stock-line/node_modules/typescript'));
const input = JSON.parse(fs.readFileSync(path.join(__dirname, 'selection_inputs.json'), 'utf8'));
const source = fs.readFileSync(path.join(root, 'stock-line/src/pages/ActiveMarket/utils/backtest.ts'), 'utf8');
const anchor = 'const rankedCandidates = topN.map((item) => ({';
assert.equal(source.split(anchor).length, 2);
const patched = source.replace(anchor, 'topN = researchSelect(etfMap, startDate, prevDate, topN, weights.length);\n      ' + anchor);
const dates = input.amv.map(r => r.date);
const prices = new Map(input.etfs.map(s => [s.name, new Map(s.data.map(r => [r.date, r.close]))]));
const bank = '银行ETF';
let method = 'original';
const cache = new Map();
const mean = a => a.reduce((s,x)=>s+x,0)/a.length;
function features(etfMap, date, prevDate) {
  if (cache.has(date)) return cache.get(date);
  const index = dates.indexOf(date);
  const rows = [];
  for (const [name] of etfMap) {
    if (name === bank) continue;
    const p = prices.get(name), close = p?.get(date), prev = p?.get(prevDate);
    if (!(close>0 && prev>0)) continue;
    const row = {name, day_change: (close/prev-1)*100, r1: close/prev-1};
    for (const n of [5,10,20]) {
      const old = p.get(dates[index-n]);
      row['r'+n] = old>0 ? close/old-1 : null;
    }
    const daily = dates.slice(Math.max(0,index-20),index+1).map(d=>p.get(d));
    row.daily = daily.length===21 && daily.every(x=>x>0) ? daily.slice(1).map((x,i)=>x/daily[i]-1) : null;
    row.vol = row.daily ? Math.sqrt(mean(row.daily.map(x=>(x-mean(row.daily))**2))) : null;
    rows.push(row);
  }
  for (const key of ['r1','r5','r10','r20']) {
    const valid=rows.filter(r=>r[key]!==null).sort((a,b)=>a[key]-b[key]);
    valid.forEach(r=>{ r['p'+key.slice(1)] = valid.filter(x=>x[key]<r[key]).length/Math.max(1,valid.length-1); });
  }
  cache.set(date,rows);
  return rows;
}
function correlation(a,b) {
  if(!a || !b) return 0;
  const ma=mean(a),mb=mean(b);
  const numerator=mean(a.map((x,i)=>(x-ma)*(b[i]-mb)));
  const denominator=Math.sqrt(mean(a.map(x=>(x-ma)**2))*mean(b.map(x=>(x-mb)**2)));
  return denominator ? numerator/denominator : 0;
}
function researchSelect(etfMap,date,prevDate,original,n) {
  if(method==='original') return original;
  const rows=features(etfMap,date,prevDate).map(r=>({...r}));
  const score = r => {
    if(method.startsWith('momentum')) return r['r'+method.slice(8)];
    if(method==='blend5') return r.p5===undefined ? null : (r.p1+r.p5)/2;
    if(method==='blend20') return r.p20===undefined ? null : (r.p1+r.p20)/2;
    if(method==='blend5_20') return r.p5===undefined||r.p20===undefined ? null : (r.p1+r.p5+r.p20)/3;
    if(method==='risk20') return r.r20!==null && r.vol>0 ? r.r20/r.vol : null;
    return r.r1;
  };
  const ranked=rows.map(r=>({...r,score:score(r)})).filter(r=>r.score!==null&&Number.isFinite(r.score)).sort((a,b)=>b.score-a.score);
  if(method==='diverse') {
    const chosen=[];
    for(const row of ranked) {
      if(chosen.every(other=>correlation(row.daily,other.daily)<.85)) chosen.push(row);
      if(chosen.length===n) break;
    }
    // Keep the same number invested; fill with remaining original-ranked names if needed.
    for(const row of ranked) if(chosen.length<n&&!chosen.some(x=>x.name===row.name)) chosen.push(row);
    return chosen;
  }
  return ranked.slice(0,n);
}
const mod={exports:{}};
vm.runInNewContext(ts.transpileModule(patched,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,
  {module:mod,exports:mod.exports,researchSelect});
const {runBacktest,DEFAULT_STRATEGY_PARAMS:defaults}=mod.exports;
const params={...defaults,startYear:2019,endYear:2026,leverageMultiplier:1,profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
const methods=['original','momentum5','momentum10','momentum20','blend5','blend20','blend5_20','risk20','diverse'];
const results={};
for(method of methods) results[method]=runBacktest(input.amv,input.etfs,params);
const baseline=results.original;
// Verify the research hook leaves the production baseline completely unchanged.
const plain={exports:{}};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,
  {module:plain,exports:plain.exports});
assert.equal(JSON.stringify(baseline),JSON.stringify(plain.exports.runBacktest(input.amv,input.etfs,params)));
const product=trades=>trades.reduce((v,t)=>v*(1+t.return),1);
function drawdown(points) {let peak=1,max=0;for(const p of points){peak=Math.max(peak,p.nav);max=Math.max(max,1-p.nav/peak);}return max*100;}
const summary=methods.map(name=>{
  const r=results[name],bull=r.trades.filter(t=>t.type==='bull');
  assert.deepEqual(r.zones,baseline.zones);
  assert.deepEqual(r.trades.filter(t=>t.type==='bear'),baseline.trades.filter(t=>t.type==='bear'));
  assert.ok(Math.abs(r.navSeries.at(-1).nav-product(r.trades))<1e-6);
  return {method:name,total_pct:r.totalReturn*100,max_dd_pct:drawdown(r.navSeries),
    annual:Object.fromEntries(r.yearResults.map(y=>[y.year,y.annual_return])),
    earlier_pct:(product(r.trades.filter(t=>t.start_date<'2024-01-01'))-1)*100,
    later_pct:(product(r.trades.filter(t=>t.start_date>='2024-01-01'))-1)*100,
    excluding_focus_pct:(product(r.trades.filter(t=>!['2025-06-25','2026-04-08'].includes(t.start_date)))-1)*100,
    bull_wins:bull.filter(t=>t.return>0).length,bull_count:bull.length,
    improved_trades:bull.filter(t=>t.return>baseline.trades.find(b=>b.type==='bull'&&b.start_date===t.start_date).return+1e-9).length,
    worsened_trades:bull.filter(t=>t.return<baseline.trades.find(b=>b.type==='bull'&&b.start_date===t.start_date).return-1e-9).length};
});
const focusDates=['2024-02-06','2024-09-24','2025-06-25','2026-04-08'];
const focus=Object.fromEntries(focusDates.map(date=>[date,Object.fromEntries(methods.map(name=>{
  const trade=results[name].trades.find(t=>t.type==='bull'&&t.start_date===date);
  return [name,trade ? {return_pct:trade.return*100,amv_pct:trade.amv_return*100,holdings:trade.holdings,protection:trade.protection}:null];
}))]));
// Future returns below are diagnostic only, never input to any selector.
const attribution=Object.fromEntries(['2025-06-25','2026-04-08'].map(date=>{
  const trade=baseline.trades.find(t=>t.type==='bull'&&t.start_date===date);
  if(!trade) return [date,null];
  const end=trade.end_date;
  const universe=features(new Map(input.etfs.filter(s=>!s.id.startsWith('sh')).map(s=>[s.name,s.data])),date,dates[dates.indexOf(date)-1]);
  const outcome=universe.map(r=>({...r,return_pct:prices.get(r.name).get(end)/prices.get(r.name).get(date)*100-100}))
    .filter(r=>Number.isFinite(r.return_pct)).sort((a,b)=>b.return_pct-a.return_pct)
    .map(r=>({name:r.name,entry_gain_pct:r.day_change,entry_20d_pct:r.r20===null?null:r.r20*100,return_pct:r.return_pct,selected:trade.holdings.some(h=>h.name===r.name)}));
  return [date,{end,amv_pct:trade.amv_return*100,selected_pct:trade.return*100,equal_universe_pct:mean(outcome.map(r=>r.return_pct)),outcome}];
}));
const contribution=Object.fromEntries(methods.filter(n=>n!=='original').map(name=>{
  const changes=results[name].trades.filter(t=>t.type==='bull').map(t=>{
    const base=baseline.trades.find(b=>b.type==='bull'&&b.start_date===t.start_date);
    return {start:t.start_date,original_pct:base.return*100,candidate_pct:t.return*100,log_wealth_gain:Math.log((1+t.return)/(1+base.return))};
  }).sort((a,b)=>b.log_wealth_gain-a.log_wealth_gain);
  return [name,{net_log_gain:changes.reduce((s,t)=>s+t.log_wealth_gain,0),changes}];
}));
// Change every post-entry quote; the ranking for that entry must remain identical.
const causalDate='2025-06-25', priorDate=dates[dates.indexOf(causalDate)-1];
const causalMap=new Map(input.etfs.filter(s=>!s.id.startsWith('sh')).map(s=>[s.name,s.data]));
const before={};
for(method of methods.filter(n=>n!=='original')) before[method]=researchSelect(causalMap,causalDate,priorDate,[],5).map(r=>r.name);
for(const p of prices.values()) for(const [d,value] of p) if(d>causalDate) p.set(d,value*17);
cache.clear();
for(method of methods.filter(n=>n!=='original')) assert.deepEqual(researchSelect(causalMap,causalDate,priorDate,[],5).map(r=>r.name),before[method]);
const output={last_date:input.amv.at(-1).date,params,summary,focus,attribution,contribution,
  checks:{production_parity:true,future_quote_invariance:true,zones_and_bear_positions_unchanged:true,nav_reconciles:true},
  conventions:['Frozen snapshot from live /api/indicators/1/data and /api/sector-data on 2026-09-30.',
    'Same-close fills and original universe retained; no fees or slippage.',
    'Entry selection uses only quotes through the entry date; no periodic switching.',
    'Every method retains 30/30/20/10/10 weights, bank allocation and fixed 13.5/2.2 protection.',
    'Annual returns group whole trades by entry year, same as UI.',
    'All date splits are retrospective diagnostics, not untouched out-of-sample tests.',
    'Existing engine missing-end-quote fallback retained; current ETF universe may contain survivorship bias.']};
fs.writeFileSync(path.join(__dirname,'selection_results.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify({last_date:output.last_date,summary,focus:Object.fromEntries(Object.entries(focus).map(([d,rows])=>[d,Object.fromEntries(Object.entries(rows).map(([n,t])=>[n,t?.return_pct]))])),attribution},null,2));
