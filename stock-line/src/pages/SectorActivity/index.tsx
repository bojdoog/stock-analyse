import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Input, InputNumber, Spin, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as echarts from 'echarts';
import './style.less';
import BacktestPanel from './BacktestPanel';
import { runSectorBacktest } from './backtest';
import { calculateSignals, calculateZoneReturns, DEFAULT_SIGNAL_PARAMS, SignalParams } from './signals';

interface Point {
  date: string; amv: number; price: number; quantity: number; market: number;
  ma10: number | null; change: number | null; change5: number | null;
  price_change: number | null; quantity_change: number | null;
  price_contribution: number | null; activity_contribution: number | null;
  market_contribution: number | null; weight: number; turnover: number;
}
interface Sector extends Point { code: string; name: string }
interface Detail { code: string; name: string; series: Point[] }
const fmt = (n: number | null | undefined, unit = '%') => n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(2)}${unit}`;
const color = (n: number | null | undefined) => n == null || n === 0 ? '#7a898f' : n > 0 ? '#c45e65' : '#238672';
const numberCell = (n: number | null) => <span style={{ color: color(n), fontVariantNumeric: 'tabular-nums' }}>{fmt(n)}</span>;
async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok || body.code !== 0) throw new Error(body.message || '数据加载失败');
  return body;
}

function Trend({ points, signals, showZones, onHoverDate }: { points: Point[]; signals: ReturnType<typeof calculateSignals>; showZones: boolean; onHoverDate: (date: string | null) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const zoomRef = useRef<{ start: number; end: number } | null>(null);
  const legendRef = useRef<Record<string, boolean>>({ '全市场反推AMV': false });
  useEffect(() => {
    if (!ref.current || !points.length) return;
    const chart = echarts.init(ref.current);
    const base = points[0];
    const zoneReturns = calculateZoneReturns(points, signals);
    const end = points[points.length - 1].date;
    const cutoff = new Date(`${end}T00:00:00Z`);
    const month = cutoff.getUTCMonth();
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
    if (cutoff.getUTCMonth() !== month) cutoff.setUTCDate(0);
    const startDate = cutoff.toISOString().slice(0, 10);
    const startIndex = Math.max(0, points.findIndex(p => p.date >= startDate));
    const zoom = zoomRef.current ?? { startValue: startIndex, endValue: points.length - 1, rangeMode: ['value', 'value'] };
    const areas: any[] = [];
    let zoneStart = 0;
    signals.forEach((signal, index) => {
      if (index > 0 && signal.zoneBull !== signals[index - 1].zoneBull) {
        areas.push([{ xAxis: points[zoneStart].date, itemStyle: { color: signals[index - 1].zoneBull ? '#fff3bf66' : '#e2f0fa66' } }, { xAxis: signal.date }]);
        zoneStart = index;
      }
      if (index === signals.length - 1) areas.push([{ xAxis: points[zoneStart].date, itemStyle: { color: signal.zoneBull ? '#fff3bf66' : '#e2f0fa66' } }, { xAxis: signal.date }]);
    });
    const line = (name: string, data: (number | null)[], shade: string, dashed = false, yAxisIndex = 0) => ({
      name, type: 'line' as const, data, showSymbol: false, yAxisIndex,
      lineStyle: { color: shade, width: name === '板块活跃市值' ? 2.5 : 1.5, type: dashed ? 'dashed' as const : 'solid' as const },
      itemStyle: { color: shade },
    });
    chart.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        formatter: (entries: { dataIndex: number; seriesIndex: number; seriesName: string; marker: string; value: number | number[] | null }[]) => {
          if (!entries.length) return '';
          const keys = ['amv', 'price', 'market', 'ma10'] as const;
          const rows = entries.map(entry => {
            const key = keys[entry.seriesIndex];
            const value = points[entry.dataIndex]?.[key];
            const previous = points[entry.dataIndex - 1]?.[key];
            const change = value != null && previous != null && previous !== 0
              ? (value / previous - 1) * 100 : null;
            const normalizedValue = entry.seriesIndex === 0 ? points[entry.dataIndex].amv / base.amv * 100 : entry.value;
            const displayedValue = normalizedValue == null ? '—' : Number(normalizedValue).toFixed(2);
            return `<div style="display:flex;align-items:center;gap:12px">` +
              `<span style="flex:1">${entry.marker}${entry.seriesName}</span>` +
              `<strong style="color:${color(change)}">${fmt(change)}</strong>` +
              `<span style="color:#999">${displayedValue}</span></div>`;
          });
          const signal = signals[entries[0].dataIndex];
          const zone = zoneReturns[entries[0].dataIndex];
          const returns = `<div style="border-top:1px solid #eee;margin-top:8px;padding-top:6px">` +
            `<div style="color:#999;font-size:12px">本${signal.zoneBull ? '多头' : '空头'}区间：${zone.start} ～ ${zone.end}${zone.open ? '（未结束）' : ''}</div>` +
            `<div>区间总收益率${zone.open ? '（截至最新日）' : ''} <strong style="color:${color(zone.total)}">${fmt(zone.total)}</strong></div>` +
            `<div>区间实时收益率 <strong style="color:${color(zone.realtime)}">${fmt(zone.realtime)}</strong></div>` +
            `<div style="color:#999;font-size:12px">行业价格起点收盘至终点 / 悬停日收盘涨幅，非策略收益</div></div>`;
          return `${signal.date} · ${signal.zoneBull ? '多头' : '空头 / 观望'}${signal.event ? `<br/>${signal.event === 'start' ? '启动' : '退出'}：${signal.reason}` : ''}<div style="color:#999;font-size:12px">较上一交易日</div>${rows.join('')}${returns}`;
        },
      },
      legend: { top: 12, itemWidth: 18, selected: legendRef.current, textStyle: { color: '#6c8088', fontSize: 11 } },
      grid: { left: 65, right: 65, top: 80, bottom: 75 },
      xAxis: {
        type: 'category', data: points.map(p => p.date), boundaryGap: true,
        axisLine: { lineStyle: { color: '#dce4e6' } }, axisLabel: { color: '#819097', fontSize: 10 }
      },
      yAxis: [
        {
          type: 'value', position: 'left', name: '板块活跃市值 / MA10', scale: true,
          nameTextStyle: { color: '#167d8d', fontSize: 11 },
          splitLine: { lineStyle: { color: '#edf1f2' } }, axisLabel: { color: '#167d8d' }
        },
        {
          type: 'value', position: 'right', name: '行业价格 / 全市场AMV', scale: true,
          nameTextStyle: { color: '#819097', fontSize: 11 },
          splitLine: { show: false }, axisLabel: { color: '#819097' }
        },
      ],
      dataZoom: [{ type: 'inside', ...zoom }, { type: 'slider', ...zoom, bottom: 10, height: 22, borderColor: '#e3ebec', fillerColor: '#167d8d14' }],
      series: [
        {
          name: '板块活跃市值', type: 'candlestick', yAxisIndex: 0,
          itemStyle: { color: '#FFB6C1', color0: '#98FB98', borderColor: '#FFB6C1', borderColor0: '#98FB98' },
          data: points.map((point, index) => {
            const close = point.amv / base.amv * 100;
            const open = (points[index - 1]?.amv ?? point.amv) / base.amv * 100;
            const event = signals[index].event;
            const shade = event === 'start' ? '#c41e3a' : event === 'exit' ? '#006400' : close > open ? '#FFB6C1' : '#98FB98';
            return {
              value: [open, close, Math.min(open, close), Math.max(open, close)],
              itemStyle: { color: shade, color0: shade, borderColor: shade, borderColor0: shade }
            };
          }),
          markArea: { silent: true, data: showZones ? areas : [] },
        },
        line('行业价格', points.map(p => p.price / base.price * 100), '#d5a057', false, 1),
        line('全市场反推AMV', points.map(p => p.market / base.market * 100), '#9ba7b8', true, 1),
        line('活跃市值MA10', points.map(point => point.ma10 == null ? null : point.ma10 / base.amv * 100), '#87b4a8'),
      ],
    });
    chart.on('legendselectchanged', (event: any) => { legendRef.current = event.selected; });
    chart.on('updateAxisPointer', (event: any) => {
      const axis = event.axesInfo?.find((item: any) => item.axisDim === 'x');
      const point = axis ? points[Number(axis.value)] : undefined;
      onHoverDate(point?.date ?? null);
    });
    chart.on('hideTip', () => onHoverDate(null));
    chart.getZr().on('globalout', () => onHoverDate(null));
    chart.getZr().on('mousemove', (event: any) => {
      if (!chart.containPixel({ gridIndex: 0 }, [event.offsetX, event.offsetY])) onHoverDate(null);
    });
    chart.on('datazoom', () => {
      const option = chart.getOption() as { dataZoom?: { start: number; end: number }[] };
      const current = option.dataZoom?.[0];
      if (current) zoomRef.current = { start: current.start, end: current.end };
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => { onHoverDate(null); observer.disconnect(); chart.dispose(); };
  }, [points, signals, showZones, onHoverDate]);
  return <div ref={ref} style={{ width: '100%', height: 520 }} aria-label="板块活跃市值与价格对比走势图" />;
}

export default function SectorActivity() {
  const [items, setItems] = useState<Sector[]>([]);
  const [asOf, setAsOf] = useState('');
  const [selected, setSelected] = useState('881121.TI');
  const [detail, setDetail] = useState<Detail>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [retry, setRetry] = useState(0);
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [signalParams, setSignalParams] = useState<SignalParams>(DEFAULT_SIGNAL_PARAMS);
  const [showZones, setShowZones] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    get<{ data: Sector[]; date: string }>('/api/sector-activity', controller.signal)
      .then(r => { if (!controller.signal.aborted) { setItems(r.data); setAsOf(r.date); } })
      .catch(e => { if (!controller.signal.aborted) { setError(e.message); setItems([]); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(undefined); setDetailError(''); setDetailLoading(true);
    get<{ data: Detail }>(`/api/sector-activity/${encodeURIComponent(selected)}`, controller.signal)
      .then(r => { if (!controller.signal.aborted) setDetail(r.data); })
      .catch(e => { if (!controller.signal.aborted) setDetailError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selected, retry]);
  const current = items.find(i => i.code === selected);
  const points = useMemo(() => {
    const history = detail?.series.filter(p => p.date <= asOf) || [];
    return history;
  }, [detail, asOf]);
  const signals = useMemo(() => calculateSignals(points, signalParams), [points, signalParams]);
  const backtest = useMemo(() => runSectorBacktest(points, signals), [points, signals]);
  const displayed = (hoverDate ? points.find(point => point.date === hoverDate) : undefined) ?? current;
  const updateParam = <K extends keyof SignalParams,>(key: K, value: SignalParams[K]) => setSignalParams(previous => ({ ...previous, [key]: value }));
  const columns: ColumnsType<Sector> = [
    { title: '板块', dataIndex: 'name', width: 112, render: (name, r) => <Button type="link" className="sector-name" onClick={() => setSelected(r.code)}>{name}</Button> },
    { title: '活跃涨幅', dataIndex: 'change', width: 110, render: numberCell, defaultSortOrder: 'descend', sorter: (a, b) => (a.change ?? -Infinity) - (b.change ?? -Infinity) },
    { title: '价格涨幅', dataIndex: 'price_change', width: 115, render: numberCell, sorter: (a, b) => (a.price_change ?? -Infinity) - (b.price_change ?? -Infinity) },
  ];
  return <div className="research-page sector-page">
    {error && <Alert showIcon type="error" message={error} action={<Button onClick={() => setRetry(n => n + 1)}>重试</Button>} />}
    <div className="sector-layout">
      <section className="sector-panel sector-list">
        <div className="sector-panel-title"><strong>行业观察</strong><span>{items.length} 个行业 · 按活跃市值涨幅排序</span></div>
        <Input.Search aria-label="搜索行业" placeholder="搜索半导体、通信、银行…" allowClear value={search} onChange={e => setSearch(e.target.value)} />
        <Table<Sector> size="small" rowKey="code" columns={columns} loading={loading}
          dataSource={items.filter(i => i.name.includes(search.trim()) || i.code.includes(search.trim()))}
          pagination={{ defaultPageSize: 12, showSizeChanger: false, size: 'small' }} scroll={{ x: 337 }}
          rowClassName={r => r.code === selected ? 'sector-selected' : ''}
          onRow={r => ({ onClick: () => setSelected(r.code), style: { cursor: 'pointer' } })} />
      </section>
      <section className="sector-panel sector-detail">
        {detailError ? <Alert type="error" message={detailError} action={<Button onClick={() => setRetry(n => n + 1)}>重试</Button>} /> :
          <Spin spinning={detailLoading || loading}>
            <div className="sector-panel-title"><strong>{current?.name || detail?.name || '板块走势'}</strong>
              <Tag color="cyan">研究指标 · EMA20</Tag></div>
            <div className="sector-signal-settings">
              <div className="sector-signal-row"><strong>多空条件</strong><Tag>研究默认 · 未经收益验证</Tag>
                {signals.length > 0 && <Tag color={signals[signals.length - 1].bull ? 'red' : 'blue'}>当前：{signals[signals.length - 1].bull ? '多头' : '空头 / 观望'}</Tag>}
                <Button size="small" onClick={() => setSignalParams({ ...DEFAULT_SIGNAL_PARAMS })}>恢复默认</Button>
                <Checkbox checked={showZones} onChange={e => setShowZones(e.target.checked)}>显示多空背景</Checkbox>
              </div>
              <div className="sector-signal-row" role="group" aria-label="多头确认条件"><strong>多头确认：</strong>
                <label>单日涨幅 ≥ <InputNumber aria-label="板块单日启动涨幅" size="small" min={0.1} step={0.5} value={signalParams.startDay} onChange={v => v !== null && updateParam('startDay', v)} /> %</label>
                <span>或</span><label>两日累计 ≥ <InputNumber aria-label="板块两日启动涨幅" size="small" min={0.1} step={0.5} value={signalParams.startTwoDays} onChange={v => v !== null && updateParam('startTwoDays', v)} /> %</label>
                <span>且满足勾选项：</span>
                <Checkbox checked={signalParams.requireMA10} onChange={e => updateParam('requireMA10', e.target.checked)}>活跃市值 &gt; MA10</Checkbox>
                <Checkbox checked={signalParams.requireQuantity} onChange={e => updateParam('requireQuantity', e.target.checked)}>平滑活跃量日增幅 &gt; 0</Checkbox>
              </div>
              <div className="sector-signal-row" role="group" aria-label="退出条件"><strong>退出 / 空头：</strong>
                <label>单日跌幅 ≥ <InputNumber aria-label="板块退出跌幅" size="small" min={0.1} max={100} step={0.5} value={signalParams.exitDrop} onChange={v => v !== null && updateParam('exitDrop', v)} /> %</label>
                <span>或</span><Checkbox checked={signalParams.exitMA10} onChange={e => updateParam('exitMA10', e.target.checked)}>活跃市值连续低于 MA10</Checkbox>
                {signalParams.exitMA10 && <label><InputNumber aria-label="连续低于MA10天数" size="small" min={1} max={20} precision={0} value={signalParams.exitDays} onChange={v => v !== null && updateParam('exitDays', v)} /> 个交易日</label>}
                <BacktestPanel key={selected} result={backtest} name={current?.name || detail?.name || '板块'} />
              </div>
            </div>
            {points.length > 0 ? <Trend key={selected} points={points} signals={signals} showZones={showZones} onHoverDate={setHoverDate} /> : <div className="sector-no-data">暂无可展示的历史数据</div>}
            <div className="sector-decomposition">
              <strong>当日变化拆解 <small>{hoverDate && displayed?.date === hoverDate ? '悬停日期' : '最新日期'}：{displayed?.date || '—'} · 拆解单位：百分点</small></strong>
              <div><span>价格拉动</span><b style={{ color: color(displayed?.price_contribution) }}>{fmt(displayed?.price_contribution, '')}</b>
                <span>＋ 活跃量变化</span><b style={{ color: color(displayed?.activity_contribution) }}>{fmt(displayed?.activity_contribution, '')}</b>
                <span>＝ 活跃市值涨幅</span><b style={{ color: color(displayed?.change) }}>{fmt(displayed?.change)}</b></div>
              <div className="sector-activity-summary">
                <span>平滑活跃量变化 <b style={{ color: color(displayed?.quantity_change) }}>{fmt(displayed?.quantity_change)}</b></span>
                <span>对全市场反推AMV贡献 {fmt(displayed?.market_contribution, ' 个百分点')}</span>
                <span>行业换手率 {displayed ? displayed.turnover.toFixed(2) : '—'}%</span>
              </div>
            </div>
          </Spin>}
      </section>
    </div>
    <Collapse ghost items={[{
      key: 'formula', label: '计算公式与口径', children: <div className="sector-formula">
        <p><strong>板块活跃市值代理 A = P × EMA20(M × h ÷ P)</strong>；P 为行业收盘点位，M 为流通市值（亿元），h 为换手率小数。</p>
        <p>Q(t) = 2/21 × q(t) + 19/21 × Q(t−1)，从2024-09-10初始化，首日Q=q。每日按完整历史计算，切换显示区间不重置EMA。</p>
        <p>图中各曲线以历史首日为100，缩放不改变基准；默认显示最新数据截至的最近一年，滑块保留全部历史。悬停显示各曲线相对上一交易日的涨跌幅，后方灰字为归一化数值。近5日为当前值相对5个交易日前的变化。全市场曲线为90个行业A之和归一化。省略全市场标定系数7.695442，因为它不影响涨跌幅；板块绝对值未独立校准。</p>
        <p>价格贡献 = Q昨 × (P今−P昨) ÷ A昨；活跃量贡献 = P今 × (Q今−Q昨) ÷ A昨。两项乘100后相加等于当日活跃市值涨幅。</p>
        <p>这是原反推模型的行业分量，不是指南针官方板块指标，也不代表真实资金净流入。板块使用合成日K：收盘为当日估算值，开盘为前日收盘（首日用自身收盘），高低取开收盘极值，不代表真实盘中价格。启动、退出阈值用于研究，尚未验证收益。表格和图表均截至最新数据日期。</p>
      </div>
    }]} />
  </div>;
}
