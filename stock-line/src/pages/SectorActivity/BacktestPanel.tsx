import React, { useEffect, useRef, useState } from 'react';
import { Button, Modal, Table, Tag } from 'antd';
import * as echarts from 'echarts';
import type { SectorBacktestResult, Trade } from './backtest';

const pct = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
const shade = (value: number) => value > 0 ? '#cf2343' : value < 0 ? '#238672' : '#819097';
const ReturnValue = ({ value }: { value: number }) => <strong style={{ color: shade(value) }}>{pct(value)}</strong>;

function NavChart({ result }: { result: SectorBacktestResult }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => Number(value).toFixed(4) },
      legend: { top: 0, data: ['策略净值', '行业买入持有'], selected: { '行业买入持有': false } },
      grid: { left: 60, right: 30, top: 45, bottom: 35 },
      xAxis: { type: 'category', data: result.navSeries.map(point => point.date), boundaryGap: false },
      yAxis: { type: 'value', scale: true },
      series: [
        { name: '策略净值', type: 'line', showSymbol: false, data: result.navSeries.map(point => point.nav),
          itemStyle: { color: '#cf2343' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#cf234344' }, { offset: 1, color: '#cf234302' }]) } },
        { name: '行业买入持有', type: 'line', showSymbol: false, data: result.navSeries.map(point => point.benchmark),
          itemStyle: { color: '#d5a057' }, lineStyle: { type: 'dashed' } },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [result]);
  return <div ref={ref} style={{ height: 350, width: '100%' }} />;
}

export default function BacktestPanel({ result, name }: { result: SectorBacktestResult; name: string }) {
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState<string | null>(null);
  const first = result.navSeries[0];
  const last = result.navSeries[result.navSeries.length - 1];
  const trades = result.trades.filter(trade => !year || (trade.entryDate.slice(0, 4) <= year && trade.endDate.slice(0, 4) >= year));
  return <>
    <div className="sector-backtest-summary">
      <Button type="primary" disabled={!first} onClick={() => { setYear(null); setOpen(true); }}>查看回测结果</Button>
      <div><strong>总收益率：<ReturnValue value={result.totalReturn} /></strong>
        <div className="sector-backtest-muted">最大回撤 {result.maxDD.toFixed(2)}% · 平均回撤 {result.avgDD.toFixed(2)}%</div></div>
      {result.years.map(item => <button className="sector-year-link" key={item.year} onClick={() => { setYear(item.year); setOpen(true); }}>
        <span>{item.year}{item.year === '2024' ? '（9月起）' : ''}</span><ReturnValue value={item.returnPct} />
      </button>)}
    </div>
    <Modal open={open} onCancel={() => setOpen(false)} footer={null} width={1200} style={{ top: 24 }}
      styles={{ body: { maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' } }} title={`${name} · 多空区间策略回测`}>
      {open && <>
        <p className="sector-backtest-muted">{first?.date} ～ {last?.date} · 行业指数模拟 · 多头全仓、空头持现金 · 次交易日收盘执行 · 未扣手续费及滑点</p>
        <NavChart result={result} />
        <div className="sector-backtest-years">
          {result.years.map(item => <div key={item.year} className="sector-year-card">
            <div><strong>{item.year}</strong><ReturnValue value={item.returnPct} /></div>
            <p className="sector-backtest-muted">{item.startDate} ～ {item.endDate}</p>
            <div><span>期初 {item.startNav.toFixed(4)}</span><span>期末 {item.endNav.toFixed(4)}</span></div>
            <p>最大回撤 {item.maxDD.toFixed(2)}% · 平均回撤 {item.avgDD.toFixed(2)}%</p>
            <Button type="link" style={{ padding: 0 }} onClick={() => setYear(item.year)}>查看交易明细</Button>
          </div>)}
        </div>
        <div className="sector-backtest-total"><strong>累计</strong><span>起点 1.0000 → 终点 {(last?.nav ?? 1).toFixed(4)}</span>
          <span>最大回撤 {result.maxDD.toFixed(2)}%</span><span>平均回撤 {result.avgDD.toFixed(2)}%</span>
          <span>模拟100万 → {((last?.nav ?? 1) * 100).toFixed(1)}万</span><ReturnValue value={result.totalReturn} /></div>
        <p>行业买入持有基准：<ReturnValue value={result.benchmarkReturn} /></p>
        <p className="sector-backtest-muted">年度收益按每日净值分年，跨年持仓收益拆入对应年份；平均回撤为发生回撤交易日的回撤均值。2024年从数据首日开始，末年截至最新数据。最新持仓按末日收盘估值，末日信号尚未成交。</p>
        <div className="sector-signal-row"><strong>{year ? `${year} 年相关交易` : '全部交易'} · {trades.length} 笔</strong>
          {year && <Button size="small" onClick={() => setYear(null)}>显示全部</Button>}</div>
        <Table<Trade> size="small" rowKey="entryDate" dataSource={trades} pagination={{ pageSize: 8 }} scroll={{ x: 850 }} columns={[
          { title: '启动确认', dataIndex: 'signalDate' },
          { title: '买入日期', dataIndex: 'entryDate' },
          { title: '买入点位', dataIndex: 'entryPrice', render: (value: number) => value.toFixed(2) },
          { title: '退出确认', dataIndex: 'exitSignalDate', render: (value?: string) => value || '—' },
          { title: '卖出 / 估值日期', dataIndex: 'endDate' },
          { title: '卖出 / 估值点位', dataIndex: 'endPrice', render: (value: number) => value.toFixed(2) },
          { title: '状态', dataIndex: 'open', render: (value: boolean) => <Tag color={value ? 'blue' : 'default'}>{value ? '持仓中' : '已结束'}</Tag> },
          { title: '整笔收益', dataIndex: 'returnPct', render: (value: number) => <ReturnValue value={value} /> },
        ]} />
        <p className="sector-backtest-muted">交易明细展示与所选年份有交集的整笔交易，整笔收益不等于该年的收益。信号来自板块活跃市值，收益来自行业价格，不等于具体ETF的可成交收益。</p>
      </>}
    </Modal>
  </>;
}
