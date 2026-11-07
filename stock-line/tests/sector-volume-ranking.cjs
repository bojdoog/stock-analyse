const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('typescript');
const mod = {exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/pages/ActiveMarket/utils/backtest.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:mod,exports:mod.exports});
const {rankSectorCandidates:rank,runBacktest,DEFAULT_STRATEGY_PARAMS} = mod.exports;
const day='2026-10-23';
const candidates=[{name:'A',gain:3,gain20:1},{name:'B',gain:2,gain20:2},{name:'C',gain:1,gain20:3}];
const data={byDate:{[day]:{A:{volumeRatio:2,amountShare:.1},B:{volumeRatio:1,amountShare:.8},C:{volumeRatio:3,amountShare:.1}}},
  mappedNames:['A','B','C'],unmappedNames:[],coverageStart:day,coverageEnd:day,amountAvailable:true};
const three=rank(candidates,candidates,day,'etf_sector_403030',data);
assert.equal(three.map(r=>r.name).join(','),'C,A,B');
assert.ok(Math.abs(three[0].score-.6)<1e-12);
const four=rank(candidates,candidates,day,'etf_sector_40203010',data);
assert.equal(four.map(r=>r.name).join(','),'A,C,B');
assert.ok(Math.abs(four[0].score-.55)<1e-12);
const unavailable={...data,amountAvailable:false};
assert.throws(()=>rank(candidates,candidates,day,'etf_sector_40203010',unavailable),/缺少行业成交额/);
assert.throws(()=>rank(candidates,candidates,'2020-01-01','etf_sector_403030',data),/缺少板块量能/);
const partial=JSON.parse(JSON.stringify(data));delete partial.byDate[day].A;
assert.throws(()=>rank(candidates,candidates,day,'etf_sector_403030',partial),/缺少完整/);
partial.mappedNames=['B','C'];partial.unmappedNames=['A'];
assert.equal(rank(candidates,candidates,day,'etf_sector_403030',partial).length,3,'Unmapped ETF remains eligible');
const falling=[{name:'A',gain:-.01,gain20:0},{name:'B',gain:.01,gain20:0}];
const directed=JSON.parse(JSON.stringify(data));directed.byDate[day].A.volumeRatio=100;
assert.equal(rank(falling,falling,day,'etf_sector_403030',directed)[0].name,'B','Huge down-day volume must not be rewarded');
const nullAmount=JSON.parse(JSON.stringify(data));nullAmount.byDate[day].B.amountShare=null;
assert.throws(()=>rank(candidates,candidates,day,'etf_sector_40203010',nullAmount),/缺少完整的行业成交额占比/);
// Current full-history baseline is unchanged by adding new methods.
const snapshotPath=path.join(__dirname,'../../back_test_data/ranking_volume_research/inputs.json');
if(fs.existsSync(snapshotPath)) {
  const input=JSON.parse(fs.readFileSync(snapshotPath,'utf8'));
  const params={...DEFAULT_STRATEGY_PARAMS,startYear:2019,endYear:2026,bullStartUseMA10:false,profitProtectionEnabled:true};
  const result=runBacktest(input.amv,input.etfs,params);
  assert.ok(Math.abs(result.totalReturn*100-853.77)<.01);
  const featuresPath=path.join(__dirname,'../../back_test_data/ranking_volume_research/production_features.json');
  if(fs.existsSync(featuresPath)) {
    const features=JSON.parse(fs.readFileSync(featuresPath,'utf8'));
    const volume=runBacktest(input.amv,input.etfs,{...params,startYear:2025,rankingMethod:'etf_sector_403030'},undefined,undefined,undefined,features);
    assert.ok(volume.trades.some(t=>t.type==='bull'&&t.holdings.some(h=>h.entry_sector_volume_ratio>0)));
    if (features.amountAvailable) {
      const fourResult=runBacktest(input.amv,input.etfs,{...params,startYear:2025,rankingMethod:'etf_sector_40203010'},undefined,undefined,undefined,features);
      assert.ok(fourResult.trades.some(t=>t.type==='bull'&&t.holdings.some(h=>h.entry_sector_amount_share>0)));
    } else {
      assert.throws(()=>runBacktest(input.amv,input.etfs,{...params,startYear:2025,rankingMethod:'etf_sector_40203010'},undefined,undefined,undefined,features),/缺少行业成交额/);
    }
  }
}
console.log('Sector volume rankings: weights, direction, missing data, history and baseline passed.');
