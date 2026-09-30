const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const research = path.join(__dirname, '../../back_test_data/strategy_failure_research');
const input = JSON.parse(fs.readFileSync(path.join(research, 'selection_inputs.json'), 'utf8'));
const expected = JSON.parse(fs.readFileSync(path.join(research, 'selection_results.json'), 'utf8'));
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/pages/ActiveMarket/utils/backtest.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText,
  { module: mod, exports: mod.exports });
const { runBacktest } = mod.exports;
const baseline = runBacktest(input.amv, input.etfs, expected.params);
const actual = runBacktest(input.amv, input.etfs, { ...expected.params, rankingMethod: 'etf_blend20' });
const summary = expected.summary.find(row => row.method === 'blend20');
assert.ok(Math.abs(actual.totalReturn * 100 - summary.total_pct) < 1e-8);
for (const year of actual.yearResults) assert.equal(year.annual_return, summary.annual[year.year]);
for (const [date, rows] of Object.entries(expected.focus)) {
  const trade = actual.trades.find(t => t.type === 'bull' && t.start_date === date);
  assert.deepEqual(JSON.parse(JSON.stringify(trade.holdings.map(({entry_20d_change, ...holding}) => holding))), rows.blend20.holdings);
  const oldDate = input.amv[input.amv.findIndex(row => row.date === date) - 20].date;
  for (const holding of trade.holdings) {
    const series = input.etfs.filter(s => s.name === holding.name).at(-1);
    const entry = series.data.find(row => row.date === date).close;
    const old = series.data.find(row => row.date === oldDate)?.close;
    if (old > 0) assert.ok(Math.abs(holding.entry_20d_change - (entry / old - 1) * 100) < 1e-9);
    else assert.equal(holding.entry_20d_change, null);
  }
  assert.ok(Math.abs(trade.return * 100 - rows.blend20.return_pct) < 1e-9);
}
assert.deepEqual(actual.zones, baseline.zones);
assert.deepEqual(actual.trades.filter(t => t.type === 'bear'), baseline.trades.filter(t => t.type === 'bear'));
assert.equal(mod.exports.DEFAULT_STRATEGY_PARAMS.rankingMethod, 'etf_blend20');
console.log('PASS: mixed selection matches research returns, years and holdings; signals and bank trades unchanged; mixed ranking is default');
