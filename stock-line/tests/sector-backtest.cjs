const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const moduleResult = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/pages/SectorActivity/backtest.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: moduleResult.exports });
const { runSectorBacktest, drawdowns } = moduleResult.exports;
const points = [100, 110, 121, 100, 90, 150].map((price, i) => ({ price, date: ['2024-12-27', '2024-12-30', '2024-12-31', '2025-01-02', '2025-01-03', '2025-01-06'][i] }));
const signals = ['start', null, 'exit', null, 'start', null].map(event => ({ event }));
const result = runSectorBacktest(points, signals);
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);
assert.equal(result.trades[0].entryDate, points[1].date);
assert.equal(result.trades[0].endDate, points[3].date);
near(result.navSeries[1].nav, 1); // No profit before entry execution.
near(result.navSeries[2].nav, 1.1);
near(result.navSeries[3].nav, 100 / 110); // Exit-day execution move included.
near(result.navSeries[4].nav, 100 / 110); // Cash avoids subsequent loss.
near(result.navSeries[5].nav, 100 / 110); // New entry does not capture prior rise.
assert.equal(result.trades[1].open, true);
near(result.trades[1].returnPct, 0);
near(result.years[0].returnPct, 10);
near(result.years[1].returnPct, (100 / 121 - 1) * 100);
near(result.years.reduce((v, y) => v * (1 + y.returnPct / 100), 1), 1 + result.totalReturn / 100);
near(result.maxDD, (1 - 100 / 121) * 100);
near(drawdowns([1, 2, 1.5, 2, 1]).avgDD, 37.5);
const lastSignal = runSectorBacktest(points.slice(0, 1), [{ event: 'start' }]);
assert.equal(lastSignal.trades.length, 0);
const pendingExit = runSectorBacktest(points.slice(0, 3), signals.slice(0, 3));
assert.equal(pendingExit.trades[0].open, true);
near(pendingExit.totalReturn, 10);
const empty = runSectorBacktest([], []);
near(empty.totalReturn, 0);
assert.equal(empty.years.length, 0);
for (let n = 1; n < points.length; n++) {
  assert.equal(JSON.stringify(runSectorBacktest(points.slice(0, n), signals.slice(0, n)).navSeries), JSON.stringify(result.navSeries.slice(0, n)));
}
console.log('PASS: next-close execution, cash, open positions, year compounding, drawdowns and causal NAV');
