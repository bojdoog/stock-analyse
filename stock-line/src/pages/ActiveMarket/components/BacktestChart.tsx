import React, { useEffect, useRef, useState } from 'react';
import { init, ECharts } from 'echarts';
import { BacktestResult, BacktestTrade, KLineData, RankingMethod } from '../utils/backtest';

interface BacktestChartProps {
  result: BacktestResult;
  year: number;
  amvData?: KLineData[];
  rankingMethod?: RankingMethod;
}

const ACTIVE_BULL_BG = 'rgba(255, 182, 193, 0.6)';
const ACTIVE_BEAR_BG = 'rgba(144, 238, 144, 0.6)';
const BULL_BG = 'rgba(255, 182, 193, 0.25)';
const BEAR_BG = 'rgba(144, 238, 144, 0.25)';
const ACTIVE_CARD_BG = '#fff0f3';
const CARD_BG = '#fff';

const BacktestChart: React.FC<BacktestChartProps> = ({ result, year, amvData = [], rankingMethod = 'etf_gain' }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  // 计算当日活跃市值涨跌幅
  const amvChangeMap = React.useMemo(() => {
    const map = new Map<string, number>();
    for (let i = 0; i < amvData.length; i++) {
      if (i === 0) {
        map.set(amvData[i].date, 0);
        continue;
      }
      const prev = amvData[i - 1].close;
      const cur = amvData[i].close;
      map.set(amvData[i].date, prev !== 0 ? (cur - prev) / prev : 0);
    }
    return map;
  }, [amvData]);

  const yearTrades = result.trades
    .filter(t => t.year === year)
    .sort((a, b) => a.start_date.localeCompare(b.start_date));

  const bullTrades = yearTrades.filter(t => t.type === 'bull');

  // 年份范围：起点为自然年1月1日，终点为归属该年的最后一个区间的结束日
  const yearStart = `${year}-01-01`;
  const yearTradesList = result.trades.filter(t => t.year === year);
  const yearEnd = yearTradesList.length > 0
    ? yearTradesList.sort((a, b) => a.end_date.localeCompare(b.end_date))[yearTradesList.length - 1].end_date
    : `${year}-12-31`;

  // 净值序列截取到该年份范围
  const yearNavData = result.navSeries.filter(p => p.date >= yearStart && p.date <= yearEnd);

  const yearZones = result.zones.filter(z => {
    return (z.start_date >= yearStart && z.start_date <= yearEnd) ||
      (z.end_date >= yearStart && z.end_date <= yearEnd) ||
      (z.start_date <= yearStart && z.end_date >= yearEnd);
  });

  const zoneKey = (z: { start_date: string; end_date: string }) => `${z.start_date}_${z.end_date}`;

  const dates = yearNavData.map(p => p.date);

  const buildOption = (highlightKey: string | null) => {
    const navValues = yearNavData.map(p => p.nav);

    const sortedZones = [...yearZones].sort((a, b) => a.start_date.localeCompare(b.start_date));
    const markAreaData: any[] = [];
    sortedZones.forEach((zone, zIdx) => {
      const isBull = zone.type === 'bull';
      const key = zoneKey(zone);
      const isActive = key === highlightKey;
      const trade = result.trades.find(
        t => t.start_date === zone.start_date && t.end_date === zone.end_date
      );

      let startXAxis = zone.start_date;
      if (zIdx > 0 && sortedZones[zIdx - 1].end_date !== zone.start_date) {
        startXAxis = sortedZones[zIdx - 1].end_date;
      }

      markAreaData.push([
        {
          name: isBull ? '多头' : '空头',
          xAxis: startXAxis,
          data: { start_date: zone.start_date, end_date: zone.end_date },
          itemStyle: {
            color: isActive ? (isBull ? ACTIVE_BULL_BG : ACTIVE_BEAR_BG) : (isBull ? BULL_BG : BEAR_BG),
          },
          label: {
            show: !isBull && trade,
            position: 'insideTop',
            fontSize: 11,
            color: trade && trade.return >= 0 ? '#c41e3a' : '#006400',
            formatter: () => {
              if (trade) {
                const ret = (trade.return * 100).toFixed(2);
                return `银行 ${trade.return >= 0 ? '+' : ''}${ret}%`;
              }
              return '';
            },
          },
        },
        {
          xAxis: zone.end_date,
        },
      ]);
    });

    return {
      backgroundColor: '#fff',
      animation: false,
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params;
          const date = p.axisValue;
          const nav = p.value;
          const yearStartNav = yearNavData[0]?.nav ?? 1;
          const yearReturn = (nav - yearStartNav) / yearStartNav;
          const returnPct = (yearReturn * 100).toFixed(2);
          const color = yearReturn >= 0 ? '#c41e3a' : '#006400';

          const amvChange = amvChangeMap.get(date) ?? 0;
          const amvChangePct = (amvChange * 100).toFixed(2);
          const amvChangeColor = amvChange >= 0 ? '#c41e3a' : '#006400';

          const zone = yearZones.find(z => date >= z.start_date && date <= z.end_date);
          let zoneInfo = '';
          let zoneReturnLine = '';
          if (zone) {
            const trade = result.trades.find(
              t => t.start_date === zone.start_date && t.end_date === zone.end_date
            );
            const zoneStartNav = result.navSeries.find(p => p.date === zone.start_date)?.nav;
            if (zoneStartNav !== undefined && zoneStartNav !== 0) {
              const zoneReturn = (nav - zoneStartNav) / zoneStartNav;
              const zoneReturnPct = (zoneReturn * 100).toFixed(2);
              const zoneReturnColor = zoneReturn >= 0 ? '#c41e3a' : '#006400';
              const zoneLabel = zone.type === 'bull' ? '多头区间收益' : '空头区间收益';
              zoneReturnLine = `<div>${zoneLabel}：<span style="color:${zoneReturnColor}">${zoneReturn >= 0 ? '+' : ''}${zoneReturnPct}%</span></div>`;
            }
            if (trade) {
              const typeLabel = zone.type === 'bull' ? '多头区间' : '空头区间';
              const typeColor = zone.type === 'bull' ? '#c41e3a' : '#006400';
              const ret = (trade.return * 100).toFixed(2);
              const retColor = trade.return >= 0 ? '#c41e3a' : '#006400';
              const amvRet = (trade.amv_return * 100).toFixed(2);
              const amvColor = trade.amv_return >= 0 ? '#c41e3a' : '#006400';
              zoneInfo = `<br/><span style="color:${typeColor};font-weight:bold">${typeLabel}</span> ${zone.start_date} ~ ${zone.end_date}`;
              zoneInfo += `<br/>策略收益：<span style="color:${retColor}">${trade.return >= 0 ? '+' : ''}${ret}%</span>`;
              zoneInfo += `<br/>活跃市值：<span style="color:${amvColor}">${trade.amv_return >= 0 ? '+' : ''}${amvRet}%</span>`;
            }
          }

          return `<div style="font-size:13px">
            <div>${date}</div>
            <div>净值：<span style="color:${color};font-weight:bold">${nav.toFixed(4)}</span></div>
            ${zoneReturnLine}
            <div>当年总收益：<span style="color:${color}">${yearReturn >= 0 ? '+' : ''}${returnPct}%</span></div>
            <div>活跃市值：<span style="color:${amvChangeColor}">${amvChange >= 0 ? '+' : ''}${amvChangePct}%</span></div>
            ${zoneInfo}
          </div>`;
        },
      },
      grid: {
        left: 60,
        right: 30,
        top: 30,
        bottom: 40,
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: {
          color: '#666',
          fontSize: 11,
          formatter: (val: string) => val.slice(5),
        },
        axisLine: { lineStyle: { color: '#ccc' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          color: '#666',
          formatter: (val: number) => val.toFixed(2),
        },
        splitLine: { lineStyle: { color: '#eee' } },
        axisLine: { lineStyle: { color: '#ccc' } },
      },
      dataZoom: [
        {
          type: 'inside',
          start: 0,
          end: 100,
        },
      ],
      series: [
        {
          name: '策略净值',
          type: 'line',
          data: navValues,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            color: '#333',
            width: 1.5,
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(51,51,51,0.15)' },
                { offset: 1, color: 'rgba(51,51,51,0.01)' },
              ],
            },
          },
          markArea: {
            silent: false,
            data: markAreaData,
            label: {
              show: true,
              position: 'insideTop',
              fontSize: 11,
            },
          },
        },
      ],
    };
  };

  useEffect(() => {
    if (!chartRef.current || yearNavData.length === 0) return;

    if (chartInstance.current) {
      chartInstance.current.dispose();
    }

    chartInstance.current = init(chartRef.current);

    chartInstance.current.setOption(buildOption(activeKey));

    // 点击图表区域高亮对应区间
    chartInstance.current.getZr().on('click', (event: any) => {
      const point = [event.offsetX, event.offsetY];
      const xIndex = chartInstance.current?.convertFromPixel({ seriesIndex: 0 }, point)?.[0];
      if (typeof xIndex === 'number' && xIndex >= 0 && xIndex < dates.length) {
        const date = dates[xIndex];
        const zone = yearZones.find(z => date >= z.start_date && date <= z.end_date);
        if (zone) {
          const key = zoneKey(zone);
          setActiveKey(prev => (prev === key ? null : key));
        }
      }
    });

    const handleResize = () => {
      chartInstance.current?.resize();
    };
    const ro = new ResizeObserver(handleResize);
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, year, yearNavData, yearZones]);

  useEffect(() => {
    chartInstance.current?.setOption(buildOption(activeKey));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey]);

  return (
    <div>
      <div ref={chartRef} style={{ width: '100%', height: 350, marginBottom: 12 }} />
      {bullTrades.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 10 }}>
          {bullTrades.map((t, idx) => {
            const key = `${t.start_date}_${t.end_date}`;
            const isActive = activeKey === key;
            const sortedReturns = [...t.holdings]
              .map(h => h.holding_return)
              .sort((a, b) => b - a);
            const top1Return = sortedReturns[0];
            const top2Return = sortedReturns[1];
            return (
              <div
                key={idx}
                onClick={() => setActiveKey(prev => (prev === key ? null : key))}
                style={{
                  border: isActive ? '2px solid #c41e3a' : '1px solid #eee',
                  borderRadius: 4,
                  padding: '8px 14px',
                  backgroundColor: isActive ? ACTIVE_CARD_BG : CARD_BG,
                  fontSize: 13,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 6, borderBottom: '1px solid #eee' }}>
                  <span style={{ fontWeight: 'bold', color: '#333' }}>
                    <span style={{ color: '#c41e3a', letterSpacing: 4, fontSize: 14 }}>多</span>
                    <span>头区间 {t.start_date.slice(5)} ~ {t.end_date.slice(5)}</span>
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, marginBottom: 8, marginTop: 8 }}>
                  {t.holdings.map((h, hIdx) => {
                    const isTop1 = h.holding_return === top1Return;
                    const isTop2 = h.holding_return === top2Return;
                    return (
                      <span
                        key={hIdx}
                        style={{
                          color: '#555',
                          fontWeight: isTop1 || isTop2 ? 700 : 'normal',
                          backgroundColor: isTop1
                            ? 'rgba(255, 182, 193, 0.25)'
                            : isTop2
                              ? 'rgba(255, 182, 193, 0.12)'
                              : 'transparent',
                          borderRadius: 2,
                          padding: '1px 4px',
                          marginLeft: -4,
                        }}
                      >
                        {(() => {
                          const useMoneyflow = !!(h.industry_name);
                          const isThsConcept = useMoneyflow && rankingMethod === 'ths_concept';
                          const isThsMoneyflow = useMoneyflow && rankingMethod === 'ths_moneyflow';
                          const isDcMoneyflow = useMoneyflow && rankingMethod === 'dc_moneyflow';
                          return (
                            <>
                              {useMoneyflow
                                ? h.industry_name
                                : h.name.replace('ETF', '')}
                              <span style={{ color: '#999' }}> {(h.weight * 100).toFixed(0)}%</span>
                              {h.day_change !== undefined && (
                                <>
                                  <span style={{ color: '#999', marginLeft: 8 }}>
                                    {isThsMoneyflow
                                      ? '同花顺板块流入'
                                      : isThsConcept
                                        ? '同花顺概念流入'
                                        : isDcMoneyflow
                                          ? '东财板块流入'
                                          : '启动涨幅'}
                                  </span>
                                  <span style={{ color: h.day_change >= 0 ? '#c41e3a' : '#006400' }}>
                                    {useMoneyflow
                                      ? (h.day_change >= 0 ? '+' : '') + h.day_change.toFixed(2) + '亿'
                                      : (h.day_change >= 0 ? '+' : '') + h.day_change.toFixed(2) + '%'}
                                  </span>
                                  {useMoneyflow && (
                                    <span style={{ color: '#666', marginLeft: 8 }}>{h.name.replace('ETF', '')}</span>
                                  )}
                                </>
                              )}
                            </>
                          );
                        })()}
                        <span style={{ color: '#999', marginLeft: 8 }}>区间收益</span>
                        <span style={{ color: h.holding_return >= 0 ? '#c41e3a' : '#006400' }}>
                          {(h.holding_return >= 0 ? '+' : '') + (h.holding_return * 100).toFixed(2)}%
                        </span>
                      </span>
                    );
                  })}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto', paddingTop: 8, borderTop: '1px solid #eee' }}>
                  <span style={{ color: '#666', fontWeight: 500 }}>
                    活跃市值：
                    <span style={{ color: t.amv_return >= 0 ? '#c41e3a' : '#006400' }}>
                      {t.amv_return >= 0 ? '+' : ''}{(t.amv_return * 100).toFixed(2)}%
                    </span>
                  </span>
                  <span style={{ color: '#666', fontWeight: 500 }}>
                    总收益：
                    <span style={{ color: t.return >= 0 ? '#c41e3a' : '#006400', fontWeight: 500 }}>
                      {t.return >= 0 ? '+' : ''}{(t.return * 100).toFixed(2)}%
                    </span>
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default BacktestChart;
