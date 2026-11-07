const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'stock-line/node_modules/typescript'));
async function api(route){const r=await fetch('http://localhost:8000/api/'+route);if(!r.ok)throw Error(route);const j=await r.json();if(j.code!==0)throw Error(route);return j.data;}
(async()=>{
 const {amv,etfs,catalog}=JSON.parse(fs.readFileSync(path.join(__dirname,'robust_execution_snapshot.json'),'utf8'));
 const mod={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'stock-line/src/pages/ActiveMarket/utils/backtest.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:mod,exports:mod.exports});
 const params={...mod.exports.DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,rankingMethod:'etf_blend20',weights:[20,20,20,20,20],leverageMultiplier:1,bearBuyBank:true,bearStartYear:2024,profitProtectionEnabled:true,profitProtectionArmPct:13.5,profitProtectionDrawdownPct:2.2};
 const baseline=mod.exports.runBacktest(amv,etfs,params);
 fs.writeFileSync(path.join(__dirname,'robust_execution_inputs.json'),JSON.stringify({amv,etfs,catalog,params,baseline}));
 console.log(JSON.stringify({last:amv.at(-1).date,total:baseline.totalReturn,trades:baseline.trades.length,etfs:etfs.length}));
})();
