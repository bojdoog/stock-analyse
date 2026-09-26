import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Empty, Modal, Spin } from 'antd';
import { init, EChartsOption } from 'echarts';
import './IntradayModal.less';

interface Snapshot { time: string; amv: number }
interface Result {
  data: Snapshot[];
  meta: { date: string; code: string; name: string; count: number; previousClose: number | null;
    previousCloseDate: string | null; previousDate: string | null; nextDate: string | null };
}
const number = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const pct = (value: number, base: number | null) => base ? `${value >= base ? '+' : ''}${((value / base - 1) * 100).toFixed(2)}%` : '—';
const shade = (value: number) => value >= 0 ? '#dc5261' : '#159b79';

function Chart({ result }: { result: Result }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = init(ref.current);
    const { data, meta } = result;
    // Fixed trading-minute slots preserve gaps instead of compressing missing records.
    const times = Array.from({ length: 240 }, (_, i) => {
      const minute = i < 120 ? 570 + i : 780 + i - 120;
      return `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
    });
    const byMinute = new Map(data.map((point, i) => [point.time.slice(0, 5), { ...point, i }]));
    let sum = 0;
    const means = data.map((point, i) => (sum += point.amv) / (i + 1));
    const values = data.map(point => point.amv);
    const base = meta.previousClose;
    const center = base || (Math.min(...values) + Math.max(...values)) / 2;
    const spread = Math.max(...values.map(value => Math.abs(value - center)), center * 0.001) * 1.12;
    const min = center - spread, max = center + spread;
    const option: EChartsOption = {
      animation: false,
      color: ['#167d8d', '#d7a33e'],
      legend: { top: 4, data: ['活跃市值', '分时算术均值'], textStyle: { color: '#657780' } },
      grid: [{ left: 88, right: 78, top: 46, height: '57%' }, { left: 88, right: 78, top: '76%', bottom: 32 }],
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      tooltip: { trigger: 'axis', confine: true, axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const point = byMinute.get(params[0]?.axisValue);
          if (!point) return '该分钟无记录';
          const change = point.i ? point.amv - data[point.i - 1].amv : null;
          return `<b>${meta.date} ${point.time}</b><br/>活跃市值　${number(point.amv)}<br/>较昨收　${pct(point.amv, base)}<br/>分时算术均值　${number(means[point.i])}<br/>较上一记录　${number(change)}`;
        } },
      xAxis: [0, 1].map(gridIndex => ({ type: 'category' as const, gridIndex, data: times, boundaryGap: false,
        axisLine: { lineStyle: { color: '#dce5e8' } }, axisTick: { show: false },
        axisLabel: { show: gridIndex === 1, color: '#809198', interval: (i: number) => [0, 60, 120, 180, 239].includes(i) },
        splitLine: { show: true, interval: 59, lineStyle: { color: '#edf1f3', type: 'dashed' as const } } })),
      yAxis: [{ type: 'value', min, max, splitNumber: 4, axisLabel: { color: '#809198', formatter: (v: number) => v.toFixed(0) },
        splitLine: { lineStyle: { color: '#edf1f3' } } },
      { type: 'value', min, max, position: 'right', splitNumber: 4, splitLine: { show: false },
        axisLabel: { color: '#809198', formatter: (v: number) => pct(v, base) } },
      { type: 'value', gridIndex: 1, name: '相邻记录变化', nameTextStyle: { color: '#809198' },
        axisLabel: { color: '#809198' }, splitNumber: 2, splitLine: { lineStyle: { color: '#edf1f3' } } }],
      series: [{ name: '活跃市值', type: 'line', symbol: 'none', connectNulls: false,
        data: times.map(time => byMinute.get(time)?.amv ?? null), lineStyle: { width: 2 },
        areaStyle: { color: '#167d8d', opacity: 0.045 },
        markLine: base ? { silent: true, symbol: 'none', label: { formatter: '昨收', position: 'insideStartTop' },
          lineStyle: { color: '#9aaab1', type: 'dashed' }, data: [{ yAxis: base }] } : undefined },
      { name: '分时算术均值', type: 'line', symbol: 'none', lineStyle: { width: 1.3 },
        data: times.map(time => { const point = byMinute.get(time); return point ? means[point.i] : null; }) },
      { name: '相邻记录变化', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, barMaxWidth: 5,
        data: times.map(time => { const point = byMinute.get(time);
          if (!point || !point.i) return null;
          const value = point.amv - data[point.i - 1].amv;
          return { value, itemStyle: { color: shade(value) } }; }) }],
    };
    chart.setOption(option);
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(ref.current);
    return () => { resize.disconnect(); chart.dispose(); };
  }, [result]);
  return <div ref={ref} className="amv-intraday-chart" aria-label="活跃市值日内走势图" />;
}

export default function IntradayModal({ indicatorId, date, onDateChange, onClose }: {
  indicatorId: number; date: string | null; onDateChange: (date: string) => void; onClose: () => void;
}) {
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    setResult(null); setError('');
    if (!date) return;
    const controller = new AbortController();
    setLoading(true);
    fetch(`/api/indicators/${indicatorId}/intraday?date=${encodeURIComponent(date)}`, { signal: controller.signal })
      .then(async response => {
        const body = await response.json();
        if (!response.ok || body.code !== 0) throw new Error(body.message || '分时数据加载失败');
        if (!controller.signal.aborted) setResult(body);
      }).catch(err => { if (!controller.signal.aborted) setError(err.message || '分时数据加载失败'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [date, indicatorId, retry]);
  const current = result?.meta.date === date ? result : null;
  const points = current?.data || [];
  const last = points[points.length - 1];
  const base = current?.meta.previousClose ?? null;
  return <Modal open={!!date} onCancel={onClose} footer={null} width={1080} centered destroyOnClose
    title={<span>活跃市值 <span className="amv-intraday-subtitle">/ 日内走势</span></span>}>
    <div className="amv-intraday-toolbar">
      <span><b>{date}</b><span className="amv-intraday-subtitle">　0AMV · 分时快照</span></span>
      <div><Button size="small" disabled={loading || !current?.meta.previousDate}
        onClick={() => current?.meta.previousDate && onDateChange(current.meta.previousDate)}>上一日</Button>
        <Button size="small" disabled={loading || !current?.meta.nextDate}
          onClick={() => current?.meta.nextDate && onDateChange(current.meta.nextDate)}>下一日</Button></div>
    </div>
    {loading ? <div className="amv-intraday-state"><Spin tip="正在查询日内走势"><div style={{ width: 200, height: 80 }} /></Spin></div>
      : error ? <div className="amv-intraday-state"><Alert type="error" showIcon message={error}
        action={<Button onClick={() => setRetry(value => value + 1)}>重试</Button>} /></div>
      : !last || !current ? <div className="amv-intraday-state"><Empty description="该日期暂无日内数据，可切换至前后有数据的日期" /></div>
      : <>
        <div className="amv-intraday-stats">
          <div><span>末笔值 · {last.time}</span><strong style={{ color: base ? shade(last.amv - base) : '#167d8d' }}>{number(last.amv)}</strong></div>
          <div><span>较昨收</span><strong style={{ color: base ? shade(last.amv - base) : undefined }}>{pct(last.amv, base)}</strong></div>
          <div><span>日内最高</span><strong>{number(Math.max(...points.map(p => p.amv)))}</strong></div>
          <div><span>日内最低</span><strong>{number(Math.min(...points.map(p => p.amv)))}</strong></div>
          <div><span>昨收 · {current.meta.previousCloseDate || '暂无'}</span><strong>{number(base)}</strong></div>
        </div>
        <Chart result={current} />
        <div className="amv-intraday-footnote">{points.length} 条记录 · {points[0].time} — {last.time} · 黄线为分时算术均值；柱形为相邻记录变化。末笔值不等同于收盘值。</div>
      </>}
  </Modal>;
}
