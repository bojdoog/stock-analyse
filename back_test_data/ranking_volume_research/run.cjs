/* Research only: inject a ranking hook into a memory copy of the production engine. */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'stock-line/node_modules/typescript'));
const input = JSON.parse(fs.readFileSync(path.join(__dirname, 'inputs.json'), 'utf8'));
const source = fs.readFileSync(path.join(root, 'stock-line/src/pages/ActiveMarket/utils/backtest.ts'), 'utf8');
const needle = `        topN = eligible.map(row => ({ ...row, score: (
          candidates.filter(other => other.gain < row.gain).length / Math.max(1, candidates.length - 1)
          + eligible.filter(other => other.gain20! < row.gain20!).length / Math.max(1, eligible.length - 1)
        ) / 2 })).sort((a, b) => b.score - a.score).slice(0, weights.length);`;
const normalized = source.replace(/\r\n/g, '\n');
assert(normalized.includes(needle), 'Production ranking block changed; abort instead of silently running wrong code.');
let config, diagnostics;
function customRank(eligible, candidates, day) {
  const feature = input.volume_features[day] || {};
  // Direction comes from the candidate ETF return; volume ONLY from mapped THS industries.
  const signed = row => Math.sign(row.gain) * feature[row.name];
  const observed = eligible.filter(row => Number.isFinite(feature[row.name]));
  const ranked = eligible.map(row => {
    const pd = candidates.filter(o => o.gain < row.gain).length / Math.max(1, candidates.length - 1);
    const p20 = eligible.filter(o => o.gain20 < row.gain20).length / Math.max(1, eligible.length - 1);
    const pv = Number.isFinite(feature[row.name])
      ? observed.filter(o => signed(o) < signed(row)).length / Math.max(1, observed.length - 1) : .5;
    return {...row, score: config[0] * pd + config[1] * p20 + config[2] * pv, volume_ratio: feature[row.name] ?? null};
  }).sort((a,b) => b.score - a.score);
  diagnostics.push({day, eligible:eligible.length, mapped:observed.length, top:ranked.slice(0,5)});
  return ranked;
}
function engine(patched) {
  const mod = {exports:{}};
  const code = patched ? normalized.replace(needle, '        topN = customRank(eligible, candidates, startDate).slice(0, weights.length);') : normalized;
  vm.runInNewContext(ts.transpileModule(code, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,
    {module:mod,exports:mod.exports,customRank});
  return mod.exports;
}
const original = engine(false), modified = engine(true);
const params = {...original.DEFAULT_STRATEGY_PARAMS, startYear:2019,endYear:2026,bullStartUseMA10:false,
  weights:[20,20,20,20,20],profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2,
  leverageMultiplier:1,bearBuyBank:true,bearStartYear:2024,rankingMethod:'etf_blend20'};
const baseline = original.runBacktest(input.amv,input.etfs,params);
config=[.5,.5,0];diagnostics=[];
const identical = modified.runBacktest(input.amv,input.etfs,params);
assert.equal(JSON.stringify(identical),JSON.stringify(baseline),'50/50 hook must reproduce production exactly.');
function metrics(result, start, end='2026-10-23') {
  const prior = result.navSeries.filter(p=>p.date<start).at(-1)?.nav ?? 1;
  const curve = result.navSeries.filter(p=>p.date>=start&&p.date<=end);
  let peak=prior, drawdown=0;
  for (const p of curve) {peak=Math.max(peak,p.nav);drawdown=Math.max(drawdown,1-p.nav/peak);}
  const zones = new Map(result.zones.map(z=>[z.start_date,z]));
  const bulls = result.trades.filter(t=>t.type==='bull'&&t.start_date>=start&&t.end_date<=end&&!zones.get(t.start_date)?.is_open);
  const wins = bulls.filter(t=>t.return>0).length;
  return {return_pct:100*((curve.at(-1)?.nav??prior)/prior-1),max_drawdown_pct:100*drawdown,
    completed_bulls:bulls.length,wins,win_rate_pct:bulls.length?100*wins/bulls.length:null,
    mean_bull_return_pct:bulls.length?100*bulls.reduce((s,t)=>s+t.return,0)/bulls.length:null};
}
const cases = [
  ['baseline_50_50',[.5,.5,0]],['day_only',null],['price_70_30',[.7,.3,0]],
  ['price_30_70',[.3,.7,0]],['price_20d_only',[0,1,0]],
  ['price_40_30_normalized',[4/7,3/7,0]],['price_30_40_normalized',[3/7,4/7,0]],
  ['price_40_20_normalized',[2/3,1/3,0]],
  ['volume_45_45_10',[.45,.45,.1]],['volume_35_35_30',[.35,.35,.3]],
  ['volume_40_40_20',[.4,.4,.2]],
  ['volume_35_35_20_no_amount',[.35,.35,.2]],
  ['volume_30_40_20_no_amount',[.3,.4,.2]],
  ['volume_40_30_20_no_amount',[.4,.3,.2]],
  ['volume_40_20_30_no_amount',[.4,.2,.3]],
];
const report = {params,last:input.amv.at(-1).date,coverage:input.coverage,mappings:input.mappings,
  validation:{baseline_hook_exact:true,screenshot_total_pct:853.77,actual_total_pct:baseline.totalReturn*100},
  conventions:[
    'Only ranking changes. Same production engine, same current ETF universe, AMV signals, exits, bank holdings and protection.',
    'Same signal-date closing execution; no fees/slippage. This is in-sample research, not an execution-delay validation.',
    'Volume: sum of fixed exact-match mapped industry volumes / mean of previous 20 AMV sessions; all mapped industries required.',
    'Missing volume or missing mapping: neutral 0.5 volume percentile, never ETF volume. No candidate is removed.',
    'Four-factor amount-share schemes cannot be tested exactly: true industry turnover amount unavailable; no_amount cases omit that term.',
    'Recent results use continuous strategy NAV from full 2019 run; no artificial reset of signals at year boundaries.',
    'Success = positive-return completed bull intervals whose entry is within the window; open intervals excluded.',
    'Historical ETF pool uses current enabled catalog; adjustment provenance and survivorship were not independently reconstructed.'
  ],cases:[]};
const curves={};
for(const [name,weights] of cases) {
  config=weights;diagnostics=[];
  const r=weights?modified.runBacktest(input.amv,input.etfs,params):original.runBacktest(input.amv,input.etfs,{...params,rankingMethod:'etf_gain'});
  assert.equal(JSON.stringify(r.zones),JSON.stringify(baseline.zones),'Signal intervals must not change.');
  assert.equal(JSON.stringify(r.trades.filter(t=>t.type==='bear')),JSON.stringify(baseline.trades.filter(t=>t.type==='bear')),'Bank trades must not change.');
  assert(Math.abs(r.navSeries.at(-1).nav-r.finalNav)<.001,'NAV must reconcile to final return.');
  const annual={};for(let y=2019;y<=2026;y++) annual[y]=metrics(r,`${y}-01-01`,`${y}-12-31`);
  const recentDiagnostics=diagnostics.filter(d=>d.day>='2025-01-01');
  const baselineTrades=new Map(baseline.trades.filter(t=>t.type==='bull').map(t=>[t.start_date,t]));
  const changed=r.trades.filter(t=>t.type==='bull'&&t.start_date>='2025-01-01').filter(t=>
    JSON.stringify(t.holdings.map(h=>h.name).sort())!==JSON.stringify((baselineTrades.get(t.start_date)?.holdings??[]).map(h=>h.name).sort()));
  report.cases.push({name,weights,full:weights?.[2]?null:metrics(r,'2019-01-01'),recent:metrics(r,'2025-01-01'),
    since_volume:metrics(r,'2024-10-17'),annual,changed_recent_intervals:changed.length,
    ui_year_results:r.yearResults,diagnostics:recentDiagnostics,trades:r.trades});
  curves[name]=r.navSeries;
  console.log(JSON.stringify({name,recent:metrics(r,'2025-01-01'),full:weights?.[2]?null:metrics(r,'2019-01-01'),years:Object.fromEntries(Object.entries(annual).map(([y,m])=>[y,m.return_pct]))}));
}
fs.writeFileSync(path.join(__dirname,'results.json'),JSON.stringify(report,null,2));
fs.writeFileSync(path.join(__dirname,'curves.json'),JSON.stringify(curves));
