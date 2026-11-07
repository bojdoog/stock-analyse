import React, { useEffect, useState } from 'react';
import { Alert, Button, Spin } from 'antd';
import KLineChart from '../ActiveMarket/components/KLineChart';

interface Bar { date: string; open: number; high: number; low: number; close: number; volume: number; amount: number }

export default function MarketDateChart({ availableDates, onSelect }: {
  availableDates: string[]; onSelect: (date: string) => void;
}) {
  const [data, setData] = useState<Bar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const get = async (url: string) => {
        const response = await fetch(url, { signal: controller.signal });
        const body = await response.json();
        if (!response.ok || body.code !== 0) throw new Error(body.message || '活跃市值加载失败');
        return body;
      };
      setLoading(true); setError('');
      try {
        const catalog = await get('/api/indicators?code=0AMV&pageSize=100');
        const indicator = catalog.data.find((item: { code: string }) => item.code === '0AMV');
        if (!indicator) throw new Error('未找到活跃市值(默认)指标');
        const result = await get(`/api/indicators/${indicator.id}/data`);
        if (!controller.signal.aborted) setData(result.data.map((row: Bar) => ({ ...row,
          open: row.open ?? NaN, high: row.high ?? NaN, low: row.low ?? NaN,
          volume: row.volume ?? NaN, amount: row.amount ?? NaN,
        })));
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '活跃市值加载失败');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [retry]);
  return <section className="sector-market-panel">
    {notice && <Alert type="info" message={notice} closable onClose={() => setNotice('')} />}
    {error ? <Alert type="error" message={error} action={<Button onClick={() => setRetry(n => n + 1)}>重试</Button>} /> :
      <Spin spinning={loading} wrapperClassName="sector-market-chart">
        {data.length > 0 ? <KLineChart data={data} chartHeight="100%" defaultWindowYears={1}
          showQuoteBar={false}
          showVolume={false} showMACD={false} showRanking={false} showBullZoneBg showBearZoneBg
          onDayClick={day => {
            if (!availableDates.includes(day)) { setNotice(`${day} 暂无行业数据，请选择有数据的交易日`); return; }
            setNotice(''); onSelect(day);
          }} /> : <div style={{ height: '100%' }} />}
      </Spin>}
  </section>;
}
