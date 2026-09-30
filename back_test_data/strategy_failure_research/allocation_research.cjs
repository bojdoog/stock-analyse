// Read-only allocation study using the current enabled ETF universe.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const ts=require(path.join(root,'stock-line/node_modules/typescript'));
async function api(url){const r=await fetch('http://localhost:8000/api/'+url);assert(r.ok);return (await r.json()).data;}
(async()=>{
 const indicators=await api('indicators?pageSize=100');
 const indicator=indicators.find(x=>x.code==='0AMV');assert(indicator);
 const [amv,series,catalog]=await Promise.all([api(`indicators/${indicator.id}/data`),api('sector-data'),api('etf-types')]);
 const etfs=[...series.etf_data,...series.index_data];
 const core=etfs.find(x=>x.id==='563300');assert(core);
 const input={amv,etfs,catalog};
 fs.writeFileSync(path.join(__dirname,'allocation_inputs.json'),JSON.stringify(input));
 const source=fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8');
 let corePct=0;
 let patched=source.replaceAll('if (name === BANK_ETF_NAME) return;', 'if (name === BANK_ETF_NAME || (researchCorePct() > 0 && name === researchCoreName)) return;');
 const anchor='      const amvStartClose = getClose(filteredAMV, startDate);';
 assert.equal(source.split(anchor).length,3); // Bull branch first; bear branch remains untouched.
 patched=patched.replace(anchor, `      if (researchCorePct() > 0) {
        const coreData = etfMap.get(researchCoreName);
        const coreClose = coreData ? getClose(coreData, startDate) : null;
        const corePrev = coreData ? getClose(coreData, prevDate) : null;
        if (coreClose !== null && coreClose > 0) tryAddHolding({name: researchCoreName,
          day_change: corePrev ? (coreClose/corePrev-1)*100 : 0}, researchCorePct());
      }
`+anchor);
 function compile(s){const m={exports:{}};vm.runInNewContext(ts.transpileModule(s,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:m,exports:m.exports,researchCorePct:()=>corePct,researchCoreName:core.name});return m.exports;}
 const engine=compile(patched),plain=compile(source);
 const params={...engine.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,rankingMethod:'etf_blend20',leverageMultiplier:1,
  bearBuyBank:true,bearStartYear:2024,profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
 const layouts={current:[30,30,20,10,10],equal3:[100/3,100/3,100/3],equal4:[25,25,25,25],equal5:[20,20,20,20,20],equal6:Array(6).fill(100/6),
  gentle4:[30,25,25,20],gentle5:[25,25,20,15,15]};
 const baseline=plain.runBacktest(amv,etfs,params);
 assert.equal(JSON.stringify(engine.runBacktest(amv,etfs,params)),JSON.stringify(baseline));
 const product=trades=>trades.reduce((v,t)=>v*(1+t.return),1);
 const dd=points=>{let peak=points[0]?.nav||1,max=0;for(const p of points){peak=Math.max(peak,p.nav);max=Math.max(max,1-p.nav/peak);}return max*100;};
 const summaries=[],details={};
 for(const [layout,weights] of Object.entries(layouts))for(const c of [0,10,20]){
  corePct=c;const p={...params,weights:weights.map(w=>w*(1-c/100))};
  const r=engine.runBacktest(amv,etfs,p),id=`${layout}_core${c}`;
  assert.equal(JSON.stringify(r.zones),JSON.stringify(baseline.zones));
  assert.equal(JSON.stringify(r.trades.filter(t=>t.type==='bear')),JSON.stringify(baseline.trades.filter(t=>t.type==='bear')));
  assert(Math.abs(r.navSeries.at(-1).nav-product(r.trades))<1e-6);
  for(const t of r.trades){assert(new Set(t.holdings.map(h=>h.name)).size===t.holdings.length);assert(t.holdings.reduce((s,h)=>s+h.weight,0)<=1+1e-8);}
  const bull=r.trades.filter(t=>t.type==='bull'),recent=r.trades.filter(t=>t.start_date>='2024-01-01');
  const navRecent=r.navSeries.filter(p=>p.date>='2024-01-01');
  summaries.push({id,weights:p.weights,core_pct:c,total_pct:r.totalReturn*100,dd_pct:dd(r.navSeries),
   recent_pct:(product(recent)-1)*100,recent_dd_pct:dd(navRecent),annual:Object.fromEntries(r.yearResults.map(y=>[y.year,y.annual_return])),
   bull_win_pct:100*bull.filter(t=>t.return>0).length/bull.length,worst_bull_pct:100*Math.min(...bull.map(t=>t.return)),
   focus:Object.fromEntries(['2024-02-06','2024-09-24','2025-06-25','2026-04-08'].map(d=>[d,100*(bull.find(t=>t.start_date===d)?.return??NaN)])),
   pre_core_missing_bulls:c?bull.filter(t=>!t.holdings.some(h=>h.name===core.name)).length:0});
  details[id]={trades:r.trades,nav:r.navSeries};
 }
 const output={last_date:amv.at(-1).date,core_first_date:core.data[0].date,universe:catalog.map(x=>({code:x.code,name:x.name})),params,
  summaries,checks:{zero_core_production_parity:true,zones_and_bank_unchanged:true,nav_reconciles:true,no_duplicate_holdings:true},
  conventions:['Current enabled ETF universe; same-close execution; no fees or slippage.',
   'Core excluded from ranked sleeve, added at fixed weight; unavailable core allocation stays cash.',
   '13.5/2.2 protection applies to whole portfolio including core, reducing every holding by half once.',
   'Annual returns are grouped by trade entry year; recent_pct is compounded trades entered since 2024.',
   'Historical comparison only, not untouched out-of-sample validation. Existing end-quote fallback retained.'],details};
 fs.writeFileSync(path.join(__dirname,'allocation_results.json'),JSON.stringify(output,null,2));
 console.log(JSON.stringify({...output,details:undefined},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
