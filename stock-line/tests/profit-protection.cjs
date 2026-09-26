const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/pages/ActiveMarket/utils/backtest.ts'), 'utf8');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
  { module: mod, exports: mod.exports });
const { calculateProfitProtection: protect, runBacktest, DEFAULT_STRATEGY_PARAMS: defaults } = mod.exports;
const near = (a, b, message) => assert.ok(Math.abs(a - b) < 1e-9, message || `${a} != ${b}`);
const days = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09'];
assert.equal(defaults.profitProtectionEnabled, false);
let result = protect(days, [1], [[100], [110], [107.8], [120], [130]], 4, 2);
assert.equal(result.status.armed_date, days[1]);
assert.equal(result.status.trigger_date, days[2]);
near(result.curve.at(-1).nav, .5 * 1.078 + .5 * 1.3);
near(result.holdingReturns[0], result.curve.at(-1).nav - 1);
// A jump below the threshold is filled at the actual close, not the stop price.
result = protect(days, [1], [[100], [105], [99], [110], [120]], 4, 2);
near(result.status.trigger_return, -.01);
near(result.curve.at(-1).nav, 1.095);
assert.equal(result.status.trigger_date, days[2]);
// Configured thresholds materially change the trigger, while old highs stay causal.
const loose = protect(days, [1], [[100], [105], [99], [110], [120]], 20, 10);
assert.equal(loose.status.trigger_date, undefined);
near(loose.curve.at(-1).nav, 1.2);
const changedFuture = protect(days, [1], [[100], [105], [99], [110], [1000]], 4, 2);
assert.equal(changedFuture.status.trigger_date, result.status.trigger_date);
for (let i = 0; i < 4; i++) near(changedFuture.curve[i].nav, result.curve[i].nav);
// A normal final exit takes priority; an open interval may protect on its latest date.
assert.equal(protect(days.slice(0, 3), [1], [[100], [110], [100]], 4, 2).status.trigger_date, undefined);
assert.equal(protect(days.slice(0, 3), [1], [[100], [110], [100]], 4, 2, true).status.trigger_date, days[2]);
// Portfolio (including cash) trigger, not a single ETF's return; stale prices cannot trigger a sale.
assert.equal(protect(days.slice(0, 3), [.5], [[100], [110], [100]], 6, 2, true).status.armed_date, undefined);
result = protect(days, [.5, .5], [[100, 100], [110, 110], [90, null], [105, 105], [120, 120]], 4, 2);
assert.equal(result.status.trigger_date, days[3]);
near(result.curve[2].nav, 1);
near(result.curve.at(-1).nav - 1, result.holdingReturns.reduce((sum, value) => sum + .5 * value, 0));
assert.throws(() => protect(days, [1], [[100], [105], [99], [110], [120]], 4, 100));
console.log('PASS: thresholds, exact boundary, one half-sale, actual fill, idle cash, stale quotes and causality');

const research = path.join(__dirname, '../../back_test_data/strategy_failure_research');
if (fs.existsSync(path.join(research, 'inputs.json')) && fs.existsSync(path.join(research, 'experiments.json'))) {
  const input = JSON.parse(fs.readFileSync(path.join(research, 'inputs.json'), 'utf8'));
  const previous = JSON.parse(fs.readFileSync(path.join(research, 'baseline.json'), 'utf8'));
  const params = { ...defaults, endYear: 2026 };
  const disabled = runBacktest(input.amv, input.etfs, params);
  assert.deepEqual(JSON.parse(JSON.stringify(disabled)), previous, 'Disabled protection must preserve every baseline output');
  const expected = JSON.parse(fs.readFileSync(path.join(research, 'experiments.json'), 'utf8'));
  const active = runBacktest(input.amv, input.etfs, { ...params, profitProtectionEnabled: true });
  let count = 0;
  for (const trade of active.trades) {
    const reference = expected.trades.find(t => t.rule === 'protect_4_2' && t.type === trade.type && t.start === trade.start_date);
    assert.ok(reference);
    near(trade.return * 100, reference.return_pct, `Trade parity ${trade.start_date}`);
    if (trade.protection?.trigger_date) {
      assert.equal(trade.protection.trigger_date, reference.actions[0].date);
      count++;
    }
  }
  const final = active.trades.reduce((nav, trade) => nav * (1 + trade.return), 1);
  assert.ok(Math.abs(active.navSeries.at(-1).nav - final) < 1e-6);
  assert.ok(Math.abs(active.finalNav - final) < .000051);
  const restored = runBacktest(input.amv, input.etfs, { ...params, profitProtectionEnabled: false, profitProtectionArmPct: 9 });
  assert.deepEqual(JSON.parse(JSON.stringify(restored)), previous);
  console.log(`PASS: full baseline unchanged, ${count} real protection events match research, NAV/returns reconcile, toggle-off restores baseline`);
}
