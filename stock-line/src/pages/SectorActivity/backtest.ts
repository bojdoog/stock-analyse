export interface PricePoint { date: string; price: number }
export interface Trade {
  signalDate: string; entryDate: string; entryPrice: number;
  exitSignalDate?: string; endDate: string; endPrice: number;
  open: boolean; returnPct: number;
}
export function drawdowns(values: number[]) {
  let peak = values[0] ?? 1;
  let max = 0, sum = 0, count = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    const drop = (1 - value / peak) * 100;
    max = Math.max(max, drop);
    if (drop > 0) { sum += drop; count++; }
  }
  return { maxDD: max, avgDD: count ? sum / count : 0 };
}
// 信号日收盘后才能知道信号；仅有收盘价，统一次日收盘成交。
export function runSectorBacktest(points: PricePoint[], signals: { event: 'start' | 'exit' | null }[]) {
  const trades: Trade[] = [];
  const navSeries: { date: string; nav: number; benchmark: number }[] = [];
  let nav = 1;
  let holding: Trade | null = null;
  points.forEach((point, index) => {
    if (holding && index > 0) nav *= point.price / points[index - 1].price;
    const previous = signals[index - 1];
    if (previous?.event === 'exit' && holding) {
      holding.exitSignalDate = points[index - 1].date;
      holding.endDate = point.date;
      holding.endPrice = point.price;
      holding.open = false;
      holding.returnPct = (point.price / holding.entryPrice - 1) * 100;
      trades.push(holding);
      holding = null;
    } else if (previous?.event === 'start' && !holding) {
      holding = { signalDate: points[index - 1].date, entryDate: point.date, entryPrice: point.price,
        endDate: point.date, endPrice: point.price, open: true, returnPct: 0 };
    }
    navSeries.push({ date: point.date, nav, benchmark: point.price / points[0].price });
  });
  if (holding && points.length) {
    const last = points[points.length - 1];
    const trade = holding as Trade;
    trades.push({ ...trade, endDate: last.date, endPrice: last.price,
      exitSignalDate: signals[signals.length - 1]?.event === 'exit' ? last.date : undefined,
      returnPct: (last.price / trade.entryPrice - 1) * 100 });
  }
  const years: { year: string; startDate: string; endDate: string; startNav: number; endNav: number; returnPct: number; maxDD: number; avgDD: number }[] = [];
  let offset = 0;
  while (offset < navSeries.length) {
    const year = navSeries[offset].date.slice(0, 4);
    let end = offset;
    while (end + 1 < navSeries.length && navSeries[end + 1].date.startsWith(year)) end++;
    const startNav = offset ? navSeries[offset - 1].nav : 1;
    const endNav = navSeries[end].nav;
    years.push({ year, startDate: navSeries[offset].date, endDate: navSeries[end].date, startNav, endNav,
      returnPct: (endNav / startNav - 1) * 100,
      ...drawdowns([startNav, ...navSeries.slice(offset, end + 1).map(point => point.nav)]) });
    offset = end + 1;
  }
  return { navSeries, trades, years, totalReturn: (nav - 1) * 100,
    ...drawdowns(navSeries.map(point => point.nav)),
    benchmarkReturn: navSeries.length ? (navSeries[navSeries.length - 1].benchmark - 1) * 100 : 0 };
}
export type SectorBacktestResult = ReturnType<typeof runSectorBacktest>;
