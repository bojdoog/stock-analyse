import * as echarts from 'echarts';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import './style.less';

/** 单根日 K。 */
export interface KBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  amount?: number | null;
}

/** 主图可叠加的指标。 */
export type OverlayKind = 'zx_short' | 'zx_long' | 'ma5' | 'ma10' | 'ma20' | 'ma60';
/** 可配置的副图，按传入顺序自上而下排列。 */
export type SubChartKind = 'volume' | 'kdj' | 'macd';

/** 覆盖在 K 线上的多头/空头区间背景。 */
export interface MarkZone { from: string; to: string; bull: boolean }
/** 主图上的额外折线（可走左轴或右轴）。 */
export interface ExtraLine {
  label: string;
  color: string;
  data: (number | null)[];
  axis?: 'left' | 'right';
  dashed?: boolean;
  width?: number;
}

interface Props {
  bars: KBar[];
  /** 主图上标记的竖虚线日期（如选股日）。 */
  markDate?: string;
  /** 悬浮框里该日期的标记文案。 */
  markLabel?: string;
  /** 主图叠加指标，默认两条知行线。 */
  overlays?: OverlayKind[];
  /** 副图列表，默认成交量 + KDJ + MACD。 */
  subCharts?: SubChartKind[];
  /** 主图区间背景（多头/空头）。 */
  zones?: MarkZone[];
  /** 额外折线；有 axis='right' 时自动启用右侧坐标轴。 */
  extraLines?: ExtraLine[];
  /** 覆盖 K 线颜色（信号日等特殊着色）。 */
  candleColors?: (string | null | undefined)[];
  /** 覆盖成交量柱颜色。 */
  volumeColors?: (string | null | undefined)[];
  /** 涨跌配色，默认红涨绿跌。 */
  colors?: { up?: string; down?: string; flat?: string };
  /** KDJ 序列覆盖（数据源已有 KDJ 时避免重算）。 */
  kdj?: { k: (number | null)[]; d: (number | null)[]; j: (number | null)[] };
  /** MACD 序列覆盖。 */
  macd?: { dif: (number | null)[]; dea: (number | null)[]; macd: (number | null)[] };
  /** 初始展示的 K 线根数，默认 250（约一年交易日）。 */
  initialBars?: number;
  /** 各副图高度（像素），默认成交量 46、KDJ/MACD 64；不同页面可按需覆盖。 */
  subHeights?: Partial<Record<SubChartKind, number>>;
  /** 悬浮框在基础行情之后追加的自定义 HTML。 */
  tooltipExtra?: (index: number) => string;
  /** 主图 K 线的图例名称（如「板块活跃市值」），默认「日K」。 */
  candleLabel?: string;
  /** 是否在图表上方显示可点击的图例（点击切换各线/副图显示）。 */
  legend?: boolean;
  /** 初始隐藏的图例项（按图例名称匹配，如「全市场反推AMV」）。 */
  defaultHidden?: string[];
  /** 悬浮框内容：默认 ohlc（开收高低+涨跌），lines 只显示各条线的涨跌幅。 */
  tooltipMode?: 'ohlc' | 'lines';
  /** 悬停日期变化（已按 rAF 合并、按日期去重）。 */
  onHoverDate?: (date: string | null) => void;
  className?: string;
  ariaLabel?: string;
}

const UP = '#c45e65';
const DOWN = '#238672';
const FLAT = '#7a898f';
const B1_MARK = '#8e44ad';

/** 面板纵向布局（像素）：顶部读出行留白、主图、副图、底部日期轴。 */
const LAYOUT = { top: 36, bottom: 24, gap: 12, mainMin: 140 };
/** 副图默认高度的下限（像素）；容器变高时再按下表比例增长，避免大屏上副图显得过矮。 */
const SUB_HEIGHT: Record<SubChartKind, number> = { volume: 46, kdj: 64, macd: 64 };
const SUB_RATIO: Record<SubChartKind, number> = { volume: 0.08, kdj: 0.11, macd: 0.11 };
const SUB_LABEL: Record<SubChartKind, string> = { volume: '成交量', kdj: 'KDJ(9,3,3)', macd: 'MACD(12,26,9)' };

const OVERLAY_META: Record<OverlayKind, { label: string; color: string; width: number }> = {
  zx_short: { label: '知行短期趋势线', color: '#f08c00', width: 1.5 },
  zx_long: { label: '知行多空线', color: '#3b6ea5', width: 1.5 },
  ma5: { label: 'MA5', color: '#d9a441', width: 1 },
  ma10: { label: 'MA10', color: '#6b9e63', width: 1 },
  ma20: { label: 'MA20', color: '#8e44ad', width: 1 },
  ma60: { label: 'MA60', color: '#657780', width: 1 },
};

const DEFAULT_OVERLAYS: OverlayKind[] = ['zx_short', 'zx_long'];
const DEFAULT_SUBS: SubChartKind[] = ['volume', 'kdj'];
/** 图例里可切换的全部副图，按固定顺序展示。 */
const ALL_SUBS: SubChartKind[] = ['volume', 'kdj', 'macd'];

const changeColor = (value: number | null | undefined, palette = { up: UP, down: DOWN, flat: FLAT }) =>
  value == null || value === 0 ? palette.flat : value > 0 ? palette.up : palette.down;

const formatPercent = (value: number | null | undefined, palette = { up: UP, down: DOWN, flat: FLAT }) =>
  value == null ? '--' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;

const formatVolume = (value: number | null | undefined) => {
  if (value == null) return '--';
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿手`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)} 万手`;
  return `${value.toFixed(0)} 手`;
};

const fmtNum = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value) ? '--' : value.toFixed(2);

/** 通达信 EMA(X,N)：等价于 pandas ewm(span=N, adjust=False)。 */
const ema = (values: number[], span: number) => {
  const k = 2 / (span + 1);
  let previous = values[0];
  return values.map((value, index) => (index === 0 ? value : (previous = previous + k * (value - previous))));
};

/** MA(C,N)，不足 N 根返回 null。 */
const ma = (values: number[], window: number) => {
  let sum = 0;
  return values.map((value, index) => {
    sum += value;
    if (index >= window) sum -= values[index - window];
    return index >= window - 1 ? sum / window : null;
  });
};

/** 知行短期趋势线 EMA(EMA(C,10),10) 与知行多空线 (MA14+MA28+MA57+MA114)/4。 */
const zxLines = (closes: number[]) => {
  const short = ema(ema(closes, 10), 10);
  const ma14 = ma(closes, 14);
  const ma28 = ma(closes, 28);
  const ma57 = ma(closes, 57);
  const ma114 = ma(closes, 114);
  const longLine = closes.map((_, index) => {
    const parts = [ma14[index], ma28[index], ma57[index], ma114[index]];
    if (parts.some((value) => value == null)) return null;
    return (parts as number[]).reduce((a, b) => a + b, 0) / 4;
  });
  return { short, longLine };
};

/** 通达信 KDJ(9,3,3)：K/D 初值 50。 */
const kdjLines = (highs: number[], lows: number[], closes: number[]) => {
  let k = 50;
  let d = 50;
  const kLines: number[] = [];
  const dLines: number[] = [];
  const jLines: number[] = [];
  closes.forEach((close, index) => {
    const start = Math.max(0, index - 8);
    const lowN = Math.min(...lows.slice(start, index + 1));
    const highN = Math.max(...highs.slice(start, index + 1));
    const rsv = ((close - lowN) / (highN - lowN + 1e-9)) * 100;
    if (index === 0) {
      k = 50;
      d = 50;
    } else {
      k = (2 / 3) * k + (1 / 3) * rsv;
      d = (2 / 3) * d + (1 / 3) * k;
    }
    kLines.push(k);
    dLines.push(d);
    jLines.push(3 * k - 2 * d);
  });
  return { k: kLines, d: dLines, j: jLines };
};

/** MACD(12,26,9)：DIF、DEA 与柱状值 2×(DIF-DEA)。 */
const macdLines = (closes: number[]) => {
  const fast = ema(closes, 12);
  const slow = ema(closes, 26);
  const dif = fast.map((value, index) => value - slow[index]);
  const dea = ema(dif, 9);
  return { dif, dea, macd: dif.map((value, index) => (value - dea[index]) * 2) };
};

/** 一次性算出绘图与读数共用的指标序列。 */
const computeIndicators = (bars: KBar[]) => {
  const closes = bars.map((bar) => bar.close);
  const highs = bars.map((bar) => bar.high);
  const lows = bars.map((bar) => bar.low);
  const { short, longLine } = zxLines(closes);
  const { k, d, j } = kdjLines(highs, lows, closes);
  const { dif, dea, macd } = macdLines(closes);
  return { closes, short, longLine, k, d, j, dif, dea, macd };
};

interface PanelLayout {
  kind: SubChartKind;
  top: number;
  height: number;
}

const makeLayout = (
  height: number,
  subCharts: SubChartKind[],
  subHeights: Partial<Record<SubChartKind, number>> = {},
) => {
  // 显式传入的像素值按原样使用；未传入时按容器高度比例自适应（不低于默认下限）。
  const resolved = (kind: SubChartKind) =>
    subHeights[kind] ?? Math.round(Math.max(SUB_HEIGHT[kind], height * SUB_RATIO[kind]));
  const subTotal = subCharts.reduce((sum, kind) => sum + resolved(kind), 0) + LAYOUT.gap * subCharts.length;
  const mainHeight = Math.max(LAYOUT.mainMin, height - LAYOUT.top - LAYOUT.bottom - subTotal);
  let cursor = LAYOUT.top + mainHeight + LAYOUT.gap;
  const panels: PanelLayout[] = subCharts.map((kind) => {
    const panel = { kind, top: cursor, height: resolved(kind) };
    cursor += resolved(kind) + LAYOUT.gap;
    return panel;
  });
  return { main: { top: LAYOUT.top, height: mainHeight }, panels };
};

const overlayData = (kind: OverlayKind, indicators: ReturnType<typeof computeIndicators>) =>
  kind === 'zx_short'
    ? indicators.short
    : kind === 'zx_long'
      ? indicators.longLine
      : ma(indicators.closes, Number(kind.slice(2)));

const buildOption = (
  bars: KBar[],
  indicators: ReturnType<typeof computeIndicators>,
  options: {
    markDate?: string;
    markLabel: string;
    overlays: OverlayKind[];
    subCharts: SubChartKind[];
    layout: ReturnType<typeof makeLayout>;
    zones: MarkZone[];
    extraLines: ExtraLine[];
    candleColors?: (string | null | undefined)[];
    volumeColors?: (string | null | undefined)[];
    palette: { up: string; down: string; flat: string };
    kdj?: Props['kdj'];
    macd?: Props['macd'];
    initialBars: number;
    tooltipExtra?: (index: number) => string;
    candleLabel: string;
    showCandle: boolean;
    tooltipMode: 'ohlc' | 'lines';
  },
): echarts.EChartsOption => {
  const {
    markDate, markLabel, overlays, subCharts, layout, zones, extraLines,
    candleColors, volumeColors, palette, initialBars, tooltipExtra,
    candleLabel, showCandle, tooltipMode,
  } = options;
  const dates = bars.map((bar) => bar.date);
  const kdj = options.kdj ?? { k: indicators.k, d: indicators.d, j: indicators.j };
  const macdSeries = options.macd ?? { dif: indicators.dif, dea: indicators.dea, macd: indicators.macd };
  const candle = bars.map((bar, index) => {
    const value = [bar.open, bar.close, bar.low, bar.high];
    const custom = candleColors?.[index];
    return custom
      ? { value, itemStyle: { color: custom, color0: custom, borderColor: custom, borderColor0: custom } }
      : value;
  });
  const volumes = bars.map((bar, index) => ({
    value: bar.volume ?? 0,
    itemStyle: { color: volumeColors?.[index] ?? (bar.close >= bar.open ? palette.up : palette.down) + '99' },
  }));
  // 初始窗口取最后 initialBars 根（默认约一年交易日）。
  const start = Math.max(0, Math.round(100 - (100 * initialBars) / bars.length));
  const rightAxis = extraLines.some((line) => line.axis === 'right');
  const gridCount = 1 + layout.panels.length;
  const panelAxisBase = 1 + (rightAxis ? 1 : 0);
  const grids = [
    { left: 58, right: 26, top: layout.main.top, height: layout.main.height },
    ...layout.panels.map((panel) => ({ left: 58, right: 26, top: panel.top, height: panel.height })),
  ];
  const last = grids.length - 1;
  const axesIndex = Array.from({ length: gridCount }, (_, index) => index);

  // 只在选股当天画一根紫色虚线。
  const markMarks = markDate && dates.includes(markDate)
    ? [{
      xAxis: markDate,
      lineStyle: { color: B1_MARK, type: 'dashed', width: 1, opacity: 0.85 },
      label: { show: false, position: 'insideEndTop', formatter: 'B1', color: B1_MARK, fontSize: 10, distance: 2 },
    }]
    : [];
  const zoneAreas = zones.map((zone) => ([
    { xAxis: zone.from, itemStyle: { color: zone.bull ? '#fff3bf66' : '#e2f0fa66' } },
    { xAxis: zone.to },
  ]));

  const series: any[] = [
    {
      name: candleLabel,
      type: 'candlestick',
      // 隐藏 K 线时只清空数据，保留区间背景与标记线。
      data: showCandle ? candle : [],
      itemStyle: { color: palette.up, color0: palette.down, borderColor: palette.up, borderColor0: palette.down, borderWidth: 1 },
      markLine: markMarks.length
        ? { silent: true, symbol: ['none', 'none'], animation: false, data: markMarks }
        : undefined,
      markArea: zoneAreas.length ? { silent: true, data: zoneAreas } : undefined,
    },
    ...overlays.map((kind, index) => ({
      name: OVERLAY_META[kind].label,
      type: 'line',
      data: overlayData(kind, indicators),
      showSymbol: false,
      lineStyle: { width: OVERLAY_META[kind].width, color: OVERLAY_META[kind].color },
      itemStyle: { color: OVERLAY_META[kind].color },
      connectNulls: false,
      z: 3 + index,
    })),
    ...extraLines.map((line, index) => ({
      name: line.label,
      type: 'line',
      data: line.data,
      showSymbol: false,
      yAxisIndex: line.axis === 'right' && rightAxis ? 1 : 0,
      lineStyle: { width: line.width ?? 1.5, color: line.color, type: line.dashed ? 'dashed' : 'solid' },
      itemStyle: { color: line.color },
      connectNulls: false,
      z: 3 + index,
    })),
  ];

  layout.panels.forEach((panel, offset) => {
    const axis = panelAxisBase + offset;
    const gridIndex = offset + 1;
    if (panel.kind === 'volume') {
      series.push({
        name: '成交量', type: 'bar', xAxisIndex: gridIndex, yAxisIndex: axis,
        data: volumes, barWidth: '60%',
      });
      return;
    }
    if (panel.kind === 'kdj') {
      series.push(
        {
          name: 'K', type: 'line', xAxisIndex: gridIndex, yAxisIndex: axis, data: kdj.k, showSymbol: false,
          lineStyle: { width: 1, color: '#d9a441' }, itemStyle: { color: '#d9a441' }, z: 3,
          // KDJ 的 0 轴单独画深一点，便于区分零轴与其它刻度线。
          markLine: {
            silent: true, symbol: ['none', 'none'], animation: false,
            lineStyle: { color: '#9fb0b7', width: 1 },
            data: [{ yAxis: 0 }],
          },
        },
        { name: 'D', type: 'line', xAxisIndex: gridIndex, yAxisIndex: axis, data: kdj.d, showSymbol: false, lineStyle: { width: 1, color: '#3b6ea5' }, itemStyle: { color: '#3b6ea5' }, z: 4 },
        { name: 'J', type: 'line', xAxisIndex: gridIndex, yAxisIndex: axis, data: kdj.j, showSymbol: false, lineStyle: { width: 1, color: B1_MARK }, itemStyle: { color: B1_MARK }, z: 5 },
      );
      return;
    }
    series.push(
      {
        name: 'MACD', type: 'bar', xAxisIndex: gridIndex, yAxisIndex: axis, barWidth: '60%',
        data: macdSeries.macd.map((value) => ({ value, itemStyle: { color: (value == null || value >= 0 ? palette.up : palette.down) + '99' } })),
      },
      { name: 'DIF', type: 'line', xAxisIndex: gridIndex, yAxisIndex: axis, data: macdSeries.dif, showSymbol: false, lineStyle: { width: 1, color: '#f08c00' }, itemStyle: { color: '#f08c00' }, z: 3 },
      { name: 'DEA', type: 'line', xAxisIndex: gridIndex, yAxisIndex: axis, data: macdSeries.dea, showSymbol: false, lineStyle: { width: 1, color: '#3b6ea5' }, itemStyle: { color: '#3b6ea5' }, z: 4 },
    );
  });

  return {
    animation: false,
    // 悬浮框只保留主图信息，副图数值由各面板顶部的读数行展示。
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'cross', label: { backgroundColor: '#546e7a' } },
      position: (point: number[], _params: unknown, _dom: unknown, _rect: unknown,
        size: { viewSize: number[]; contentSize: number[] }) => {
        const left = Math.min(Math.max(point[0] - size.contentSize[0] / 2, 8),
          size.viewSize[0] - size.contentSize[0] - 8);
        return [left, layout.main.top + 2];
      },
      formatter: (params: any[]) => {
        const index = params[0]?.dataIndex ?? 0;
        const bar = bars[index];
        if (!bar) return '';
        const prev = bars[index - 1];
        const pct = prev ? (bar.close / prev.close - 1) * 100 : null;
        // 悬浮框文字固定用深色涨跌色，避免浅色蜡烛配色在白底上看不清。
        const tone = changeColor(pct);
        const mark = bar.date === markDate ? `<span style="color:${B1_MARK}"><b>${markLabel}</b></span>` : '';
        if (tooltipMode === 'lines') {
          // 只展示各条线的涨跌幅，不展示开收高低与原始点位。
          const pctOf = (values: (number | null)[], cursor: number) => {
            const current = values[cursor];
            const previous = values[cursor - 1];
            if (current == null || previous == null || previous === 0) return null;
            return (current / previous - 1) * 100;
          };
          const rows = [
            showCandle ? `${candleLabel} <span style="color:${tone}">${formatPercent(pct)}</span>` : '',
            ...overlays.map((kind) => {
              const change = pctOf(overlayData(kind, indicators), index);
              return `${OVERLAY_META[kind].label} <span style="color:${changeColor(change)}">${formatPercent(change)}</span>`;
            }),
            ...extraLines.map((line) => {
              const change = pctOf(line.data, index);
              return `${line.label} <span style="color:${changeColor(change)}">${formatPercent(change)}</span>`;
            }),
          ];
          return [`<b>${bar.date}</b>`, ...rows, mark, tooltipExtra?.(index) ?? ''].filter(Boolean).join('<br/>');
        }
        return [
          `<b>${bar.date}</b>`,
          `开 ${fmtNum(bar.open)}　收 <span style="color:${tone}">${fmtNum(bar.close)}</span>`,
          `高 ${fmtNum(bar.high)}　低 ${fmtNum(bar.low)}`,
          `涨跌 <span style="color:${tone}">${formatPercent(pct)}</span>`,
          mark,
          tooltipExtra?.(index) ?? '',
        ].filter(Boolean).join('<br/>');
      },
    },
    axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }], label: { backgroundColor: '#546e7a' } },
    grid: grids,
    xAxis: grids.map((_, index) => ({
      type: 'category',
      gridIndex: index,
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#dfe6e7' } },
      axisLabel: index === last
        ? { color: '#7a898f', fontSize: 10, hideOverlap: true }
        : { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      // 悬停时只在最底部面板显示日期，其余面板不重复显示。
      axisPointer: { label: { show: index === last } },
    })),
    yAxis: [
      {
        scale: true, splitNumber: 5, axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#7a898f', fontSize: 10 },
        splitLine: { lineStyle: { color: '#eef2f3' } },
      },
      ...(rightAxis ? [{
        gridIndex: 0, position: 'right', scale: true, splitNumber: 5,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#9aa8ad', fontSize: 10 }, splitLine: { show: false },
      }] : []),
      ...layout.panels.map((panel, offset) => (panel.kind === 'volume'
        ? {
          gridIndex: offset + 1, scale: true, splitNumber: 2, axisLine: { show: false },
          axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false },
        }
        : {
          gridIndex: offset + 1, scale: true, splitNumber: 2, axisLine: { show: false },
          axisTick: { show: false }, axisLabel: { color: '#9aa8ad', fontSize: 9 },
          splitLine: { lineStyle: { color: '#f2f5f6' } },
        })),
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: axesIndex, start, end: 100 }],
    series,
  } as echarts.EChartsOption;
};

const KLineChart: React.FC<Props> = ({
  bars,
  markDate,
  markLabel = 'B1 选股日',
  overlays = DEFAULT_OVERLAYS,
  subCharts = DEFAULT_SUBS,
  zones = [],
  extraLines = [],
  candleColors,
  volumeColors,
  colors,
  kdj,
  macd,
  initialBars = 250,
  subHeights,
  tooltipExtra,
  candleLabel = '日K',
  legend = false,
  defaultHidden = [],
  tooltipMode = 'ohlc',
  onHoverDate,
  className,
  ariaLabel = '日K走势图',
}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const barsRef = useRef(bars);
  barsRef.current = bars;
  const hoverRef = useRef<Props['onHoverDate']>(onHoverDate);
  hoverRef.current = onHoverDate;
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const palette = { up: colors?.up ?? UP, down: colors?.down ?? DOWN, flat: colors?.flat ?? FLAT };

  // 初始化只做一次：事件绑定、尺寸监听、销毁。
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = echarts.init(host);
    chartRef.current = chart;
    // 悬停日期只在真正换了一根 K 线时才通知外部，并用 rAF 合并高频 mousemove。
    const hovered = { date: null as string | null };
    let frame = 0;
    let pending: string | null = null;
    const notify = (date: string | null) => {
      pending = date;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (hovered.date === pending) return;
        hovered.date = pending;
        hoverRef.current?.(pending);
      });
    };
    chart.on('updateAxisPointer', (event: any) => {
      const info = event?.axesInfo?.[0];
      if (!info) return;
      const current = barsRef.current;
      const index = typeof info.value === 'number'
        ? info.value
        : current.findIndex((bar) => bar.date === info.value);
      if (index >= 0 && index < current.length) {
        setHoverIndex(index);
        notify(current[index].date);
      }
    });
    chart.on('globalout', () => {
      setHoverIndex(null);
      notify(null);
    });
    const measure = () => {
      const rect = host.getBoundingClientRect();
      setSize({ width: Math.round(rect.width), height: Math.round(rect.height) });
    };
    measure();
    // 容器高度随控制台展开/收起、窗口变化而变，画布始终铺满。
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    const first = requestAnimationFrame(measure);
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(frame);
      notify(null);
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    setHoverIndex(null);
  }, [bars]);

  // 图例：点击切换 K 线、叠加指标、额外折线与成交量副图的显示；键名即图例名称。
  const [hidden, setHidden] = useState<Set<string>>(() => {
    // subCharts 只决定初始展示的副图；开启图例时其余副图以关闭态出现，可随时打开。
    const initial = new Set(defaultHidden);
    if (legend) {
      ALL_SUBS.forEach((kind) => {
        if (!subCharts.includes(kind)) initial.add(SUB_LABEL[kind]);
      });
    }
    return initial;
  });
  const toggle = React.useCallback((key: string) => {
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);
  const activeOverlays = overlays.filter((kind) => !hidden.has(OVERLAY_META[kind].label));
  const activeExtraLines = extraLines.filter((line) => !hidden.has(line.label));
  // 开启图例时列出全部副图，关闭的以灰态展示，可点击开启。
  const activeSubCharts = (legend ? ALL_SUBS : subCharts).filter((kind) => !hidden.has(SUB_LABEL[kind]));
  const showCandle = !hidden.has(candleLabel);
  const legendItems = legend
    ? [
      { key: candleLabel, label: candleLabel, color: palette.up },
      ...overlays.map((kind) => ({ key: OVERLAY_META[kind].label, label: OVERLAY_META[kind].label, color: OVERLAY_META[kind].color })),
      ...extraLines.map((line) => ({ key: line.label, label: line.label, color: line.color })),
      ...ALL_SUBS.map((kind) => ({ key: SUB_LABEL[kind], label: SUB_LABEL[kind], color: kind === 'kdj' ? '#d9a441' : kind === 'macd' ? '#f08c00' : '#9fb3bd' })),
    ]
    : [];
  const hiddenKey = Array.from(hidden).sort().join(',');
  const layout = makeLayout(size.height, activeSubCharts, subHeights);
  const heightKey = activeSubCharts.map((kind) => `${kind}:${subHeights?.[kind] ?? '-'}`).join(',');
  const overlayKey = activeOverlays.join(',');
  const subKey = activeSubCharts.join(',');
  const extraKey = activeExtraLines.map((line) => `${line.label}:${line.axis ?? 'left'}`).join(',');
  const zoneKey = zones.map((zone) => `${zone.from}-${zone.to}-${zone.bull}`).join(',');

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || size.width === 0 || size.height === 0) return;
    if (!bars.length) {
      chart.clear();
      return;
    }
    chart.resize({ width: size.width, height: size.height });
    chart.setOption(buildOption(bars, computeIndicators(bars), {
      markDate, markLabel, overlays: activeOverlays, subCharts: activeSubCharts, layout,
      zones, extraLines: activeExtraLines,
      candleColors, volumeColors, palette, kdj, macd, initialBars, tooltipExtra,
      candleLabel, showCandle, tooltipMode,
    }), true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, markDate, markLabel, overlayKey, subKey, extraKey, zoneKey, hiddenKey, heightKey,
    candleColors, volumeColors, colors?.up, colors?.down, colors?.flat, kdj, macd,
    candleLabel, tooltipMode, initialBars, size.width, size.height]);

  const indicators = useMemo(() => (bars.length ? computeIndicators(bars) : null), [bars]);
  const kdjSeries = kdj ?? (indicators ? { k: indicators.k, d: indicators.d, j: indicators.j } : null);
  const macdSeries = macd ?? (indicators ? { dif: indicators.dif, dea: indicators.dea, macd: indicators.macd } : null);
  const active = !bars.length || !indicators
    ? null
    : Math.min(Math.max(hoverIndex ?? bars.length - 1, 0), bars.length - 1);
  const bar = active == null ? null : bars[active];

  return (
    <div className="kline-chart-root">
      {legendItems.length > 0 && (
        <div className="kline-legend" role="group" aria-label="指标显示控制">
          {legendItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`kline-legend-item${hidden.has(item.key) ? ' is-off' : ''}`}
              aria-pressed={!hidden.has(item.key)}
              onClick={() => toggle(item.key)}
            >
              <i className="kline-legend-swatch" style={{ background: item.color }} />
              {item.label}
            </button>
          ))}
        </div>
      )}
      <div className={`kline-chart-wrap${className ? ` ${className}` : ''}`}>
        <div ref={hostRef} className="kline-chart" role="img" aria-label={ariaLabel} />
        {size.height > 0 && bar && indicators && active != null && kdjSeries && macdSeries && (
          <div className="kline-readout-layer">
            {(activeOverlays.length > 0 || activeExtraLines.length > 0) && (
              <div className="kline-readout kline-readout-main">
                {activeOverlays.map((kind) => (
                  <span key={kind}>
                    <i className="kline-readout-swatch" style={{ background: OVERLAY_META[kind].color }} />
                    {OVERLAY_META[kind].label} <b>{fmtNum(overlayData(kind, indicators)[active])}</b>
                  </span>
                ))}
                {activeExtraLines.map((line) => (
                  <span key={line.label}>
                    <i className="kline-readout-swatch" style={{ background: line.color }} />
                    {line.label} <b>{fmtNum(line.data[active])}</b>
                  </span>
                ))}
              </div>
            )}
            {layout.panels.map((panel) => (
              <div key={panel.kind} className="kline-readout" style={{ top: panel.top + 2 }}>
                <span className="kline-readout-name">{SUB_LABEL[panel.kind]}</span>
                {panel.kind === 'volume' && (
                  <span>量 <b>{formatVolume(bar.volume)}</b></span>
                )}
                {panel.kind === 'kdj' && (
                  <>
                    <span style={{ color: '#d9a441' }}>K:<b>{fmtNum(kdjSeries.k[active])}</b></span>
                    <span style={{ color: '#3b6ea5' }}>D:<b>{fmtNum(kdjSeries.d[active])}</b></span>
                    <span style={{ color: B1_MARK }}>J:<b>{fmtNum(kdjSeries.j[active])}</b></span>
                  </>
                )}
                {panel.kind === 'macd' && (
                  <>
                    <span style={{ color: '#f08c00' }}>DIF:<b>{fmtNum(macdSeries.dif[active])}</b></span>
                    <span style={{ color: '#3b6ea5' }}>DEA:<b>{fmtNum(macdSeries.dea[active])}</b></span>
                    <span style={{ color: changeColor(macdSeries.macd[active], palette) }}>MACD:<b>{fmtNum(macdSeries.macd[active])}</b></span>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default KLineChart;
