import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, DatePicker, Empty, Modal, Spin } from 'antd';
import dayjs from 'dayjs';
import { init, EChartsOption } from 'echarts';
import '../ActiveMarket/components/IntradayModal.less';

interface Point { time: string; open: number; high: number; low: number; close: number; volume: number; amount: number }
interface Result {
  data: Point[];
  meta: { date: string; requestedDate: string; fromSina: 'Y' | 'N'; availableFrom: string | null; availableTo: string | null;
    code: string; name: string; count: number; previousClose: number | null;
    previousCloseDate: string | null; previousDate: string | null; nextDate: string | null };
}

const number = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 3 });
const pct = (value: number, base: number | null) => base ? `${value >= base ? '+' : ''}${((value / base - 1) * 100).toFixed(2)}%` : '—';
const shade = (value: number) => value >= 0 ? '#dc5261' : '#159b79';

// 09:31–11:30、13:01–15:00，共 240 个交易分钟
const SLOTS = Array.from({ length: 240 }, (_, i) => {
  const minute = i < 120 ? 571 + i : 781 + i - 120;
  return `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
});

function Chart({ result }: { result: Result }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = init(ref.current);
    const { data, meta } = result;
    const byMinute = new Map(data.map(point => [point.time.slice(0, 5), point]));
    const prices = data.map(point => point.close);
    const base = meta.previousClose;
    const center = base || (Math.min(...prices) + Math.max(...prices)) / 2;
    const spread = Math.max(...prices.map(value => Math.abs(value - center)), center * 0.001) * 1.12;
    const min = center - spread, max = center + spread;
    const avg: (number | null)[] = [];
    let cumAmount = 0, cumVolume = 0;
    for (const point of data) {
      cumAmount += point.amount || 0;
      cumVolume += point.volume || 0;
      avg.push(cumVolume ? cumAmount / (cumVolume * 100) : null);
    }
    const indexByTime = new Map(data.map((point, i) => [point.time.slice(0, 5), i]));
    const option: EChartsOption = {
      animation: false,
      color: ['#167d8d', '#d7a33e'],
      legend: { top: 4, data: ['分时价格', '分时均价'], textStyle: { color: '#657780' } },
      grid: [{ left: 76, right: 74, top: 46, height: '57%' }, { left: 76, right: 74, top: '76%', bottom: 32 }],
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      tooltip: { trigger: 'axis', confine: true, axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const index = params[0]?.dataIndex ?? -1;
          const point = data[index];
          if (!point) return '该分钟无记录';
          return `<b>${meta.date} ${point.time.slice(0, 5)}</b><br/>价格　${number(point.close)}<br/>`
            + `较昨收　${pct(point.close, base)}<br/>分钟成交量　${number(point.volume)} 手<br/>`
            + `分钟成交额　${number(point.amount)}`;
        } },
      xAxis: [0, 1].map(gridIndex => ({ type: 'category' as const, gridIndex, data: SLOTS, boundaryGap: false,
        axisLine: { lineStyle: { color: '#dce5e8' } }, axisTick: { show: false },
        axisLabel: { show: gridIndex === 1, color: '#809198', interval: (i: number) => [0, 60, 120, 180, 239].includes(i) },
        splitLine: { show: true, interval: 59, lineStyle: { color: '#edf1f3', type: 'dashed' as const } } })),
      yAxis: [{ type: 'value', min, max, splitNumber: 4, axisLabel: { color: '#809198', formatter: (v: number) => v.toFixed(3) },
        splitLine: { lineStyle: { color: '#edf1f3' } } },
      { type: 'value', min, max, position: 'right', splitNumber: 4, splitLine: { show: false },
        axisLabel: { color: '#809198', formatter: (v: number) => pct(v, base) } },
      { type: 'value', gridIndex: 1, name: '成交量(手)', nameTextStyle: { color: '#809198', fontSize: 11 },
        axisLabel: { color: '#809198', formatter: (v: number) => v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : `${v}` },
        splitNumber: 2, splitLine: { lineStyle: { color: '#edf1f3' } } }],
      series: [
        { name: '分时价格', type: 'line', symbol: 'none', connectNulls: false,
          data: SLOTS.map(time => byMinute.get(time)?.close ?? null), lineStyle: { width: 2 },
          areaStyle: { color: '#167d8d', opacity: 0.045 },
          markLine: base ? { silent: true, symbol: 'none', label: { formatter: '昨收', position: 'insideStartTop' },
            lineStyle: { color: '#9aaab1', type: 'dashed' }, data: [{ yAxis: base }] } : undefined },
        { name: '分时均价', type: 'line', symbol: 'none', connectNulls: false,
          data: SLOTS.map(time => { const i = indexByTime.get(time); return i === undefined ? null : avg[i]; }),
          lineStyle: { width: 1.3 } },
        { name: '分钟成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, barMaxWidth: 4,
          data: SLOTS.map(time => byMinute.get(time)?.volume ?? null),
          itemStyle: { color: '#9fb3ba' } },
      ],
    };
    chart.setOption(option);
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(ref.current);
    return () => { resize.disconnect(); chart.dispose(); };
  }, [result]);
  return <div ref={ref} className="amv-intraday-chart" aria-label="ETF 分时走势图" />;
}

export default function EtfIntradayModal({ code, date, onDateChange, onClose }: {
  code: string; date: string | null; onDateChange: (date: string) => void; onClose: () => void;
}) {
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setResult(null); setError('');
    if (!date || !code) return;
    const controller = new AbortController();
    setLoading(true);
    fetch(`/api/etf_hj/${code}/intraday?date=${encodeURIComponent(date)}`, { signal: controller.signal })
      .then(async response => {
        const body = await response.json();
        if (!response.ok || body.code !== 0) throw new Error(body.message || '分时数据加载失败');
        // 后端在该日无分时数据时会就近回退，一次请求即可，无需前端二次跳转
        if (!controller.signal.aborted) setResult(body);
      }).catch(err => { if (!controller.signal.aborted) setError(err.message || '分时数据加载失败'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [date, code]);
  const current = result;
  const points = current?.data || [];
  const last = points[points.length - 1];
  const base = current?.meta.previousClose ?? null;
  const total = points.reduce((sum, point) => sum + (point.volume || 0), 0);
  return <Modal open={!!date} onCancel={onClose} footer={null} width={1080} centered destroyOnHidden
    title={<span>{current ? `${current.meta.name} ${current.meta.code}` : code} <span className="amv-intraday-subtitle">/ 日内走势</span></span>}>
    <div className="amv-intraday-toolbar">
      <span><b>{date}</b><span className="amv-intraday-subtitle">
        {current?.meta.fromSina === 'Y' ? '　已从新浪补拉入库' : '　分时 1 分钟'}</span></span>
      <div><DatePicker className="hj-date-picker" size="small" allowClear={false} value={date ? dayjs(date) : null}
        format="YYYY-MM-DD" disabled={loading} disabledDate={now => now.isAfter(dayjs(), 'day')}
        onChange={value => value && onDateChange(value.format('YYYY-MM-DD'))} />
        <Button size="small" disabled={loading || !current?.meta.previousDate}
        onClick={() => current?.meta.previousDate && onDateChange(current.meta.previousDate)}>上一日</Button>
        <Button size="small" disabled={loading || !current?.meta.nextDate}
          onClick={() => current?.meta.nextDate && onDateChange(current.meta.nextDate)}>下一日</Button></div>
    </div>
    {loading ? <div className="amv-intraday-state"><Spin tip="正在查询日内走势"><div style={{ width: 200, height: 80 }} /></Spin></div>
      : error ? <div className="amv-intraday-state"><Alert type="error" showIcon message={error} /></div>
      : !last || !current ? <div className="amv-intraday-state"><Empty description={
        current?.meta.availableFrom
          ? `该日期暂无分时数据；本地已保存 ${current.meta.availableFrom} ~ ${current.meta.availableTo}${current.meta.nextDate ? `，可点「下一日」查看 ${current.meta.nextDate}` : ''}`
          : '该日期暂无分时数据'} /></div>
      : <>
        <div className="amv-intraday-stats">
          <div><span>末笔价 · {last.time.slice(0, 5)}</span><strong style={{ color: base ? shade(last.close - base) : '#167d8d' }}>{number(last.close)}</strong></div>
          <div><span>较昨收</span><strong style={{ color: base ? shade(last.close - base) : undefined }}>{pct(last.close, base)}</strong></div>
          <div><span>日内最高</span><strong>{number(Math.max(...points.map(p => p.high)))}</strong></div>
          <div><span>日内最低</span><strong>{number(Math.min(...points.map(p => p.low)))}</strong></div>
          <div><span>昨日收盘 · {current.meta.previousCloseDate || '暂无'}</span><strong>{number(base)}</strong></div>
        </div>
        <Chart result={current} />
        <div className="amv-intraday-footnote">{points.length} 条记录 · {points[0].time.slice(0, 5)} — {last.time.slice(0, 5)} · 累计成交量 {(total / 1e4).toFixed(0)} 万手 · 均价 = 累计成交额 /（累计成交量 × 100）</div>
      </>}
  </Modal>;
}
