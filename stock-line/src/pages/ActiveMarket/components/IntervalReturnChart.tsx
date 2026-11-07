import React, { useEffect, useMemo, useRef } from 'react';
import { init, ECharts } from 'echarts';
import { BacktestTrade } from '../utils/backtest';

/** 区间收益分档：左闭右开，密集区用 2% 一档，尾部合并；正好 0% 单独一档 */
const BUCKETS: { label: string; tip: string; min: number; max: number; exact?: boolean }[] = [
  { label: '< -8', tip: '< -8%', min: -Infinity, max: -8 },
  { label: '-8~-6', tip: '-8% ~ -6%', min: -8, max: -6 },
  { label: '-6~-4', tip: '-6% ~ -4%', min: -6, max: -4 },
  { label: '-4~-2', tip: '-4% ~ -2%', min: -4, max: -2 },
  { label: '-2~0', tip: '-2% ~ 0%（不含 0）', min: -2, max: 0 },
  { label: '0', tip: '正好 0%', min: 0, max: 0, exact: true },
  { label: '0~2', tip: '0% ~ 2%（不含 0）', min: 0, max: 2 },
  { label: '2~4', tip: '2% ~ 4%', min: 2, max: 4 },
  { label: '4~6', tip: '4% ~ 6%', min: 4, max: 6 },
  { label: '6~8', tip: '6% ~ 8%', min: 6, max: 8 },
  { label: '8~10', tip: '8% ~ 10%', min: 8, max: 10 },
  { label: '10~12', tip: '10% ~ 12%', min: 10, max: 12 },
  { label: '12~14', tip: '12% ~ 14%', min: 12, max: 14 },
  { label: '14~16', tip: '14% ~ 16%', min: 14, max: 16 },
  { label: '16~18', tip: '16% ~ 18%', min: 16, max: 18 },
  { label: '18~20', tip: '18% ~ 20%', min: 18, max: 20 },
  { label: '20~30', tip: '20% ~ 30%', min: 20, max: 30 },
  { label: '≥ 30', tip: '≥ 30%', min: 30, max: Infinity },
];

interface IntervalReturnChartProps {
  trades: BacktestTrade[];
  height?: number;
}

/** 多空区间收益分布直方图：x 轴为收益分档，y 轴为区间数量 */
const IntervalReturnChart: React.FC<IntervalReturnChartProps> = ({ trades, height = 220 }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);

  const counts = useMemo(() => {
    const bull = BUCKETS.map(() => 0);
    const finished = trades.filter(t => t.type === 'bull' && !t.is_open && Number.isFinite(t.return));
    finished.forEach(t => {
      const pct = t.return * 100;
      // 正好 0% 归到单独的 "0" 档，其余按左闭右开区间归组
      const index = pct === 0
        ? BUCKETS.findIndex(b => b.exact)
        : BUCKETS.findIndex(b => !b.exact && pct >= b.min && pct < b.max);
      if (index >= 0) bull[index] += 1;
    });
    return { bull, total: finished.length };
  }, [trades]);

  useEffect(() => {
    if (!chartRef.current) return;
    if (chartInstance.current) chartInstance.current.dispose();
    chartInstance.current = init(chartRef.current);

    // 0% 分界线穿过单独的 "0" 档（分类轴以档位中心为整数坐标）
    const zeroBoundaryCoord = BUCKETS.findIndex(b => b.exact);

    chartInstance.current.setOption({
      backgroundColor: '#fff',
      animation: false,
      grid: { left: 56, right: 24, top: 28, bottom: 40 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line' },
        formatter: (raw: any) => {
          const item = Array.isArray(raw) ? raw[0] : raw;
          const index = item?.dataIndex ?? 0;
          const share = counts.total > 0 ? ((item.value / counts.total) * 100).toFixed(0) : '0';
          return `<div style="font-size:13px"><div>${BUCKETS[index].tip}</div>
            <div>多头区间：<b>${item.value}</b> 个（占 ${share}%）</div></div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: BUCKETS.map(b => b.label),
        name: '区间收益（%）',
        nameLocation: 'middle',
        nameGap: 26,
        nameTextStyle: { color: '#999', fontSize: 11 },
        axisLabel: { color: '#666', fontSize: 10, interval: 0, margin: 8 },
        axisLine: { lineStyle: { color: '#ccc' } },
        axisTick: { alignWithLabel: true },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        name: '区间数量',
        nameTextStyle: { color: '#999', fontSize: 11, padding: [0, 0, 4, 0] },
        minInterval: 1,
        axisLabel: { color: '#666', fontSize: 10 },
        splitLine: { lineStyle: { color: '#eee' } },
        axisLine: { lineStyle: { color: '#ccc' } },
      },
      series: [
        {
          name: '多头区间',
          type: 'line',
          data: counts.bull,
          smooth: false,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { color: '#c41e3a', width: 2 },
          itemStyle: { color: '#c41e3a' },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(196,30,58,0.22)' },
                { offset: 1, color: 'rgba(196,30,58,0.02)' },
              ],
            },
          },
          label: { show: true, position: 'top', color: '#c41e3a', fontSize: 10, formatter: (p: any) => (p.value > 0 ? p.value : '') },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ xAxis: zeroBoundaryCoord }],
            lineStyle: { color: '#8a8a8a', width: 1, type: 'dashed' },
            label: { show: true, formatter: '0', position: 'end', color: '#8a8a8a', fontSize: 10 },
          },
        },
      ],
    });

    const handleResize = () => chartInstance.current?.resize();
    const ro = new ResizeObserver(handleResize);
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, [counts]);

  return (
    <div style={{ marginTop: 16, border: '1px solid #eee', borderRadius: 8, padding: '12px 16px 4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>多头区间收益分布</span>
        <span style={{ fontSize: 12, color: '#999' }}>共 {counts.total} 个已结束多头区间</span>
      </div>
      <div ref={chartRef} style={{ width: '100%', height }} />
      <div style={{ fontSize: 11, color: '#aaa', lineHeight: 1.6, paddingBottom: 6 }}>
        x 轴为多头区间收益分档（2% 一档、左闭右开，正好 0% 单独一档，两端合并），y 轴为落在该档的区间数量；区间收益为 ETF 组合收益，未结束的区间不计入。
      </div>
    </div>
  );
};

export default IntervalReturnChart;
