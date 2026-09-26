const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const mod = {exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/pages/ActiveMarket/utils/backtest.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{module:mod,exports:mod.exports});
const {runBacktest,DEFAULT_STRATEGY_PARAMS:defaults,calculateProfitProtection:protect}=mod.exports;
assert.equal(defaults.leverageMultiplier,1);
for(const leverageMultiplier of [-1,-.01,Infinity,NaN]) assert.throws(()=>runBacktest([],[],{...defaults,leverageMultiplier}));
assert.doesNotThrow(()=>runBacktest([],[],{...defaults,leverageMultiplier:1e6}));
const input=JSON.parse(fs.readFileSync(path.join(__dirname,'../../back_test_data/strategy_failure_research/inputs.json'),'utf8'));
const base=runBacktest(input.amv,input.etfs,{...defaults,endYear:2026});
const protectedBase=runBacktest(input.amv,input.etfs,{...defaults,endYear:2026,profitProtectionEnabled:true});
for(const leverageMultiplier of [0,.01,.1,.5,2]) {
 const result=runBacktest(input.amv,input.etfs,{...defaults,endYear:2026,leverageMultiplier});
 assert.equal(result.trades.length,base.trades.length);
 result.trades.forEach((trade,i)=>{
  assert.ok(Math.abs(trade.return-base.trades[i].return*leverageMultiplier)<1e-9);
  trade.holdings.forEach((h,j)=>assert.ok(Math.abs(h.weight-base.trades[i].holdings[j].weight*leverageMultiplier)<1e-9));
 });
 const compound=result.trades.reduce((v,t)=>v*(1+t.return),1);
 assert.ok(Math.abs(result.navSeries.at(-1).nav-compound)<1e-6);
 const protectedResult=runBacktest(input.amv,input.etfs,{...defaults,endYear:2026,leverageMultiplier,profitProtectionEnabled:true});
 protectedResult.trades.forEach((trade,i)=>{
  const original=protectedBase.trades[i];
  assert.ok(Math.abs(trade.return-original.return*leverageMultiplier)<1e-9);
  if(leverageMultiplier>0) assert.deepEqual(trade.protection,original.protection);
 });
 if (leverageMultiplier === 0) {
  for (const output of [result, protectedResult]) {
   assert.equal(output.totalReturn, 0);
   assert.ok(output.navSeries.every(point => point.nav === 1));
   assert.ok(output.trades.every(trade => !trade.protection?.trigger_date));
  }
 }
 assert.ok(Math.abs(protectedResult.navSeries.at(-1).nav-protectedResult.trades.reduce((v,t)=>v*(1+t.return),1))<1e-6);
}
const dates=['2026-01-01','2026-01-02','2026-01-03'];
assert.equal(protect(dates,[.5],[[100],[105],[100]],4,2,true).status.armed_date,undefined);
assert.equal(protect(dates,[2],[[100],[103],[100]],4,2,true).status.trigger_date,dates[2]);
assert.throws(()=>runBacktest(input.amv,input.etfs,{...defaults,endYear:2026,leverageMultiplier:1000}));
console.log('PASS: leverage range, scaled bull/bear returns, NAV reconciliation, protection triggers and depleted equity');
