import { Alert, Empty, Spin } from 'antd';
import * as echarts from 'echarts';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import EtfIntradayModal from './IntradayModal';
import './style.less';

interface HuijinEtf {
  code: string;
  name: string;
  date: string;
  close: number;
  volume: number | null;
  change_pct: number | null;
}

interface Bar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

const UP = '#c45e65';
const DOWN = '#238672';
const FLAT = '#7a898f';

const changeColor = (value: number | null | undefined) =>
  value == null || value === 0 ? FLAT : value > 0 ? UP : DOWN;

const formatVolume = (value: number | null | undefined) => {
  if (value == null) return '--';
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿手`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)} 万手`;
  return `${value.toFixed(0)} 手`;
};

const formatPercent = (value: number | null | undefined) =>
  value == null ? '--' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  return response.json();
}

const buildOption = (bars: Bar[]) => {
  const dates = bars.map((bar) => bar.date);
  const candle = bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]);
  const volumes = bars.map((bar, index) => ({
    value: bar.volume ?? 0,
    itemStyle: { color: (bar.close >= bar.open ? UP : DOWN) + '99' },
  }));
  const start = Math.max(0, Math.round(100 - 25000 / bars.length));

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', label: { backgroundColor: '#546e7a' } },
      formatter: (params: any[]) => {
        const index = params[0]?.dataIndex ?? 0;
        const bar = bars[index];
        if (!bar) return '';
        const prev = bars[index - 1];
        const pct = prev ? (bar.close / prev.close - 1) * 100 : null;
        const color = changeColor(pct);
        return [
          `<b>${bar.date}</b>`,
          `开 ${bar.open.toFixed(3)}　收 <span style="color:${color}">${bar.close.toFixed(3)}</span>`,
          `高 ${bar.high.toFixed(3)}　低 ${bar.low.toFixed(3)}`,
          `涨跌 <span style="color:${color}">${formatPercent(pct)}</span>`,
          `成交量 ${formatVolume(bar.volume)}`,
        ].join('<br/>');
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 58, right: 26, top: 28, height: '58%' },
      { left: 58, right: 26, top: '74%', height: '15%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#dfe6e7' } },
        axisLabel: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#dfe6e7' } },
        axisLabel: { color: '#7a898f', fontSize: 10, hideOverlap: true },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        splitNumber: 5,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#7a898f', fontSize: 10 },
        splitLine: { lineStyle: { color: '#eef2f3' } },
      },
      {
        gridIndex: 1,
        scale: true,
        splitNumber: 2,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start, end: 100 },
    ],
    series: [
      {
        name: '日K',
        type: 'candlestick',
        data: candle,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN, borderWidth: 1 },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        barWidth: '60%',
      },
    ],
  } as echarts.EChartsOption;
};

const HuijinHoldings: React.FC = () => {
  const [etfs, setEtfs] = useState<HuijinEtf[]>([]);
  const [asOf, setAsOf] = useState('');
  const [selected, setSelected] = useState('');
  const [bars, setBars] = useState<Bar[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingBars, setLoadingBars] = useState(false);
  const [error, setError] = useState('');
  const [intradayDate, setIntradayDate] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchJson<{ data: HuijinEtf[]; date: string }>('/api/huijin-etfs')
      .then((result) => {
        const rows = [...(result.data || [])].sort((a, b) => (b.volume ?? 0) - (a.volume ?? 0));
        setEtfs(rows);
        setAsOf(result.date || rows[0]?.date || '');
        if (rows.length) setSelected(rows[0].code);
      })
      .catch(() => setError('国家队持仓数据加载失败，请确认后端已启动并拉取过汇金系宽基数据。'))
      .finally(() => setLoadingList(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoadingBars(true);
    setError('');
    fetchJson<{ data: Bar[] }>(`/api/kline/etf_hj/${encodeURIComponent(selected)}`)
      .then((result) => setBars(result.data || []))
      .catch(() => {
        setBars([]);
        setError('该 ETF 的日 K 数据加载失败。');
      })
      .finally(() => setLoadingBars(false));
  }, [selected]);

  useEffect(() => {
    if (!chartRef.current || !bars.length) return;
    const chart = echarts.init(chartRef.current);
    chart.setOption(buildOption(bars));
    // 双击日 K 弹出分时弹窗；蜡烛最窄约 2px，按画布坐标吸附到最近的交易日。
    const node = chartRef.current;
    const onDblClick = (event: MouseEvent) => {
      // 只传 x 像素：传 [x, y] 时 Axis.toLocalCoord 会得到 NaN。
      const index = Math.round(Number(chart.convertFromPixel({ xAxisIndex: 0 }, event.offsetX)));
      const bar = bars[index];
      if (bar) setIntradayDate(bar.date);
    };
    node.addEventListener('dblclick', onDblClick);
    const onResize = () => chart.resize();
    window.addEventListener('resize', onResize);
    return () => {
      node.removeEventListener('dblclick', onDblClick);
      window.removeEventListener('resize', onResize);
      chart.dispose();
    };
  }, [bars]);

  const current = useMemo(() => etfs.find((item) => item.code === selected), [etfs, selected]);

  return (
    <div className="research-page hj-page">
      <section className="hj-panel hj-list-panel">
        <div className="hj-panel-title">
          <strong>汇金系宽基</strong>
          <span>{etfs.length} 只 · 按成交量排序 · {asOf || '--'}</span>
        </div>
        <Spin spinning={loadingList}>
          {etfs.length ? (
            <div className="hj-list">
              {etfs.map((item, index) => (
                <button
                  key={item.code}
                  type="button"
                  className={`hj-row${item.code === selected ? ' hj-row-active' : ''}`}
                  onClick={() => setSelected(item.code)}
                >
                  <span className="hj-rank">{index + 1}</span>
                  <span className="hj-name">
                    <b>{item.name}</b>
                    <small>{item.code}</small>
                  </span>
                  <span className="hj-price">
                    <b style={{ color: changeColor(item.change_pct) }}>{item.close?.toFixed(3)}</b>
                    <small style={{ color: changeColor(item.change_pct) }}>{formatPercent(item.change_pct)}</small>
                  </span>
                  <span className="hj-volume">{formatVolume(item.volume)}</span>
                </button>
              ))}
            </div>
          ) : (
            <Empty className="hj-empty" description="暂无数据" />
          )}
        </Spin>
      </section>

      <section className="hj-panel hj-chart-panel">
        <div className="hj-panel-title">
          <strong>{current?.name || '日 K'}</strong>
          <span>{current ? `${current.code} · 前复权 · 截至 ${current.date}` : '选择左侧 ETF 查看日 K'}</span>
        </div>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
        <Spin spinning={loadingBars}>
          <div ref={chartRef} className="hj-chart" role="img" aria-label="ETF 日K走势图" />
        </Spin>
      </section>
      {selected && (
        <EtfIntradayModal code={selected} date={intradayDate}
          onDateChange={setIntradayDate} onClose={() => setIntradayDate(null)} />
      )}
    </div>
  );
};

export default HuijinHoldings;
