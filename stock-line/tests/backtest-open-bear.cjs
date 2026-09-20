const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function load(file, dependencies = {}, globals = {}) {
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: key => {
    if (!(key in dependencies)) throw Error(key);
    return dependencies[key];
  }, ...globals });
  return module.exports;
}
const backtest = load('src/pages/ActiveMarket/utils/backtest.ts');
const bar = (day, close) => ({ date: `2026-09-${day}`, open: close, high: close, low: close, close, volume: 1, amount: 1 });
const amv = [bar('10', 100), bar('11', 99), bar('14', 98), bar('15', 97), bar('18', 96)];
const params = { ...backtest.DEFAULT_STRATEGY_PARAMS, startYear: 2026, endYear: 2026 };
function run(prices) {
  return backtest.runBacktest(amv, [{ name: '银行ETF', id: '512800', data: prices }], params);
}
const stale = run([bar('10', 100), bar('11', 110)]);
assert.equal(stale.trades.length, 1, 'unfinished bear must not disappear when latest quote is missing');
assert.equal(stale.trades[0].is_open, true);
assert.equal(stale.trades[0].valuation_date, '2026-09-11');
assert.equal(stale.trades[0].end_date, '2026-09-18');
assert.ok(Math.abs(stale.totalReturn - .1) < 1e-10);
assert.equal(stale.navSeries.at(-1).nav, 1.1);
const fresh = run([bar('10', 100), bar('11', 110), bar('14', 120), bar('18', 125), bar('21', 999)]);
assert.equal(fresh.trades[0].valuation_date, '2026-09-18');
assert.equal(fresh.navSeries.at(-1).date, '2026-09-18', 'do not extend beyond indicator history');
assert.equal(fresh.navSeries.at(-1).nav, 1.25, 'missing intermediate quote must not lose later gains');
assert.equal(fresh.yearResults[0].bear_return, 25);

// Render the annual chart with trades ending earlier than the latest NAV.
let option;
const effects = [];
let refs = 0;
const react = { createElement() {}, useMemo: fn => fn(), useState: () => [null, () => {}],
  useRef: value => ({ current: refs++ === 0 ? {} : value }), useEffect: fn => effects.push(fn) };
const chart = { setOption: value => { option = value; }, dispose() {}, resize() {}, getZr: () => ({ on() {} }) };
const Component = load('src/pages/ActiveMarket/components/BacktestChart.tsx', {
  react, echarts: { init: () => chart }, '../utils/backtest': backtest,
}, { ResizeObserver: class { observe() {} disconnect() {} } }).default;
const shortened = { ...stale, trades: stale.trades.map(t => ({ ...t, end_date: '2026-09-11' })) };
Component({ result: shortened, year: 2026 });
effects.forEach(fn => fn());
assert.equal(option.xAxis.data.at(-1), '2026-09-18', 'chart must include unfinished tail');
console.log('PASS: open bear valuation, stale quotes, later updates, annual totals and chart tail');
