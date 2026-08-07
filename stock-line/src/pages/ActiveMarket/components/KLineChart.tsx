import React, { useEffect, useRef } from 'react';
import { init, connect, ECharts } from 'echarts';

interface KLineData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

interface ExtraSeries {
  name: string;
  id: string;
  data: KLineData[];
}

interface ZoneRange {
  start: number;
  end: number;
}

interface ChartZones {
  bull: ZoneRange[];
  bear: ZoneRange[];
}

interface KLineChartProps {
  data: KLineData[];
  highlightThreshold?: number;
  showBullZoneBg?: boolean;
  showBearZoneBg?: boolean;
  extraSeries?: ExtraSeries[];
  allETFSeries?: ExtraSeries[];
  syncGroup?: string;
  dataLabel?: string;
  mainSeriesName?: string;
  showVolume?: boolean;
  showRanking?: boolean;
  showZones?: boolean;
  chartHeight?: number | string;
  maxDate?: string;
  showDataZoom?: boolean;
  baseDates?: string[];
  zones?: ChartZones;
  onZonesChange?: (zones: ChartZones) => void;
  seriesType?: 'candlestick' | 'line';
}

const ETF_COLORS = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7', '#dda0dd', '#f0e68c', '#87ceeb', '#ffa07a', '#98d8c8', '#c9b1ff', '#f7dc6f', '#a3e4d7', '#f5b7b1', '#aed6f1', '#d5f5e3', '#fadbd8'];

const EMPTY_ITEM: KLineData = {
  date: '',
  open: NaN,
  high: NaN,
  low: NaN,
  close: NaN,
  volume: 0,
  amount: 0
};

const alignDataToDates = (source: KLineData[], dates: string[]): KLineData[] => {
  const map = new Map(source.map(d => [d.date, d]));
  return dates.map(date => map.get(date) || { ...EMPTY_ITEM, date });
};

const KLineChart: React.FC<KLineChartProps> = ({
  data,
  highlightThreshold = 4,
  showBullZoneBg = false,
  showBearZoneBg = false,
  extraSeries = [],
  allETFSeries = [],
  syncGroup,
  dataLabel = '活跃市值',
  mainSeriesName = '日K',
  showVolume = true,
  showRanking = true,
  showZones = true,
  chartHeight = 900,
  maxDate,
  showDataZoom = true,
  baseDates,
  zones: externalZones,
  onZonesChange,
  seriesType = 'candlestick'
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);
  const zoomRange = useRef<{ start: number; end: number } | null>(null);

  const calculateMA = (dayCount: number, data: KLineData[]) => {
    const result: (number | string)[] = [];
    for (let i = 0; i < data.length; i++) {
      if (i < dayCount - 1) {
        result.push('-');
        continue;
      }
      let sum = 0;
      let validCount = 0;
      for (let j = 0; j < dayCount; j++) {
        const close = data[i - j].close;
        if (!isNaN(close)) {
          sum += close;
          validCount++;
        }
      }
      if (validCount === 0 || validCount < dayCount) {
        result.push('-');
      } else {
        result.push(parseFloat((sum / dayCount).toFixed(2)));
      }
    }
    return result;
  };

  useEffect(() => {
    if (!chartRef.current || data.length === 0) {
      console.log('Chart not ready:', { hasRef: !!chartRef.current, dataLength: data.length });
      return;
    }

    if (chartInstance.current) {
      chartInstance.current.dispose();
    }

    chartInstance.current = init(chartRef.current);

    // 按 baseDates / maxDate 对齐并截断主数据和叠加序列，确保上方副图与主图 x 轴一致
    const alignedBaseDates = baseDates
      ? (maxDate ? baseDates.filter(d => d <= maxDate) : baseDates)
      : null;

    const filteredData = alignedBaseDates
      ? alignDataToDates(data, alignedBaseDates)
      : (maxDate ? data.filter(item => item.date <= maxDate) : data);
    const filteredExtraSeries = alignedBaseDates
      ? extraSeries.map(s => ({ ...s, data: alignDataToDates(s.data, alignedBaseDates) }))
      : (maxDate
        ? extraSeries.map(s => ({ ...s, data: s.data.filter(d => d.date <= maxDate) }))
        : extraSeries);

    const dates = filteredData.map(item => item.date);

    // 如果有保存的 zoom 范围，应用它；否则使用默认初始范围
    const initialStart = zoomRange.current?.start ?? 90;
    const initialEnd = zoomRange.current?.end ?? 100;

    const ma10 = calculateMA(10, filteredData);

    const specialMarks: { index: number; type: 'bull' | 'bear' }[] = [];
    let bullZones: { start: number; end: number }[] = [];
    let bearZones: { start: number; end: number }[] = [];
    let bullZoneRankings: { zone: { start: number; end: number }; startItems: string[]; zoneItems: string[] }[] = [];

    if (showZones) {
      if (externalZones) {
        // 使用外部传入的主图区间（活跃市值），让副图区间与主图完全一致
        bullZones = externalZones.bull;
        bearZones = externalZones.bear;
        bullZones.forEach(zone => {
          specialMarks.push({ index: zone.start, type: 'bull' });
        });
        bearZones.forEach(zone => {
          specialMarks.push({ index: zone.end, type: 'bear' });
        });
      } else {
        let isBullZone = false;
        let lastBullMarkIndex = -1;
        let currentBullStart = -1;

        for (let i = 0; i < filteredData.length; i++) {
          const item = filteredData[i];

          let change = 0;
          if (i > 0) {
            const prevItem = filteredData[i - 1];
            change = (item.close - prevItem.close) / prevItem.close * 100;
          }

          let bullStart = false;
          let twoDayBull = false;

          if (change > 4) {
            bullStart = true;
          } else if (change > 0 && i > 0) {
            const prevItem = filteredData[i - 1];
            const prevPrevItem = filteredData[i - 2];
            if (prevPrevItem) {
              const prevChange = (prevItem.close - prevPrevItem.close) / prevPrevItem.close * 100;
              if (prevChange > 0 && change + prevChange > 4) {
                bullStart = true;
                twoDayBull = true;
              }
            }
          }

          if (bullStart && !isBullZone) {
            if (twoDayBull && i - 1 > lastBullMarkIndex) {
              specialMarks.push({ index: i - 1, type: 'bull' });
            }
            specialMarks.push({ index: i, type: 'bull' });
            lastBullMarkIndex = i;
            isBullZone = true;
            currentBullStart = i;
            continue;
          }

          if (isBullZone) {
            const ma10Value = parseFloat(ma10[i] as string);
            const breakMA10 = !isNaN(ma10Value) && item.close < ma10Value;

            if (change < -2.3 || breakMA10) {
              specialMarks.push({ index: i, type: 'bear' });
              isBullZone = false;
              bullZones.push({ start: currentBullStart, end: i });
              currentBullStart = -1;
            }
          }
        }

        if (isBullZone && currentBullStart >= 0) {
          bullZones.push({ start: currentBullStart, end: filteredData.length - 1 });
        }

        // 计算空头区间（多头区间以外的区域）
        let currentBearStart = -1;
        for (let i = 0; i < filteredData.length; i++) {
          const inBullZone = bullZones.some(zone => i >= zone.start && i <= zone.end);
          if (!inBullZone) {
            if (currentBearStart === -1) {
              currentBearStart = i;
            }
          } else {
            if (currentBearStart !== -1) {
              bearZones.push({ start: currentBearStart, end: i - 1 });
              currentBearStart = -1;
            }
          }
        }
        if (currentBearStart !== -1) {
          bearZones.push({ start: currentBearStart, end: filteredData.length - 1 });
        }

        if (onZonesChange) {
          onZonesChange({ bull: bullZones, bear: bearZones });
        }
      }

      if (showRanking) {
        // 计算每个多头区间内板块 ETF 的排名信息
        bullZoneRankings = bullZones.map(zone => {
          const startDate = filteredData[zone.start].date;
          const prevDate = zone.start > 0 ? filteredData[zone.start - 1].date : null;
          const endDate = filteredData[zone.end].date;
          const startChange0AMV = zone.start > 0
            ? (filteredData[zone.start].close - filteredData[zone.start - 1].close) / filteredData[zone.start - 1].close * 100
            : 0;
          const isSingleDayStart = startChange0AMV > 4;

          const startGains: { name: string; gain: number; series: ExtraSeries }[] = [];
          const zoneGains: { name: string; gain: number }[] = [];

          allETFSeries
            .filter(series => !series.id.startsWith('sh')) // 排除上证指数、沪深300等指数
            .forEach(series => {
              const seriesDataMap = new Map<string, KLineData>();
              series.data.forEach(d => seriesDataMap.set(d.date, d));

              const startItem = seriesDataMap.get(startDate);
              const prevItem = prevDate ? seriesDataMap.get(prevDate) : undefined;
              const endItem = seriesDataMap.get(endDate);

              if (startItem && prevItem && prevDate) {
                const singleDayChange = (startItem.close - prevItem.close) / prevItem.close * 100;
                if (isSingleDayStart) {
                  startGains.push({ name: series.name, gain: singleDayChange, series });
                } else {
                  const prevIndex = series.data.findIndex(d => d.date === prevDate);
                  const prevPrevItem = prevIndex > 0 ? series.data[prevIndex - 1] : undefined;
                  if (prevPrevItem) {
                    const prevDayChange = (prevItem.close - prevPrevItem.close) / prevPrevItem.close * 100;
                    startGains.push({ name: series.name, gain: prevDayChange + singleDayChange, series });
                  }
                }
              }

              if (startItem && endItem) {
                const totalChange = (endItem.close - startItem.close) / startItem.close * 100;
                zoneGains.push({ name: series.name, gain: totalChange });
              }
            });

          const topStart = startGains
            .filter(item => !isNaN(item.gain))
            .sort((a, b) => b.gain - a.gain)
            .slice(0, 5);
          const topZone = zoneGains
            .filter(item => !isNaN(item.gain))
            .sort((a, b) => b.gain - a.gain)
            .slice(0, 5);

          const overlapNames = new Set(topStart.map(s => s.name).filter(name => topZone.some(z => z.name === name)));
          const highlightColor = '#ff6b6b';

          const zoneGainMap = new Map<string, number>();
          zoneGains.forEach(z => zoneGainMap.set(z.name, z.gain));

          const topZoneNames = new Set(topZone.map(z => z.name));

          const startItems = topStart.map(item => {
            const name = item.name.replace('ETF', '');
            const startSign = item.gain >= 0 ? '+' : '';
            const zoneGain = zoneGainMap.get(item.name);
            let zoneText = '';
            if (zoneGain !== undefined && !topZoneNames.has(item.name)) {
              const zoneColor = zoneGain >= 0 ? '#ff4d4d' : '#00b300';
              const zoneSign = zoneGain >= 0 ? '+' : '';
              zoneText = `<span style="color:${zoneColor}">(区间${zoneSign}${zoneGain.toFixed(2)}%)</span>`;
            }
            const text = `${name}${startSign}${item.gain.toFixed(2)}%${zoneText}`;
            return overlapNames.has(item.name)
              ? `<span style="color:${highlightColor};font-weight:bold;">${text}</span>`
              : text;
          });

          const zoneItems = topZone.map(item => {
            const name = item.name.replace('ETF', '');
            const sign = item.gain >= 0 ? '+' : '';
            const text = `${name}${sign}${item.gain.toFixed(2)}%`;
            return overlapNames.has(item.name)
              ? `<span style="color:${highlightColor};font-weight:bold;">${text}</span>`
              : text;
          });

          return {
            zone,
            startItems,
            zoneItems
          };
        });
      }
    }

    const kLineData = filteredData.map((item, index) => {
      if (isNaN(item.close)) return '-';

      let color, borderColor;
      const mark = specialMarks.find(m => m.index === index);

      if (mark?.type === 'bull') {
        color = '#c41e3a';
        borderColor = '#c41e3a';
      } else if (mark?.type === 'bear') {
        color = '#006400';
        borderColor = '#006400';
      } else if (item.close > item.open) {
        color = '#FFB6C1';
        borderColor = '#FFB6C1';
      } else {
        color = '#98FB98';
        borderColor = '#98FB98';
      }

      return {
        value: [item.open, item.close, item.low, item.high],
        itemStyle: { color, borderColor }
      };
    });

    const volumes = filteredData.map((item, index) => {
      if (isNaN(item.close)) return '-';

      let color;
      const mark = specialMarks.find(m => m.index === index);

      if (mark?.type === 'bull') {
        color = '#8B0000';
      } else if (mark?.type === 'bear') {
        color = '#006400';
      } else if (item.close > item.open) {
        color = '#FFB6C1';
      } else {
        color = '#98FB98';
      }

      return {
        value: [index, item.volume],
        itemStyle: { color }
      };
    });

    const ma5 = calculateMA(5, filteredData);
    const ma20 = calculateMA(20, filteredData);
    const ma60 = calculateMA(60, filteredData);

    const extraSeriesData: any[] = [];
    const extraYAxis: any[] = [];

    filteredExtraSeries.forEach((series, idx) => {
      const seriesDataMap = new Map<string, KLineData>();
      series.data.forEach(d => seriesDataMap.set(d.date, d));

      const alignedData = filteredData.map(item => {
        const etfItem = seriesDataMap.get(item.date);
        if (etfItem && !isNaN(etfItem.close)) {
          const isUp = etfItem.close > etfItem.open;
          return {
            value: [etfItem.open, etfItem.close, etfItem.low, etfItem.high],
            itemStyle: {
              color: isUp ? '#e8606c' : '#3dbf7a',
              borderColor: isUp ? '#e8606c' : '#3dbf7a'
            }
          };
        }
        return '-';
      });

      extraSeriesData.push({
        name: series.name,
        type: 'candlestick',
        yAxisIndex: idx + 1,
        data: alignedData,
        itemStyle: {
          borderWidth: 1
        }
      });

      extraYAxis.push({
        type: 'value',
        scale: true,
        position: idx % 2 === 0 ? 'right' : 'left',
        axisLine: { show: true, lineStyle: { color: ETF_COLORS[idx] } },
        axisLabel: {
          show: true,
          color: ETF_COLORS[idx],
          formatter: (value: number) => value.toFixed(2)
        },
        splitLine: { show: false }
      });
    });

    const yAxis = [
      {
        type: 'value',
        scale: true,
        splitArea: { show: false },
        splitLine: { show: true, lineStyle: { color: '#eee' } },
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#666' },
        // axisLabel: { color: '#666', width: 60, align: 'right', overflow: 'truncate' }
      },
      ...extraYAxis,
      {
        type: 'value',
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false }
      }
    ];

    const legendData = [mainSeriesName, 'MA5', 'MA10', 'MA20', 'MA60', ...extraSeries.map(s => s.name)];
    const legendSelected: { [key: string]: boolean } = {
      [mainSeriesName]: true,
      'MA5': false,
      'MA10': true,
      'MA20': false,
      'MA60': true
    };
    extraSeries.forEach(s => {
      legendSelected[s.name] = true;
    });

    const option = {
      backgroundColor: '#fff',
      animation: false,
      legend: {
        show: true,
        data: legendData,
        selected: legendSelected,
        textStyle: { color: '#333' },
        top: 10
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          lineStyle: { color: '#888', type: 'dashed' }
        },
        backgroundColor: 'rgba(0,0,0,0.8)',
        borderColor: '#333',
        textStyle: { color: '#fff' },
        formatter: (params: any) => {
          const kData = params.find((p: any) => p.seriesName === mainSeriesName);
          if (!kData) return '';

          const dataIndex = kData.dataIndex;
          const item = filteredData[dataIndex];
          if (!item || isNaN(item.close)) return '';

          let change = '0.00';
          if (dataIndex > 0) {
            const prevItem = filteredData[dataIndex - 1];
            change = ((item.close - prevItem.close) / prevItem.close * 100).toFixed(2);
          }
          const changeColor = parseFloat(change) >= 0 ? '#ff4d4d' : '#00b300';
          const date = params[0].axisValue;

          // 找到当前日期所在的多头区间和空头区间
          const currentBullZone = bullZones.find(zone => dataIndex >= zone.start && dataIndex <= zone.end);
          const currentBearZone = bearZones.find(zone => dataIndex >= zone.start && dataIndex <= zone.end);
          const currentZone = currentBullZone || currentBearZone;
          const zoneLabel = currentBullZone ? '本多头区间涨幅' : '本空头区间涨幅';

          let tooltipHtml = `
            <div style="font-size:12px;line-height:1.6;">
              <div style="font-weight:bold;margin-bottom:4px;">${date}</div>
              <div>${dataLabel}涨跌幅: <span style="color:${changeColor}">${change}%</span></div>
          `;

          // 如果在多头或空头区间内，显示主序列的区间总涨跌幅
          if (currentZone) {
            const baseIndex = currentBearZone ? Math.max(0, currentZone.start - 1) : currentZone.start;
            const startItem = filteredData[baseIndex];
            if (startItem && !isNaN(startItem.close)) {
              const totalChange = ((item.close - startItem.close) / startItem.close * 100).toFixed(2);
              const totalChangeColor = parseFloat(totalChange) >= 0 ? '#ff4d4d' : '#00b300';
              const zoneLabelColor = currentBullZone ? '#ffd700' : '#00b300';
              tooltipHtml += `
                <div style="color:${zoneLabelColor};padding-left:10px;font-size:11px;">↳ ${zoneLabel}: <span style="color:${totalChangeColor}">${totalChange}%</span></div>
              `;

              // 区间总涨幅（从区间起点到区间终点）
              const zoneEndItem = filteredData[currentZone.end];
              if (zoneEndItem && !isNaN(zoneEndItem.close)) {
                const zoneTotalChange = ((zoneEndItem.close - startItem.close) / startItem.close * 100).toFixed(2);
                const zoneTotalChangeColor = parseFloat(zoneTotalChange) >= 0 ? '#ff4d4d' : '#00b300';
                const zoneTotalLabel = currentBullZone ? '多头区间总涨幅' : '空头区间总涨幅';
                tooltipHtml += `
                  <div style="color:${zoneLabelColor};padding-left:10px;font-size:11px;">↳ ${zoneTotalLabel}: <span style="color:${zoneTotalChangeColor}">${zoneTotalChange}%</span></div>
                `;
              }
            }
          }

          // 独立副图显示至今涨跌幅
          if (seriesType === 'line') {
            const lastValidItem = [...filteredData].reverse().find(d => !isNaN(d.close) && d.close !== 0);
            if (lastValidItem && item.close !== 0) {
              const changeToToday = ((lastValidItem.close - item.close) / item.close * 100).toFixed(2);
              const changeColor = parseFloat(changeToToday) >= 0 ? '#ff4d4d' : '#00b300';
              tooltipHtml += `
                <div>至今涨跌幅: <span style="color:${changeColor}">${changeToToday}%</span></div>
              `;
            }
          }

          filteredExtraSeries.forEach((series, idx) => {
            const seriesDataMap = new Map<string, KLineData>();
            series.data.forEach(d => seriesDataMap.set(d.date, d));
            const etfItem = seriesDataMap.get(item.date);
            if (etfItem && !isNaN(etfItem.close)) {
              let etfChange = '0.00';
              const prevEtfItem = seriesDataMap.get(filteredData[dataIndex - 1]?.date);
              if (prevEtfItem && !isNaN(prevEtfItem.close)) {
                etfChange = ((etfItem.close - prevEtfItem.close) / prevEtfItem.close * 100).toFixed(2);
              }
              const etfChangeColor = parseFloat(etfChange) >= 0 ? '#ff4d4d' : '#00b300';
              tooltipHtml += `
                <div style="color:${etfChangeColor}">${series.name}涨跌幅: <span style="color:${etfChangeColor}">${etfChange}%</span></div>
              `;

              // 如果在多头或空头区间内，显示区间总涨跌幅
              if (currentZone) {
                // 空头区间从启动前一天收盘价开始计算，把第一天跌幅算进区间涨幅
                const baseIndex = currentBearZone ? Math.max(0, currentZone.start - 1) : currentZone.start;
                const startItem = seriesDataMap.get(filteredData[baseIndex]?.date);
                if (startItem && !isNaN(startItem.close)) {
                  const totalChange = ((etfItem.close - startItem.close) / startItem.close * 100).toFixed(2);
                  const totalChangeColor = parseFloat(totalChange) >= 0 ? '#ff4d4d' : '#00b300';
                  const zoneLabelColor = currentBullZone ? ETF_COLORS[idx] : '#00b300';
                  tooltipHtml += `
                    <div style="color:${zoneLabelColor};padding-left:10px;font-size:11px;">↳ ${zoneLabel}: <span style="color:${totalChangeColor}">${totalChange}%</span></div>
                  `;
                }
              }
            }
          });

          // 如果在多头区间内，显示板块 ETF 排名
          if (showRanking && currentBullZone) {
            const ranking = bullZoneRankings.find(r => r.zone === currentBullZone);
            if (ranking && (ranking.startItems.length > 0 || ranking.zoneItems.length > 0)) {
              tooltipHtml += `
                <div style="margin-top:6px;padding-top:6px;border-top:1px solid #555;">
                  ${ranking.startItems.length > 0
                  ? `<div style="color:#ffd700;font-size:11px;margin-bottom:2px;">启动前五:</div>`
                  + ranking.startItems.map(item => `<div style="color:#ffd700;font-size:11px;padding-left:8px;">${item}</div>`).join('')
                  : ''}
                  ${ranking.zoneItems.length > 0
                  ? `<div style="color:#ffd700;font-size:11px;margin-top:4px;margin-bottom:2px;">区间前五:</div>`
                  + ranking.zoneItems.map(item => `<div style="color:#ffd700;font-size:11px;padding-left:8px;">${item}</div>`).join('')
                  : ''}
                </div>
              `;
            }
          }

          tooltipHtml += '</div>';
          return tooltipHtml;
        }
      },
      grid: showVolume
        ? [
          { left: 80, right: 80, height: '55%', top: '15%' },
          { left: 80, right: 80, top: '72%', height: '16%' }
        ]
        : [{ left: 80, right: 80, height: '75%', top: '15%' }],
      xAxis: showVolume
        ? [
          {
            type: 'category',
            data: dates,
            scale: true,
            boundaryGap: false,
            axisLine: { onZero: false, lineStyle: { color: '#ccc' } },
            splitLine: { show: false },
            axisLabel: { color: '#666' },
            min: 'dataMin',
            max: 'dataMax'
          },
          {
            type: 'category',
            gridIndex: 1,
            data: dates,
            scale: true,
            boundaryGap: false,
            axisLine: { onZero: false, lineStyle: { color: '#ccc' } },
            axisTick: { show: false },
            splitLine: { show: false },
            axisLabel: { show: false },
            min: 'dataMin',
            max: 'dataMax'
          }
        ]
        : [{
          type: 'category',
          data: dates,
          scale: true,
          boundaryGap: false,
          axisLine: { onZero: false, lineStyle: { color: '#ccc' } },
          splitLine: { show: false },
          axisLabel: { color: '#666' },
          min: 'dataMin',
          max: 'dataMax'
        }],
      yAxis: showVolume ? yAxis : yAxis.slice(0, -1),
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: showVolume ? [0, 1] : [0],
          start: initialStart,
          end: initialEnd
        },
        ...(showDataZoom ? [{
          show: true,
          xAxisIndex: showVolume ? [0, 1] : [0],
          type: 'slider',
          top: '92%',
          start: initialStart,
          end: initialEnd,
          textStyle: { color: '#666' },
          borderColor: '#ddd',
          fillerColor: 'rgba(100,100,100,0.1)',
          handleStyle: { color: '#999' }
        }] : [])
      ],
      series: [
        ...(seriesType === 'line' ? [{
          name: mainSeriesName,
          type: 'line' as const,
          data: filteredData.map(item => isNaN(item.close) ? '-' : item.close),
          smooth: false,
          symbol: 'none',
          lineStyle: { color: '#333', width: 1.5 },
          markArea: (showZones && (showBullZoneBg || showBearZoneBg)) ? {
            data: [
              ...(showBullZoneBg ? bullZones.map(zone => [
                { xAxis: dates[zone.start], yAxis: 'min', itemStyle: { color: 'rgba(255, 215, 0, 0.15)' } },
                { xAxis: dates[zone.end], yAxis: 'max' }
              ]) : []),
              ...(showBearZoneBg ? bearZones.map(zone => [
                { xAxis: dates[zone.start], yAxis: 'min', itemStyle: { color: 'rgba(173, 216, 230, 0.2)' } },
                { xAxis: dates[zone.end], yAxis: 'max' }
              ]) : [])
            ]
          } : undefined
        }] : [{
          name: mainSeriesName,
          type: 'candlestick' as const,
          data: kLineData,
          markArea: (showZones && (showBullZoneBg || showBearZoneBg)) ? {
            data: [
              ...(showBullZoneBg ? bullZones.map(zone => [
                { xAxis: dates[zone.start], yAxis: 'min', itemStyle: { color: 'rgba(255, 215, 0, 0.15)' } },
                { xAxis: dates[zone.end], yAxis: 'max' }
              ]) : []),
              ...(showBearZoneBg ? bearZones.map(zone => [
                { xAxis: dates[zone.start], yAxis: 'min', itemStyle: { color: 'rgba(173, 216, 230, 0.2)' } },
                { xAxis: dates[zone.end], yAxis: 'max' }
              ]) : [])
            ]
          } : undefined
        }]),
        {
          name: 'MA5',
          type: 'line',
          data: ma5,
          smooth: true,
          lineStyle: { opacity: 0.8, width: 1, color: '#f5d742' },
          symbol: 'none'
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10,
          smooth: true,
          lineStyle: { opacity: 0.8, width: 1, color: '#4287f5' },
          symbol: 'none'
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20,
          smooth: true,
          lineStyle: { opacity: 0.8, width: 1, color: '#f542e3' },
          symbol: 'none'
        },
        {
          name: 'MA60',
          type: 'line',
          data: ma60,
          smooth: true,
          lineStyle: { opacity: 0.8, width: 1, color: '#ff8c00' },
          symbol: 'none'
        },
        ...extraSeriesData,
        ...(showVolume ? [{
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: yAxis.length - 1,
          data: volumes
        }] : [])
      ]
    };

    chartInstance.current.setOption(option);

    // 设置同步组，使多个图表共享缩放/平移
    if (syncGroup) {
      chartInstance.current.group = syncGroup;
      connect(syncGroup);
    }

    // 监听缩放事件，保存当前范围
    chartInstance.current.on('dataZoom', () => {
      const opt = chartInstance.current?.getOption() as { dataZoom?: Array<{ start?: number; end?: number }> } | undefined;
      if (opt?.dataZoom && opt.dataZoom.length > 0) {
        const dz = opt.dataZoom[0];
        if (typeof dz.start === 'number' && typeof dz.end === 'number') {
          zoomRange.current = { start: dz.start, end: dz.end };
        }
      }
    });

    const handleResize = () => {
      chartInstance.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    // 监听容器大小变化（上方副图出现/消失时高度变化），自动 resize
    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined' && chartRef.current) {
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(chartRef.current);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      chartInstance.current?.dispose();
    };
  }, [data, highlightThreshold, showBullZoneBg, showBearZoneBg, extraSeries, allETFSeries, syncGroup, dataLabel, mainSeriesName, showVolume, showRanking, showZones, maxDate, showDataZoom, baseDates]);

  return (
    <div
      ref={chartRef}
      style={{ width: '100%', height: typeof chartHeight === 'number' ? `${chartHeight}px` : chartHeight, backgroundColor: '#fff' }}
    />
  );
};

export default KLineChart;