import { queryIndicatorData, queryIndicators } from '@/services/indicators';
import type { Indicator } from '@/services/indicators';
import { Alert, Button, Checkbox, Descriptions, Empty, InputNumber, Modal, Space, Spin, Typography } from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import KLineChart from '../ActiveMarket/components/KLineChart';
import type { KLineData } from '../ActiveMarket/utils/backtest';
import { DEFAULT_STRATEGY_PARAMS } from '../ActiveMarket/utils/backtest';
import type { ZoneParams } from '../ActiveMarket/components/KLineChart';

interface Props {
  indicator: Indicator;
  compare: boolean;
  onClose: () => void;
}

const IndicatorModal: React.FC<Props> = ({ indicator, compare, onClose }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<KLineData[]>([]);
  const [baseline, setBaseline] = useState<{ indicator: Indicator; data: KLineData[] }>();
  const [showBullZoneBg, setShowBullZoneBg] = useState(true);
  const [showBearZoneBg, setShowBearZoneBg] = useState(true);
  const [zoneParams, setZoneParams] = useState<ZoneParams>(() => ({
    bullStartSingleDay: DEFAULT_STRATEGY_PARAMS.bullStartSingleDay,
    bullStartTwoDay: DEFAULT_STRATEGY_PARAMS.bullStartTwoDay,
    bullEndSingleDay: DEFAULT_STRATEGY_PARAMS.bullEndSingleDay,
    bullStartUseMA10: DEFAULT_STRATEGY_PARAMS.bullStartUseMA10,
    bullEndUseMA10: DEFAULT_STRATEGY_PARAMS.bullEndUseMA10,
  }));
  const dateWindow = useRef<{ start: string; end: string } | null>(null);
  const syncGroup = `indicator-comparison-${indicator.id}`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setData([]);
    setBaseline(undefined);
    dateWindow.current = null;
    (async () => {
      try {
        const [selected, list] = await Promise.all([
          queryIndicatorData(indicator.id),
          compare ? queryIndicators({ current: 1, pageSize: 100 }) : Promise.resolve(null),
        ]);
        let reference;
        if (compare) {
          // The API orders default indicators first, independent of table search/pagination.
          const defaultIndicator = list?.data.find(item => item.is_default);
          if (!defaultIndicator) throw new Error('暂无默认指标可供比对');
          reference = { indicator: defaultIndicator, data: await queryIndicatorData(defaultIndicator.id) };
        }
        if (!cancelled) {
          setData(selected);
          setBaseline(reference);
        }
      } catch {
        if (!cancelled) setError('指标行情加载失败或尚未配置数据，请稍后重试');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [indicator.id, compare, attempt]);

  const selectedDates = data.map(row => row.date).sort();
  const baselineDates = baseline?.data.map(row => row.date).sort() ?? [];
  const start = compare ? [selectedDates[0], baselineDates[0]].filter(Boolean).sort().slice(-1)[0] : selectedDates[0];
  const end = compare ? [selectedDates.slice(-1)[0], baselineDates.slice(-1)[0]].filter(Boolean).sort()[0] : selectedDates.slice(-1)[0];
  const dates = [...new Set([...selectedDates, ...baselineDates])].filter(date => date >= start && date <= end).sort();
  const hasData = data.length > 0 && (!compare || !!baseline?.data.length) && dates.length > 0;
  const renderChart = (rows: KLineData[], name: string) => (
    <KLineChart
      data={rows.filter(row => row.date >= start && row.date <= end)}
      baseDates={dates}
      dateWindowRef={dateWindow}
      defaultWindowYears={1.5}
      syncGroup={compare ? syncGroup : undefined}
      dataLabel={name}
      showZones
      zoneParams={zoneParams}
      highlightThreshold={zoneParams.bullStartSingleDay}
      showBullZoneBg={showBullZoneBg}
      showBearZoneBg={showBearZoneBg}
      showRanking={false}
      showVolume={false}
      chartHeight={compare ? 310 : 400}
    />
  );

  return (
    <Modal open title={`${compare ? '比对基准' : '查看详情'} · ${indicator.name}`}
      onCancel={onClose} footer={null} width={1200} style={{ top: 24 }}
      styles={{ body: { maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' } }}>
      {!compare && <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="指标名称">{indicator.name}</Descriptions.Item>
        <Descriptions.Item label="指标代码">{indicator.code}</Descriptions.Item>
        <Descriptions.Item label="来源">{indicator.source || '—'}</Descriptions.Item>
        <Descriptions.Item label="类型">{indicator.is_default ? '默认指标' : '自定义指标'}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{indicator.created_at}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{indicator.updated_at}</Descriptions.Item>
        <Descriptions.Item label="指标说明" span={2}>
          <div style={{ whiteSpace: 'pre-line', lineHeight: 1.8 }}>{indicator.description || '—'}</div>
        </Descriptions.Item>
      </Descriptions>}
      {loading ? <div style={{ padding: 72, textAlign: 'center' }}><Spin tip="正在加载日 K 线" /></div>
        : error ? <Alert type="error" showIcon message={error}
          action={<Button size="small" onClick={() => setAttempt(value => value + 1)}>重试</Button>} />
          : !hasData ? <Empty description={compare ? '两项指标暂无可比对的共同日期数据' : '暂无行情数据'} />
            : <>
              <div style={{ padding: 12, marginBottom: 16, background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6 }}>
                <Space wrap size={[20, 12]} style={{ marginBottom: 12 }}>
                  <Checkbox checked={showBullZoneBg} onChange={event => setShowBullZoneBg(event.target.checked)}>显示多头区间背景</Checkbox>
                  <Checkbox checked={showBearZoneBg} onChange={event => setShowBearZoneBg(event.target.checked)}>显示空头区间背景</Checkbox>
                </Space>
                <div role="group" aria-label="多头确认条件" style={{ marginBottom: 12 }}><Space wrap size={[20, 12]}>
                  <Typography.Text strong>多头确认条件：</Typography.Text>
                  <Space size={6}>
                    <span>当日涨幅大于</span>
                    <InputNumber aria-label="当日涨幅大于" size="small" min={0} step={0.1} style={{ width: 76 }}
                      value={zoneParams.bullStartSingleDay} onChange={value => { if (value !== null) setZoneParams(params => ({ ...params, bullStartSingleDay: value })); }} />
                    <span>%</span>
                  </Space>
                  <Space size={6}>
                    <span>两日累计涨幅大于</span>
                    <InputNumber aria-label="两日累计涨幅大于" size="small" min={0} step={0.1} style={{ width: 76 }}
                      value={zoneParams.bullStartTwoDay} onChange={value => { if (value !== null) setZoneParams(params => ({ ...params, bullStartTwoDay: value })); }} />
                    <span>%</span>
                  </Space>
                  <Checkbox checked={zoneParams.bullStartUseMA10}
                    onChange={event => setZoneParams(params => ({ ...params, bullStartUseMA10: event.target.checked }))}>启动日收盘价站上 MA10 才启动多头</Checkbox>
                </Space></div>
                <div role="group" aria-label="空头确认条件"><Space wrap size={[20, 12]}>
                  <Typography.Text strong>空头确认条件：</Typography.Text>
                  <Space size={6}>
                    <span>单日涨跌幅低于</span>
                    <InputNumber aria-label="结束多头的单日涨跌幅" size="small" max={0} min={-100} step={0.1} style={{ width: 76 }}
                      value={zoneParams.bullEndSingleDay} onChange={value => { if (value !== null) setZoneParams(params => ({ ...params, bullEndSingleDay: value })); }} />
                    <span>% 结束多头</span>
                  </Space>
                  <Checkbox checked={zoneParams.bullEndUseMA10}
                    onChange={event => setZoneParams(params => ({ ...params, bullEndUseMA10: event.target.checked }))}>收盘价跌破 MA10 也结束多头</Checkbox>
                </Space></div>
              </div>
              <Typography.Text type="secondary">
                {start} ～ {end}{compare ? ' · 上下图缩放与十字光标联动' : ''}
              </Typography.Text>
              {compare && baseline && <>
                <Typography.Title level={5}>基准：{baseline.indicator.name} · 日 K</Typography.Title>
                {renderChart(baseline.data, baseline.indicator.name)}
              </>}
              <Typography.Title level={5}>{indicator.name} · 日 K</Typography.Title>
              {compare && indicator.description && <Typography.Paragraph
                type="secondary"
                ellipsis={{ rows: 1, tooltip: indicator.description }}
                style={{ marginBottom: 0 }}>
                {indicator.description}
              </Typography.Paragraph>}
              {renderChart(data, indicator.name)}
            </>}
    </Modal>
  );
};

export default IndicatorModal;
