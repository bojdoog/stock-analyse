import React, { useEffect, useRef } from 'react';
import { init, ECharts } from 'echarts';
import { BacktestNavPoint } from '../utils/backtest';

interface NavOverviewChartProps {
  navSeries: BacktestNavPoint[];
  height?: number;
}

/** 总时间范围内的策略净值曲线（弹窗顶部总览） */
const NavOverviewChart: React.FC<NavOverviewChartProps> = ({ navSeries, height = 180 }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || navSeries.length === 0) return;

    if (chartInstance.current) {
      chartInstance.current.dispose();
    }
    chartInstance.current = init(chartRef.current);

    const dates = navSeries.map(p => p.date);
    const navs = navSeries.map(p => p.nav);
    const startNav = navs[0] ?? 1;

    chartInstance.current.setOption({
      backgroundColor: '#fff',
      animation: false,
      grid: { left: 55, right: 20, top: 24, bottom: 24 },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params;
          const nav = p.value as number;
          const ret = ((nav - startNav) / startNav) * 100;
          const color = ret >= 0 ? '#c41e3a' : '#006400';
          return `<div style="font-size:13px">
            <div>${p.axisValue}</div>
            <div>净值：${nav.toFixed(4)}</div>
            <div>累计收益：<span style="color:${color};font-weight:bold">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</span></div>
          </div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: '#666', fontSize: 10 },
        axisLine: { lineStyle: { color: '#ccc' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#666', fontSize: 10, formatter: (val: number) => val.toFixed(1) },
        splitLine: { lineStyle: { color: '#eee' } },
        axisLine: { lineStyle: { color: '#ccc' } },
      },
      series: [
        {
          name: '策略净值',
          type: 'line',
          data: navs,
          symbol: 'none',
          lineStyle: { color: '#c41e3a', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(196,30,58,0.28)' },
                { offset: 1, color: 'rgba(196,30,58,0.02)' },
              ],
            },
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
  }, [navSeries]);

  return <div ref={chartRef} style={{ width: '100%', height }} />;
};

export default NavOverviewChart;
