export interface SignalParams {
  startDay: number;
  startTwoDays: number;
  requireMA10: boolean;
  requireQuantity: boolean;
  exitDrop: number;
  exitMA10: boolean;
  exitDays: number;
}
export const DEFAULT_SIGNAL_PARAMS: SignalParams = {
  startDay: 6, startTwoDays: 8, requireMA10: true, requireQuantity: true,
  exitDrop: 4, exitMA10: true, exitDays: 2,
};
interface SignalPoint { date: string; amv: number; ma10: number | null; quantity_change: number | null }
export function calculateZoneReturns(points: { date: string; price: number }[], signals: { bull: boolean; event: 'start' | 'exit' | null }[]) {
  const result: { start: string; end: string; open: boolean; total: number | null; realtime: number | null }[] = [];
  let start = 0;
  while (start < points.length) {
    let next = start + 1;
    const isBull = signals[start].bull || signals[start].event === 'exit';
    if (isBull) {
      next = start;
      while (next < points.length && signals[next].event !== 'exit') next++;
      if (next < points.length) next++;
    } else {
      while (next < points.length && signals[next].event !== 'start') next++;
    }
    const end = isBull ? next - 1 : Math.min(next, points.length - 1);
    // 退出日归多头；空头从下一日展示，收益仍以退出日收盘为基准。
    const base = !isBull && start > 0 && signals[start - 1].event === 'exit' ? start - 1 : start;
    const price = points[base].price;
    for (let index = start; index < next; index++) {
      result.push({ start: points[base].date, end: points[end].date, open: next === points.length && signals[end].event !== 'exit',
        total: price > 0 ? (points[end].price / price - 1) * 100 : null,
        realtime: price > 0 ? (points[index].price / price - 1) * 100 : null });
    }
    start = next;
  }
  return result;
}
export function calculateSignals(points: SignalPoint[], params: SignalParams) {
  let bull = false;
  let belowDays = 0;
  return points.map((point, index) => {
    const previous = points[index - 1];
    const twoAgo = points[index - 2];
    const day = previous?.amv > 0 ? (point.amv / previous.amv - 1) * 100 : null;
    const twoDays = twoAgo?.amv > 0 ? (point.amv / twoAgo.amv - 1) * 100 : null;
    let event: 'start' | 'exit' | null = null;
    let reason = '';
    if (bull) {
      belowDays = point.ma10 != null && point.amv < point.ma10 ? belowDays + 1 : 0;
      const drop = day != null && day <= -params.exitDrop;
      const below = params.exitMA10 && belowDays >= params.exitDays;
      if (drop || below) {
        bull = false;
        event = 'exit';
        reason = [drop ? '单日跌幅达到退出阈值' : '', below ? `连续${params.exitDays}日低于MA10` : ''].filter(Boolean).join('；');
        belowDays = 0;
      }
    } else if (((day != null && day >= params.startDay) || (twoDays != null && twoDays >= params.startTwoDays))
      && (!params.requireMA10 || (point.ma10 != null && point.amv > point.ma10))
      && (!params.requireQuantity || (point.quantity_change != null && point.quantity_change > 0))) {
      bull = true;
      event = 'start';
      reason = day != null && day >= params.startDay ? '单日涨幅达到启动阈值' : '两日累计涨幅达到启动阈值';
    }
    return { date: point.date, bull, zoneBull: bull || event === 'exit', event, reason };
  });
}
