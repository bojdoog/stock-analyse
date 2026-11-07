import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, DatePicker, Input, InputNumber, Spin, Table, Tag } from 'antd';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import KLineChart, { type KBar, type MarkZone } from '../../components/KLineChart';
import './style.less';
import BacktestPanel from './BacktestPanel';
import MarketDateChart from './MarketDateChart';
import { runSectorBacktest } from './backtest';
import { calculateMACD } from '../ActiveMarket/utils/macd';
import { calculateSignals, calculateZoneReturns, DEFAULT_SIGNAL_PARAMS, SignalParams } from './signals';

interface Point {
  date: string; amv: number; price: number; quantity: number; market: number;
  ma10: number | null; change: number | null; change5: number | null;
  price_change: number | null; quantity_change: number | null;
  price_contribution: number | null; activity_contribution: number | null;
  market_contribution: number | null; weight: number; turnover: number;
  amount: number | null; volume_ratio: number | null;
  volume: number | null; k: number | null; d: number | null; j: number | null;
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

/** 板块活跃市值日 K：用通用 KLineChart 渲染，附多头/空头区间背景与区间收益。 */
function Trend({ points, signals, showZones, onHoverDate }: { points: Point[]; signals: ReturnType<typeof calculateSignals>; showZones: boolean; onHoverDate: (date: string | null) => void }) {
  const derived = useMemo(() => {
    if (!points.length) return null;
    const base = points[0];
    // 活跃市值按首个交易日归一化为 100，阳线开=前一日收盘，高/低取开盘与收盘的极值。
    const bars: KBar[] = points.map((point, index) => {
      const close = point.amv / base.amv * 100;
      const open = (points[index - 1]?.amv ?? point.amv) / base.amv * 100;
      return { date: point.date, open, close, high: Math.max(open, close), low: Math.min(open, close), volume: point.volume };
    });
    const startMarks = new Set<number>();
    signals.forEach((signal, index) => {
      if (signal.event === 'start') {
        startMarks.add(index);
        if (signal.startBars === 2 && index > 0) startMarks.add(index - 1);
      }
    });
    const candleColors = bars.map((bar, index) => startMarks.has(index) ? '#c41e3a'
      : signals[index]?.event === 'exit' ? '#006400'
        : bar.close > bar.open ? '#FFB6C1' : '#98FB98');
    const volumeColors = points.map((point, index) => startMarks.has(index) ? '#8B0000'
      : signals[index]?.event === 'exit' ? '#006400'
        : point.price_change == null || point.price_change === 0 ? '#cbd5d9'
          : point.price_change > 0 ? '#FFB6C1' : '#98FB98');
    // 多头/空头区间背景：状态切换处收尾上一段，最后一根收尾当前段。
    const zones: MarkZone[] = [];
    let zoneStart = 0;
    signals.forEach((signal, index) => {
      if (index > 0 && signal.zoneBull !== signals[index - 1].zoneBull) {
        zones.push({ from: points[zoneStart].date, to: signal.date, bull: signals[index - 1].zoneBull });
        zoneStart = index;
      }
      if (index === signals.length - 1) zones.push({ from: points[zoneStart].date, to: signal.date, bull: signal.zoneBull });
    });
    const macd = calculateMACD(points.map(point => point.price));
    return {
      base,
      bars,
      candleColors,
      volumeColors,
      zones,
      zoneReturns: calculateZoneReturns(points, signals),
      kdj: { k: points.map(point => point.k), d: points.map(point => point.d), j: points.map(point => point.j) },
      macd: { dif: macd.map(value => value.dif), dea: macd.map(value => value.dea), macd: macd.map(value => value.histogram) },
      extraLines: [
        { label: '行业价格', color: '#d5a057', axis: 'right' as const, data: points.map(point => point.price / base.price * 100) },
        { label: '全市场反推AMV', color: '#9ba7b8', axis: 'right' as const, dashed: true, data: points.map(point => point.market / base.market * 100) },
        { label: '活跃市值MA10', color: '#87b4a8', data: points.map(point => point.ma10 == null ? null : point.ma10 / base.amv * 100) },
      ],
    };
  }, [points, signals]);

  // 悬浮框由组件展示各条线的涨跌幅，这里只追加当前多空区间收益与信号原因。
  const tooltipExtra = useCallback((index: number) => {
    const signal = signals[index];
    const zone = derived?.zoneReturns[index];
    if (!signal || !zone) return '';
    return `<div style="border-top:1px solid #eee;margin-top:6px;padding-top:4px">` +
      `<div style="color:#999">本${signal.zoneBull ? '多头' : '空头'}区间：${zone.start} ～ ${zone.end}${zone.open ? '（未结束）' : ''}</div>` +
      `<div>区间总收益率${zone.open ? '（截至最新日）' : ''} <strong style="color:${color(zone.total)}">${fmt(zone.total)}</strong></div>` +
      `<div>区间实时收益率 <strong style="color:${color(zone.realtime)}">${fmt(zone.realtime)}</strong></div>` +
      (signal.event ? `<div style="color:#999">${signal.event === 'start' ? '启动' : '退出'}：${signal.reason}</div>` : '') +
      `</div>`;
  }, [derived, signals]);

  return <div style={{ display: 'flex', width: '100%', height: 935 }}>
    {derived && <KLineChart
      bars={derived.bars}
      overlays={[]}
      legend
      candleLabel="板块活跃市值"
      defaultHidden={['全市场反推AMV']}
      subCharts={['volume', 'kdj', 'macd']}
      subHeights={{ volume: 70, kdj: 108, macd: 108 }}
      tooltipMode="lines"
      extraLines={derived.extraLines}
      zones={showZones ? derived.zones : []}
      candleColors={derived.candleColors}
      volumeColors={derived.volumeColors}
      colors={{ up: '#FFB6C1', down: '#98FB98', flat: '#cbd5d9' }}
      kdj={derived.kdj}
      macd={derived.macd}
      tooltipExtra={tooltipExtra}
      onHoverDate={onHoverDate}
      ariaLabel="板块活跃市值、行业价格、成交量、KDJ与MACD走势图"
    />}
  </div>;
}

type HoverHandler = (date: string | null) => void;

/** 悬停日期的拆解只在这里更新，避免整页（表格/回测）随鼠标重渲染。 */
function Decomposition({ points, current, hoverRef }: {
  points: Point[];
  current?: Sector;
  hoverRef: React.MutableRefObject<HoverHandler | null>;
}) {
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  useEffect(() => {
    hoverRef.current = setHoverDate;
    return () => { hoverRef.current = null; };
  }, [hoverRef]);
  const displayed = (hoverDate ? points.find(point => point.date === hoverDate) : undefined) ?? current;
  return <div className="sector-decomposition">
    <strong>当日变化拆解 <small>{hoverDate && displayed?.date === hoverDate ? '悬停日期' : '所选日期'}：{displayed?.date || '—'} · 拆解单位：百分点</small></strong>
    <div><span>价格拉动</span><b style={{ color: color(displayed?.price_contribution) }}>{fmt(displayed?.price_contribution, '')}</b>
      <span>＋ 活跃量变化</span><b style={{ color: color(displayed?.activity_contribution) }}>{fmt(displayed?.activity_contribution, '')}</b>
      <span>＝ 活跃市值涨幅</span><b style={{ color: color(displayed?.change) }}>{fmt(displayed?.change)}</b></div>
    <div className="sector-activity-summary">
      <span>平滑活跃量变化 <b style={{ color: color(displayed?.quantity_change) }}>{fmt(displayed?.quantity_change)}</b></span>
      <span>对全市场反推AMV贡献 {fmt(displayed?.market_contribution, ' 个百分点')}</span>
      <span>行业换手率 {displayed ? displayed.turnover.toFixed(2) : '—'}%</span>
    </div>
  </div>;
}

export default function SectorActivity() {
  const [items, setItems] = useState<Sector[]>([]);
  const [asOf, setAsOf] = useState('');
  const [requestedDate, setRequestedDate] = useState('');
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const dateSet = useMemo(() => new Set(availableDates), [availableDates]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Detail>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [retry, setRetry] = useState(0);
  // 悬停日期不再存进页面 state，交给 Decomposition 内部消化，避免整页重渲染。
  const hoverRef = React.useRef<HoverHandler | null>(null);
  const handleHoverDate = useCallback<HoverHandler>((date) => { hoverRef.current?.(date); }, []);
  const [signalParams, setSignalParams] = useState<SignalParams>(DEFAULT_SIGNAL_PARAMS);
  const [showZones, setShowZones] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    get<{ data: Sector[]; date: string; dates: string[] }>(`/api/sector-activity${requestedDate ? `?date=${encodeURIComponent(requestedDate)}` : ''}`, controller.signal)
      .then(r => {
        if (!controller.signal.aborted) {
          const ranked = [...r.data].sort((a, b) => (b.change ?? -Infinity) - (a.change ?? -Infinity));
          setItems(ranked);
          setAsOf(r.date);
          setAvailableDates(r.dates);
          setSelected(previous => ranked.some(item => item.code === previous) ? previous : ranked[0]?.code ?? '');
        }
      })
      .catch(e => { if (!controller.signal.aborted) { setError(e.message); setItems([]); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry, requestedDate]);
  useEffect(() => {
    if (!selected) { setDetailLoading(false); return; }
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
  const updateParam = <K extends keyof SignalParams,>(key: K, value: SignalParams[K]) => setSignalParams(previous => ({ ...previous, [key]: value }));
  const columns: ColumnsType<Sector> = useMemo(() => [
    { title: '板块', dataIndex: 'name', width: 112, render: (name, r) => <Button type="link" className="sector-name" onClick={() => setSelected(r.code)}>{name}</Button> },
    { title: '活跃涨幅', dataIndex: 'change', width: 110, render: numberCell, defaultSortOrder: 'descend', sorter: (a, b) => (a.change ?? -Infinity) - (b.change ?? -Infinity) },
    { title: '价格涨幅', dataIndex: 'price_change', width: 115, render: numberCell, sorter: (a, b) => (a.price_change ?? -Infinity) - (b.price_change ?? -Infinity) },
    { title: <span title="同花顺行业成交量（手）×100×均价，换算为亿元">成交额（亿）</span>, dataIndex: 'amount', width: 90, align: 'right', render: (n: number | null) => n == null ? '—' : (n / 1e8).toFixed(2), sorter: (a, b) => (a.amount ?? -Infinity) - (b.amount ?? -Infinity) },
    { title: <span title="当日行业成交量 ÷ 此前20个交易日平均成交量，不含当天">板块放量比</span>, dataIndex: 'volume_ratio', width: 90, align: 'right', render: (n: number | null) => n == null ? '—' : `${n.toFixed(2)}倍`, sorter: (a, b) => (a.volume_ratio ?? -Infinity) - (b.volume_ratio ?? -Infinity) },
  ], []);
  return <div className="research-page sector-page">
    {error && <Alert showIcon type="error" message={error} action={<Button onClick={() => setRetry(n => n + 1)}>重试</Button>} />}
    <div className="sector-layout">
      <section className="sector-panel sector-list sector-left-column">
        <div className="sector-panel-title"><strong>行业观察</strong><span>同花顺 {items.length} 个行业 · {asOf}</span></div>
        <MarketDateChart availableDates={availableDates} onSelect={setRequestedDate} />
        <div className="sector-filters">
          <Input.Search aria-label="搜索行业" placeholder="搜索半导体、通信、银行…" allowClear value={search} onChange={e => setSearch(e.target.value)} />
          <DatePicker aria-label="行业观察日期" placeholder="选择交易日" format="YYYY-MM-DD"
            value={requestedDate || asOf ? dayjs(requestedDate || asOf) : null}
            disabled={!availableDates.length} disabledDate={date => !dateSet.has(date.format('YYYY-MM-DD'))}
            onChange={date => setRequestedDate(date ? date.format('YYYY-MM-DD') : '')} />
          <Button onClick={() => setRequestedDate('')} disabled={!requestedDate}>最新</Button>
        </div>
        <Table<Sector> key={asOf} size="small" rowKey="code" columns={columns} loading={loading}
          dataSource={items.filter(i => i.name.includes(search.trim()) || i.code.includes(search.trim()))}
          pagination={{ defaultPageSize: 8, showSizeChanger: false, size: 'small' }} scroll={{ x: 517 }}
          rowClassName={r => r.code === selected ? 'sector-selected' : ''}
          onRow={r => ({ onClick: () => setSelected(r.code), style: { cursor: 'pointer' } })} />
      </section>
      <section className="sector-panel sector-detail">
        {detailError ? <Alert type="error" message={detailError} action={<Button onClick={() => setRetry(n => n + 1)}>重试</Button>} /> :
          <Spin spinning={detailLoading || loading}>
            <div className="sector-panel-title"><strong>{current?.name || detail?.name || '板块走势'}</strong>
              <Tag color="cyan">研究指标 · EMA20</Tag></div>
            <Collapse defaultActiveKey={[]} items={[{
              key: 'signal-settings', label: '多空条件与回测',
              children: <div className="sector-signal-settings" style={{ marginTop: 0 }}>
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
              </div>,
            }]} />
            {points.length > 0 ? <Trend key={`${selected}-${asOf}`} points={points} signals={signals} showZones={showZones} onHoverDate={handleHoverDate} /> : <div className="sector-no-data">暂无可展示的历史数据</div>}
            <Decomposition points={points} current={current} hoverRef={hoverRef} />
          </Spin>}
      </section>
    </div>
    <Collapse ghost items={[{
      key: 'formula', label: '计算公式与口径', children: <div className="sector-formula">
        <p><strong>板块活跃市值代理 A = P × EMA20(M × h ÷ P)</strong>；P 为行业收盘点位，M 为流通市值（亿元），h 为换手率小数。</p>
        <p>Q(t) = 2/21 × q(t) + 19/21 × Q(t−1)，从2024-09-10初始化，首日Q=q。每日按完整历史计算，切换显示区间不重置EMA。</p>
        <p>图中各曲线以历史首日为100，缩放不改变基准；默认显示最新数据截至的最近一年，滑块保留全部历史。悬停显示各曲线相对上一交易日的涨跌幅，后方灰字为归一化数值。近5日为当前值相对5个交易日前的变化。全市场曲线为90个行业A之和归一化。省略全市场标定系数7.695442，因为它不影响涨跌幅；板块绝对值未独立校准。</p>
        <p>价格贡献 = Q昨 × (P今−P昨) ÷ A昨；活跃量贡献 = P今 × (Q今−Q昨) ÷ A昨。两项乘100后相加等于当日活跃市值涨幅。</p>
        <p>行业观察使用同花顺行业日线。成交额 = 成交量（手）×100×均价，以亿元展示；板块放量比 = 当日成交量 ÷ 此前20个交易日平均成交量（不含当天）。缺失数据、历史不足20日或均量为零时显示“—”。</p>
        <p>成交量副图使用行业真实成交量，单位万手，按行业收盘较前日涨跌着色。KDJ使用行业真实最高、最低和收盘价，参数（9、3、3）：RSV=(收盘−9日最低)/(9日最高−9日最低)×100，K=2/3×前K+1/3×RSV，D=2/3×前D+1/3×K，J=3K−2D。K、D初值50，满9日开始显示，区间高低相等时RSV取50；缺失行情后重新初始化。缩放不重算指标。</p>
        <p>这是原反推模型的行业分量，不是指南针官方板块指标，也不代表真实资金净流入。板块使用合成日K：收盘为当日估算值，开盘为前日收盘（首日用自身收盘），高低取开收盘极值，不代表真实盘中价格。启动、退出阈值用于研究，尚未验证收益。表格和图表均截至最新数据日期。</p>
      </div>
    }]} />
  </div>;
}
