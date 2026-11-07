const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
const input=JSON.parse(fs.readFileSync(path.join(__dirname,'robust_execution_inputs.json'),'utf8'));
const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:m,exports:m.exports});
function summarize(r){let peak=1,dd=0;for(const p of r.navSeries){peak=Math.max(peak,p.nav);dd=Math.max(dd,1-p.nav/peak);}return {return_pct:100*(r.finalNav-1),dd_pct:100*dd,bull_count:r.trades.filter(t=>t.type==='bull').length,bull_win_count:r.trades.filter(t=>t.type==='bull'&&t.return>0).length};}
const cases={};
for(const protection of [false,true])for(const bank of [false,true])for(const ranking of ['etf_gain','etf_blend20']){
 const p={...input.params,profitProtectionEnabled:protection,bearBuyBank:bank,rankingMethod:ranking};
 cases[`${ranking}_protection${protection}_bank${bank}`]=summarize(m.exports.runBacktest(input.amv,input.etfs,p));
}
const benchmarks=[];
for(const code of ['sh000001','sh000300','510050','510300','563300']){
 const s=input.etfs.find(s=>s.id===code),bars=s.data.filter(p=>p.date>='2019-01-01'&&p.date<=input.amv.at(-1).date);
 let peak=bars[0].close,dd=0;for(const p of bars){peak=Math.max(peak,p.close);dd=Math.max(dd,1-p.close/peak);}
 benchmarks.push({code,name:s.name,first:bars[0].date,last:bars.at(-1).date,hold_pct:100*(bars.at(-1).close/bars[0].close-1),dd_pct:dd*100});
}
const broadTiming={};
for(const code of ['510050','510300']){
 const universe=input.etfs.filter(s=>[code,'512800'].includes(s.id));
 broadTiming[code]=summarize(m.exports.runBacktest(input.amv,universe,{...input.params,weights:[100],profitProtectionEnabled:false,bearBuyBank:false}));
}
const trades=input.baseline.trades,product=ts=>ts.reduce((v,t)=>v*(1+t.return),1);
const best=[...trades.filter(t=>t.type==='bull')].sort((a,b)=>b.return-a.return);
const withoutBest=trades.filter(t=>!best.slice(0,3).includes(t));
const report={last:input.amv.at(-1).date,cases,benchmarks,broadTiming,bull_factor:product(trades.filter(t=>t.type==='bull')),bank_factor:product(trades.filter(t=>t.type==='bear')),without_best3_bull_pct:100*(product(withoutBest)-1),best3:best.slice(0,3).map(t=>({start:t.start_date,end:t.end_date,return_pct:t.return*100})),conventions:['Frozen inputs reproduce screenshot; same close, no costs.','Displayed production benchmarks compound ONLY bull intervals, not buy-and-hold.','Index close returns exclude dividends; stored ETF OHLC adjustment provenance not independently verified.','Removing best trades is a concentration diagnostic, not an executable strategy.']};
fs.writeFileSync(path.join(__dirname,'strategy_evidence.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
