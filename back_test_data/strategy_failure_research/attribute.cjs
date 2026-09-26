// Descriptive attribution only: uses the existing same-close execution assumption.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'stock-line/node_modules/typescript'));
const source = fs.readFileSync(path.join(root, 'stock-line/src/pages/ActiveMarket/utils/backtest.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const moduleValue = { exports: {} };
vm.runInNewContext(code, { module: moduleValue, exports: moduleValue.exports });
const { runBacktest, DEFAULT_STRATEGY_PARAMS } = moduleValue.exports;
const { amv, etfs } = JSON.parse(fs.readFileSync(path.join(__dirname, 'inputs.json'), 'utf8'));
const result = runBacktest(amv, etfs, { ...DEFAULT_STRATEGY_PARAMS, endYear: 2026 });
fs.writeFileSync(path.join(__dirname, 'baseline.json'), JSON.stringify(result));
const prices = new Map(etfs.map(series => [series.name, new Map(series.data.map(row => [row.date, row.close]))]));
const amvMap = new Map(amv.map((row, i) => [row.date, { ...row, i }]));
const trades = result.trades.filter(t => t.type === 'bull' && !t.is_open).map(trade => {
  const start = amvMap.get(trade.start_date);
  const end = amvMap.get(trade.end_date);
  const curve = amv.slice(start.i, end.i + 1).map(row => {
    const values = trade.holdings.map(holding => {
      const entry = prices.get(holding.name)?.get(trade.start_date);
      const current = prices.get(holding.name)?.get(row.date);
      return entry && current ? holding.weight * (current / entry - 1) : null;
    });
    return { date: row.date, value: values.some(v => v === null) ? null : values.reduce((a, b) => a + b, 0) };
  });
  const valid = curve.filter(point => point.value !== null);
  const peak = valid.reduce((best, point) => point.value > best.value ? point : best, valid[0]);
  const loss = trade.return <= 0;
  const before = amv.slice(Math.max(0, start.i - 59), start.i + 1);
  const earlier = amv.slice(Math.max(0, start.i - 64), start.i - 4);
  const ma60 = before.reduce((sum, row) => sum + row.close, 0) / before.length;
  const priorMA60 = earlier.reduce((sum, row) => sum + row.close, 0) / earlier.length;
  if (curve[0].value !== 0 || Math.abs(curve.at(-1).value - trade.return) > 1e-9) throw Error('Portfolio curve does not reconcile');
  return { start: trade.start_date, end: trade.end_date, sessions: end.i - start.i,
    return_pct: trade.return * 100, amv_return_pct: trade.amv_return * 100,
    peak_close_profit_pct: peak.value * 100, peak_date: peak.date,
    worst_close_profit_pct: Math.min(...valid.map(p => p.value)) * 100,
    giveback_pp: (peak.value - trade.return) * 100, missing_curve_days: curve.length - valid.length,
    entry_below_ma60: start.close < ma60, entry_ma60_falling: ma60 < priorMA60,
    timing_failure: loss && trade.amv_return <= 0,
    selection_failure: loss && trade.amv_return > 0,
    profit_to_loss: loss && peak.value >= .02,
    holdings: trade.holdings.map(h => ({ name: h.name, weight: h.weight, return_pct: h.holding_return * 100 })) };
});
const periods = [['2023', '2023-01-01', '2023-12-31'], ['2024H1', '2024-01-01', '2024-06-30'],
  ['2024H2', '2024-07-01', '2024-12-31'], ['2025', '2025-01-01', '2025-12-31'], ['2026', '2026-01-01', '2026-09-24']];
const summary = periods.map(([name, first, last]) => {
  const selected = trades.filter(t => t.start >= first && t.start <= last);
  return { period: name, trades: selected.length, wins: selected.filter(t => t.return_pct > 0).length,
    losses: selected.filter(t => t.return_pct <= 0).length,
    timing_failures: selected.filter(t => t.timing_failure).length,
    selection_failures: selected.filter(t => t.selection_failure).length,
    profit_2pct_to_loss: selected.filter(t => t.profit_to_loss).length,
    bull_only_compounded_pct: (selected.reduce((nav, t) => nav * (1 + t.return_pct / 100), 1) - 1) * 100,
    losers_below_ma60: selected.filter(t => t.return_pct <= 0 && t.entry_below_ma60).length,
    winners_below_ma60: selected.filter(t => t.return_pct > 0 && t.entry_below_ma60).length };
});
const report = { assumptions: ['Current UI ETF universe and DEFAULT_STRATEGY_PARAMS, not the unobserved browser settings.',
  'Existing signal-date close execution; no fees/slippage; descriptive, not executable performance.',
  'Closed bull trades grouped by start date; profit-to-loss tag overlaps timing/selection tags.',
  'Profit-to-loss means closing-price portfolio profit reached at least 2%; not intraday high.',
  'Bull-only compounded returns exclude bank trades and differ from calendar-year mark-to-market results.',
  'ETF historical availability/adjustment and same-close lookahead require separate audit before optimization.'],
  parameters: DEFAULT_STRATEGY_PARAMS, summary, annual: result.yearResults, trades };
fs.writeFileSync(path.join(__dirname, 'attribution.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ summary, annual: result.yearResults.filter(r => r.year >= 2023),
  researchTrades: trades.filter(t => t.start >= '2023-01-01' && t.start <= '2024-06-30') }, null, 2));
