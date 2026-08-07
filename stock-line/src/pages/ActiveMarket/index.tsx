import React, { useEffect, useState } from 'react';
import { Select, Modal, Collapse, Tooltip } from 'antd';
import { DeleteTwoTone } from '@ant-design/icons';
import KLineChart from './components/KLineChart';
import BacktestChart from './components/BacktestChart';
import { runBacktest, BacktestResult, BacktestTrade, StrategyParams, DEFAULT_STRATEGY_PARAMS, calculateOptimalWeights, OptimalMethod, MoneyflowData, RankingMethod, BenchmarkReturn } from './utils/backtest';

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

const ETF_OPTIONS = [
    { value: '510050', label: '上证50ETF', file: 'etf/510050_上证50ETF.csv' },
    { value: '510300', label: '沪深300ETF', file: 'etf/510300_沪深300ETF.csv' },
    { value: '563300', label: '中证2000ETF', file: 'etf/563300_中证2000ETF.csv' },
    { value: '159915', label: '创业板ETF', file: 'etf/159915_创业板ETF.csv' },
    { value: '512480', label: '半导体ETF', file: 'etf/512480_半导体ETF.csv' },
    { value: '588710', label: '科创半导体设备ETF', file: 'etf/588710_科创半导体设备ETF.csv' },
    { value: '515880', label: '通信ETF', file: 'etf/515880_通信ETF.csv' },
    { value: '159381', label: '创业板人工智能ETF', file: 'etf/159381_创业板人工智能ETF.csv' },
    { value: '516160', label: '新能源ETF', file: 'etf/516160_新能源ETF.csv' },
    { value: '515030', label: '新能源车ETF', file: 'etf/515030_新能源车ETF.csv' },
    { value: '512400', label: '有色ETF', file: 'etf/512400_有色ETF.csv' },
    { value: '510150', label: '消费ETF', file: 'etf/510150_消费ETF.csv' },
    { value: '515220', label: '煤炭ETF', file: 'etf/515220_煤炭ETF.csv' },
    { value: '512690', label: '白酒ETF', file: 'etf/512690_白酒ETF.csv' },
    { value: '512880', label: '证券ETF', file: 'etf/512880_证券ETF.csv' },
    { value: '512800', label: '银行ETF', file: 'etf/512800_银行ETF.csv' },
    { value: '562500', label: '机器人ETF', file: 'etf/562500_机器人ETF.csv' },
    { value: '510660', label: '创新药ETF', file: 'etf/510660_创新药ETF.csv' },
    { value: '159869', label: '游戏ETF', file: 'etf/159869_游戏ETF.csv' },
    { value: '515230', label: '软件ETF', file: 'etf/515230_软件ETF.csv' },
    { value: '512980', label: '传媒ETF', file: 'etf/512980_传媒ETF.csv' },
    { value: '516290', label: '光伏ETF', file: 'etf/516290_光伏ETF.csv' },
    { value: '561380', label: '电网设备ETF', file: 'etf/561380_电网设备ETF.csv' },
    { value: '159206', label: '卫星ETF', file: 'etf/159206_卫星ETF.csv' },
    { value: '159638', label: '高端装备ETF', file: 'etf/159638_高端装备ETF.csv' },
    { value: '512660', label: '军工ETF', file: 'etf/512660_军工ETF.csv' },
    { value: '159929', label: '医药ETF', file: 'etf/159929_医药ETF.csv' },
    { value: 'sh000001', label: '上证指数', file: 'index/000001_上证指数.csv' },
    { value: 'sh000300', label: '沪深300', file: 'index/000300_沪深300.csv' },
];

const ActiveMarket: React.FC = () => {
    const [data, setData] = useState<KLineData[]>([]);
    const [loading, setLoading] = useState(true);
    const [showBullZoneBg, setShowBullZoneBg] = useState(false);
    const [showBearZoneBg, setShowBearZoneBg] = useState(false);
    const [selectedETFs, setSelectedETFs] = useState<string[]>([]);
    const [extraSeries, setExtraSeries] = useState<ExtraSeries[]>([]);
    const [allETFSeries, setAllETFSeries] = useState<ExtraSeries[]>([]);
    const [upperETFId, setUpperETFId] = useState<string | undefined>(undefined);
    const [chartZones, setChartZones] = useState<{ bull: { start: number; end: number }[]; bear: { start: number; end: number }[] } | undefined>(undefined);
    const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
    const [showBacktestModal, setShowBacktestModal] = useState(false);
    const [selectedYear, setSelectedYear] = useState<number | null>(null);
    const [strategyParams, setStrategyParams] = useState<StrategyParams>(DEFAULT_STRATEGY_PARAMS);
    const [activePreset, setActivePreset] = useState<string>('default');
    const [showStrategyCard, setShowStrategyCard] = useState(false);
    const [moneyflowData, setMoneyflowData] = useState<MoneyflowData[]>([]);
    const [conceptMoneyflowData, setConceptMoneyflowData] = useState<MoneyflowData[]>([]);
    const [indMoneyflowData, setIndMoneyflowData] = useState<MoneyflowData[]>([]);

    // 当前页面全屏展示图表，去除 body 默认 margin/padding 避免滚动条
    useEffect(() => {
        const originalMargin = document.body.style.margin;
        const originalPadding = document.body.style.padding;
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        return () => {
            document.body.style.margin = originalMargin;
            document.body.style.padding = originalPadding;
        };
    }, []);

    useEffect(() => {
        fetch('/api/amv')
            .then(res => res.json())
            .then(json => {
                if (json.code === 0) {
                    setData(json.data);
                } else {
                    console.error('加载活跃市值失败:', json.message);
                }
                setLoading(false);
            })
            .catch(err => {
                console.error('加载数据失败:', err);
                setLoading(false);
            });
    }, []);

    // 加载所有板块 ETF + Index 数据（通过后端 API，27+2 → 1 个请求）
    useEffect(() => {
        fetch('/api/sector-data')
            .then(res => res.json())
            .then(json => {
                if (json.code === 0) {
                    const { etf_data, index_data } = json.data;
                    const allSeries: ExtraSeries[] = [
                        ...(etf_data || []),
                        ...(index_data || []),
                    ];
                    setAllETFSeries(allSeries);
                }
            })
            .catch(err => console.error('加载板块数据失败:', err));
    }, []);

    useEffect(() => {
        setExtraSeries(allETFSeries.filter(s => selectedETFs.includes(s.id)));
    }, [selectedETFs, allETFSeries]);

    // 加载资金流向数据（通过后端 API，1615 → 1 个请求）
    useEffect(() => {
        fetch('/api/moneyflow/batch?types=ind_dc,cnt_ths,ind_ths')
            .then(res => res.json())
            .then(json => {
                if (json.code === 0) {
                    const { ind_dc, cnt_ths, ind_ths } = json.data;
                    setMoneyflowData(ind_dc || []);
                    setConceptMoneyflowData(cnt_ths || []);
                    setIndMoneyflowData(ind_ths || []);
                }
            })
            .catch(err => console.error('加载资金流向数据失败:', err));
    }, []);

    // 数据加载完成后运行多空区间策略回测
    useEffect(() => {
        if (data.length > 0 && allETFSeries.length > 0) {
            const result = runBacktest(data, allETFSeries, strategyParams, moneyflowData, conceptMoneyflowData, indMoneyflowData);
            setBacktestResult(result);
        }
    }, [data, allETFSeries, strategyParams, moneyflowData, conceptMoneyflowData, indMoneyflowData]);

    if (loading) {
        return (
            <div style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                backgroundColor: '#f5f5f5',
                gap: 20,
            }}>
                <div style={{
                    width: 48,
                    height: 48,
                    border: '4px solid #e0e0e0',
                    borderTop: '4px solid #1890ff',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                }} />
                <div style={{ color: '#666', fontSize: 14 }}>数据加载中，请稍候...</div>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
        );
    }

    const activeMarketLastDate = data.length > 0 ? data[data.length - 1].date : undefined;
    const activeMarketDates = data.map(d => d.date);

    return (
        <div style={{ padding: 20, backgroundColor: '#f5f5f5', height: 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <h1 style={{ color: '#333', marginBottom: 20, flexShrink: 0 }}>活跃市值 (0AMV)</h1>
            <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 15, flexShrink: 0 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                    <input
                        type="checkbox"
                        checked={showBullZoneBg}
                        onChange={(e) => setShowBullZoneBg(e.target.checked)}
                        style={{ width: 16, height: 16 }}
                    />
                    <span style={{ color: '#666', fontSize: 14 }}>显示多头区间背景</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                    <input
                        type="checkbox"
                        checked={showBearZoneBg}
                        onChange={(e) => setShowBearZoneBg(e.target.checked)}
                        style={{ width: 16, height: 16 }}
                    />
                    <span style={{ color: '#666', fontSize: 14 }}>显示空头区间背景</span>
                </label>
                <span style={{ color: '#999', fontSize: 14 }}>|</span>
                <span style={{ color: '#666', fontSize: 14 }}>叠加显示:</span>
                <Select
                    mode="multiple"
                    allowClear
                    placeholder="选择指数/ETF"
                    value={selectedETFs}
                    onChange={setSelectedETFs}
                    options={ETF_OPTIONS}
                    style={{ minWidth: 300, fontSize: 14 }}
                    maxTagCount="responsive"
                    size="middle"
                />
                <span style={{ color: '#999', fontSize: 14 }}>|</span>
                <span style={{ color: '#666', fontSize: 14 }}>上方副图:</span>
                <Select
                    allowClear
                    placeholder="选择ETF单独展示"
                    value={upperETFId}
                    onChange={setUpperETFId}
                    options={ETF_OPTIONS}
                    style={{ minWidth: 180, fontSize: 14 }}
                    size="middle"
                />
            </div>
            <Collapse style={{ marginBottom: 12, flexShrink: 0, backgroundColor: '#fff' }}>
                <Collapse.Panel header="策略设置" key="strategy">
                    <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <span style={{ color: '#333', fontSize: 14, fontWeight: 500 }}>策略预设：</span>
                        {[
                            { key: 'default', label: '默认策略' },
                            { key: 'conservative', label: '稳健策略' },
                            { key: 'aggressive', label: '激进策略' },
                        ].map(preset => (
                            <button
                                key={preset.key}
                                onClick={() => {
                                    setActivePreset(preset.key);
                                    if (preset.key === 'default') {
                                        setStrategyParams(DEFAULT_STRATEGY_PARAMS);
                                    } else if (preset.key === 'conservative') {
                                        setStrategyParams({
                                            ...DEFAULT_STRATEGY_PARAMS,
                                            bullStartSingleDay: 5,
                                            bullStartTwoDay: 5,
                                            bullEndSingleDay: -1.5,
                                        });
                                    } else if (preset.key === 'aggressive') {
                                        setStrategyParams({
                                            ...DEFAULT_STRATEGY_PARAMS,
                                            bullStartSingleDay: 3,
                                            bullStartTwoDay: 3,
                                            bullEndSingleDay: -3,
                                        });
                                    }
                                }}
                                style={{
                                    padding: '4px 12px',
                                    fontSize: 13,
                                    border: activePreset === preset.key ? '1px solid #1890ff' : '1px solid #d9d9d9',
                                    backgroundColor: activePreset === preset.key ? '#e6f7ff' : '#fff',
                                    color: activePreset === preset.key ? '#1890ff' : '#666',
                                    borderRadius: 4,
                                    cursor: 'pointer',
                                }}
                            >
                                {preset.label}
                            </button>
                        ))}
                        <span style={{ color: '#e8e8e8', margin: '0 4px' }}>|</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
                            回测区间
                            <Select
                                value={strategyParams.startYear}
                                onChange={val => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({
                                        ...p,
                                        startYear: Math.min(val, p.endYear),
                                    }));
                                }}
                                options={Array.from({ length: (new Date().getFullYear() - 2013 + 1) }, (_, i) => ({
                                    value: 2013 + i,
                                    label: `${2013 + i}年`,
                                }))}
                                style={{ width: 90 }}
                                size="small"
                            />
                            <span style={{ color: '#999' }}>~</span>
                            <Select
                                value={strategyParams.endYear}
                                onChange={val => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({
                                        ...p,
                                        endYear: Math.max(val, p.startYear),
                                    }));
                                }}
                                options={Array.from({ length: (new Date().getFullYear() - 2013 + 1) }, (_, i) => ({
                                    value: 2013 + i,
                                    label: `${2013 + i}年`,
                                }))}
                                style={{ width: 90 }}
                                size="small"
                                getPopupContainer={trigger => trigger.parentElement as HTMLElement}
                            />
                            <span style={{ color: '#e8e8e8', margin: '0 4px' }}>|</span>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
                                买入排名方式：
                                <Select
                                    value={strategyParams.rankingMethod}
                                    onChange={val => {
                                        setActivePreset('custom');
                                        setStrategyParams(p => ({ ...p, rankingMethod: val as RankingMethod }));
                                    }}
                                    options={[
                                        { value: 'etf_gain', label: 'ETF涨幅' },
                                        { value: 'dc_moneyflow', label: '东财板块流入' },
                                        { value: 'ths_moneyflow', label: '同花顺板块流入' },
                                        { value: 'ths_concept', label: '同花顺概念流入' },
                                    ]}
                                    style={{ width: 140 }}
                                    size="small"
                                />
                            </label>
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px 24px', marginBottom: 12 }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
                            当日涨幅大于
                            <input
                                type="number"
                                step={0.1}
                                value={strategyParams.bullStartSingleDay}
                                onChange={e => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({ ...p, bullStartSingleDay: parseFloat(e.target.value) || 0 }));
                                }}
                                style={{ width: 60, padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                            />
                            %
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
                            两日累计涨幅大于
                            <input
                                type="number"
                                step={0.1}
                                value={strategyParams.bullStartTwoDay}
                                onChange={e => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({ ...p, bullStartTwoDay: parseFloat(e.target.value) || 0 }));
                                }}
                                style={{ width: 60, padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                            />
                            %
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
                            单日跌幅大于
                            <input
                                type="number"
                                step={0.1}
                                value={strategyParams.bullEndSingleDay}
                                onChange={e => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({ ...p, bullEndSingleDay: parseFloat(e.target.value) || 0 }));
                                }}
                                style={{ width: 60, padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                            />
                            % 结束多头
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666', cursor: 'pointer' }}>
                            <input
                                type="checkbox"
                                checked={strategyParams.bullEndUseMA10}
                                onChange={e => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({ ...p, bullEndUseMA10: e.target.checked }));
                                }}
                                style={{ width: 14, height: 14 }}
                            />
                            收盘价跌破 MA10 也结束多头
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
                            空头买银行起始年：
                            <input
                                type="number"
                                value={strategyParams.bearStartYear}
                                onChange={e => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({ ...p, bearStartYear: parseInt(e.target.value, 10) || 0 }));
                                }}
                                style={{ width: 70, padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                            />
                        </label>
                    </div>

                    <div style={{ marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
                            <span style={{ fontSize: 13, color: '#666' }}>多头区间买入比例（前 N ETF）：</span>
                            <button
                                onClick={() => {
                                    setActivePreset('custom');
                                    setStrategyParams(p => ({ ...p, weights: [...p.weights, 0] }));
                                }}
                                style={{
                                    padding: '4px 10px',
                                    fontSize: 13,
                                    color: '#1890ff',
                                    backgroundColor: '#fff',
                                    border: '1px solid #1890ff',
                                    borderRadius: 4,
                                    cursor: 'pointer',
                                }}
                            >
                                + 添加排名
                            </button>
                            <button
                                onClick={() => {
                                    setActivePreset('default');
                                    setStrategyParams(p => ({ ...p, weights: [...DEFAULT_STRATEGY_PARAMS.weights] }));
                                }}
                                style={{
                                    padding: '4px 10px',
                                    fontSize: 13,
                                    color: '#666',
                                    backgroundColor: '#fff',
                                    border: '1px solid #d9d9d9',
                                    borderRadius: 4,
                                    cursor: 'pointer',
                                }}
                            >
                                恢复默认
                            </button>
                            <span style={{ color: '#e8e8e8', margin: '0 4px' }}>|</span>
                            {([
                                { key: 'equal', label: '等权', tip: '前 5 名 ETF 各买入 20%，不考虑历史表现差异。' },
                                { key: 'return', label: '收益加权', tip: '按历史各名次（第1~5名）的平均区间收益比例分配仓位，收益高的名次配更多。' },
                                { key: 'growth', label: '增长最优', tip: '网格搜索所有权重组合，找出使历史多头区间累计净值乘积最大的分配方案。' },
                                { key: 'sharpe', label: '夏普最优', tip: '网格搜索所有权重组合，找出使历史多头区间收益均值/波动（夏普）最大的分配方案。' },
                            ] as { key: OptimalMethod; label: string; tip: string }[]).map((item) => (
                                <Tooltip key={item.key} title={item.tip} placement="top">
                                    <button
                                        onClick={() => {
                                            if (!backtestResult) return;
                                            setActivePreset('custom');
                                            const optimal = calculateOptimalWeights(backtestResult, item.key);
                                            setStrategyParams(p => ({ ...p, weights: optimal }));
                                        }}
                                        disabled={!backtestResult}
                                        style={{
                                            padding: '2px 8px',
                                            fontSize: 12,
                                            color: backtestResult ? '#1890ff' : '#bbb',
                                            backgroundColor: '#fff',
                                            border: '1px solid #1890ff',
                                            borderRadius: 4,
                                            cursor: backtestResult ? 'pointer' : 'not-allowed',
                                            lineHeight: '20px',
                                        }}
                                    >
                                        {item.label}
                                    </button>
                                </Tooltip>
                            ))}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
                            {strategyParams.weights.map((w, idx) => {
                                const otherTotal = strategyParams.weights.reduce((a, b, i) => a + (i === idx ? 0 : b), 0);
                                const maxVal = Math.max(0, 100 - otherTotal);
                                return (
                                    <label key={idx} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#666' }}>
                                        第{idx + 1}名
                                        <input
                                            type="number"
                                            step={1}
                                            min={0}
                                            max={maxVal}
                                            value={w}
                                            onChange={e => {
                                                setActivePreset('custom');
                                                const raw = parseFloat(e.target.value) || 0;
                                                const val = Math.min(Math.max(raw, 0), maxVal);
                                                const newWeights = [...strategyParams.weights];
                                                newWeights[idx] = val;
                                                setStrategyParams(p => ({ ...p, weights: newWeights }));
                                            }}
                                            style={{ width: 60, padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                                        />
                                        %
                                        {strategyParams.weights.length > 1 && (
                                            <span
                                                onClick={() => {
                                                    setActivePreset('custom');
                                                    const newWeights = strategyParams.weights.filter((_, i) => i !== idx);
                                                    setStrategyParams(p => ({ ...p, weights: newWeights }));
                                                }}
                                                style={{
                                                    marginLeft: 4,
                                                    cursor: 'pointer',
                                                    display: 'inline-flex',
                                                    alignItems: 'center',
                                                }}
                                                title="删除"
                                            >
                                                <DeleteTwoTone twoToneColor="#ff4d4f" />
                                            </span>
                                        )}
                                    </label>
                                );
                            })}
                            <span style={{
                                fontSize: 13,
                                color: strategyParams.weights.reduce((a, b) => a + b, 0) > 100 ? '#ff4d4f' : '#999',
                                fontWeight: strategyParams.weights.reduce((a, b) => a + b, 0) > 100 ? 500 : 'normal',
                            }}>
                                合计：{strategyParams.weights.reduce((a, b) => a + b, 0).toFixed(0)}%
                            </span>
                        </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                        <button
                            onClick={() => setShowBacktestModal(true)}
                            style={{
                                padding: '6px 16px',
                                fontSize: 14,
                                color: '#fff',
                                backgroundColor: '#1890ff',
                                border: 'none',
                                borderRadius: 4,
                                cursor: 'pointer',
                            }}
                        >
                            查看回测结果
                        </button>
                        {backtestResult && (
                            <>
                                <span style={{ fontSize: 14, color: backtestResult.totalReturn >= 0 ? '#c41e3a' : '#006400', fontWeight: 500 }}>
                                    总收益率：{backtestResult.totalReturn >= 0 ? '+' : ''}{(backtestResult.totalReturn * 100).toFixed(2)}%
                                </span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                                    {backtestResult.yearResults.map(r => (
                                        <div key={r.year} style={{ textAlign: 'center', minWidth: 48 }}>
                                            <div style={{ fontSize: 11, color: '#999' }}>{r.year}</div>
                                            <div style={{
                                                fontSize: 12,
                                                color: r.annual_return >= 0 ? '#c41e3a' : '#006400',
                                                fontWeight: 500,
                                            }}>
                                                {r.annual_return >= 0 ? '+' : ''}{r.annual_return.toFixed(2)}%
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', fontSize: 13, color: '#666', marginTop: 4 }}>
                                    <span style={{ fontWeight: 500 }}>基准对比：</span>
                                    {backtestResult.benchmarkReturns.map(b => (
                                        <span key={b.name} style={{ color: b.totalReturn >= 0 ? '#c41e3a' : '#006400' }}>
                                            {b.name}：{b.totalReturn >= 0 ? '+' : ''}{(b.totalReturn * 100).toFixed(2)}%
                                        </span>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </Collapse.Panel>
            </Collapse>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, gap: upperETFId ? 12 : 0 }}>
                {upperETFId && (
                    <div style={{ flex: '0 0 30%', minHeight: 220, display: 'flex', flexDirection: 'column', border: '1px solid #ddd', borderRadius: 4, padding: '8px 0', backgroundColor: '#fff' }}>
                        <div style={{ fontSize: 14, fontWeight: 'bold', color: '#333', marginBottom: 4, padding: '0 12px', flexShrink: 0 }}>
                            {ETF_OPTIONS.find(o => o.value === upperETFId)?.label}（独立副图）
                        </div>
                        <div style={{ flex: 1, minHeight: 0 }}>
                            <KLineChart
                                data={allETFSeries.find(s => s.id === upperETFId)?.data || []}
                                dataLabel={ETF_OPTIONS.find(o => o.value === upperETFId)?.label || ''}
                                mainSeriesName={ETF_OPTIONS.find(o => o.value === upperETFId)?.label || '日K'}
                                highlightThreshold={4}
                                showZones={true}
                                showBullZoneBg={showBullZoneBg}
                                showBearZoneBg={showBearZoneBg}
                                showRanking={false}
                                showVolume={false}
                                seriesType="line"
                                chartHeight="100%"
                                syncGroup="active-market-sync"
                                maxDate={activeMarketLastDate}
                                showDataZoom={false}
                                baseDates={activeMarketDates}
                                zones={chartZones}
                            />
                        </div>
                    </div>
                )}
                <div style={{ flex: 1, minHeight: 0 }}>
                    <KLineChart
                        data={data}
                        highlightThreshold={4}
                        showBullZoneBg={showBullZoneBg}
                        showBearZoneBg={showBearZoneBg}
                        extraSeries={extraSeries}
                        allETFSeries={allETFSeries}
                        syncGroup="active-market-sync"
                        chartHeight="100%"
                        onZonesChange={setChartZones}
                    />
                </div>
            </div>

            <Modal
                title="多空区间策略回测"
                open={showBacktestModal}
                onCancel={() => setShowBacktestModal(false)}
                footer={null}
                width={760}
                bodyStyle={{ padding: '28px 36px' }}
            >
                {backtestResult && (
                    <>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 15 }}>
                            <thead>
                                <tr style={{ backgroundColor: '#f5f5f5' }}>
                                    <th style={{ padding: '14px 18px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>年份</th>
                                    <th style={{ padding: '14px 18px', textAlign: 'right', borderBottom: '1px solid #ddd' }}>年初净值</th>
                                    <th style={{ padding: '14px 18px', textAlign: 'right', borderBottom: '1px solid #ddd' }}>年末净值</th>
                                    <th style={{ padding: '14px 18px', textAlign: 'right', borderBottom: '1px solid #ddd' }}>年收益率</th>
                                    <th style={{ padding: '14px 18px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {backtestResult.yearResults.map(r => (
                                    <tr key={r.year}>
                                        <td style={{ padding: '14px 18px', borderBottom: '1px solid #eee' }}>{r.year}</td>
                                        <td style={{ padding: '14px 18px', textAlign: 'right', borderBottom: '1px solid #eee' }}>{r.start_nav.toFixed(4)}</td>
                                        <td style={{ padding: '14px 18px', textAlign: 'right', borderBottom: '1px solid #eee' }}>{r.end_nav.toFixed(4)}</td>
                                        <td style={{ padding: '14px 18px', textAlign: 'right', borderBottom: '1px solid #eee', color: r.annual_return >= 0 ? '#c41e3a' : '#006400', fontWeight: 500 }}>
                                            {r.annual_return >= 0 ? '+' : ''}{r.annual_return.toFixed(2)}%
                                        </td>
                                        <td style={{ padding: '14px 18px', borderBottom: '1px solid #eee' }}>
                                            <a
                                                onClick={() => { setSelectedYear(r.year); }}
                                                style={{ color: '#1890ff', cursor: 'pointer' }}
                                            >
                                                查看交易明细
                                            </a>
                                        </td>
                                    </tr>
                                ))}
                                <tr style={{ fontWeight: 'bold', backgroundColor: '#fafafa' }}>
                                    <td style={{ padding: '14px 18px' }}>累计</td>
                                    <td style={{ padding: '14px 18px', textAlign: 'right' }}>1.0000</td>
                                    <td style={{ padding: '14px 18px', textAlign: 'right' }}>{backtestResult.finalNav.toFixed(4)}</td>
                                    <td style={{ padding: '14px 18px', textAlign: 'right', color: backtestResult.totalReturn >= 0 ? '#c41e3a' : '#006400' }}>
                                        {backtestResult.totalReturn >= 0 ? '+' : ''}{(backtestResult.totalReturn * 100).toFixed(2)}%
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                        <div style={{ marginTop: 16, display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 14 }}>
                            <div style={{ fontWeight: 500, color: '#666' }}>基准对比（多头）：</div>
                            {backtestResult.benchmarkReturns.map(b => (
                                <div key={b.name} style={{ color: b.totalReturn >= 0 ? '#c41e3a' : '#006400' }}>
                                    {b.name}：{b.totalReturn >= 0 ? '+' : ''}{(b.totalReturn * 100).toFixed(2)}%
                                </div>
                            ))}
                        </div>
                        <div style={{ marginTop: 16, fontSize: 13, color: '#999', lineHeight: 1.8 }}>
                            规则：多头区间启动日买入涨幅前{strategyParams.weights.length} ETF（{strategyParams.weights.map(w => `${w.toFixed(0)}%`).join('/')}），区间结束卖出；单日涨幅&gt;{strategyParams.bullStartSingleDay}%或两日累计&gt;{strategyParams.bullStartTwoDay}%启动多头；单日跌幅&lt;{strategyParams.bullEndSingleDay}%{strategyParams.bullEndUseMA10 ? '或跌破MA10' : ''}结束多头；{strategyParams.bearStartYear}年起空头区间持有银行 ETF；跨年收益计入开始年份。点击年份可查看当年每个波段的交易明细。
                        </div>
                    </>
                )}
            </Modal>

            <Modal
                title={(() => {
                    const yearResult = backtestResult?.yearResults.find(y => y.year === selectedYear);
                    if (!yearResult) return `${selectedYear}年 收益率曲线`;
                    const color = yearResult.annual_return >= 0 ? '#c41e3a' : '#006400';
                    return (
                        <span>
                            {selectedYear}年 收益率曲线
                            <span style={{ marginLeft: 16, fontSize: 15, color, fontWeight: 500 }}>
                                策略：{yearResult.annual_return >= 0 ? '+' : ''}{yearResult.annual_return.toFixed(2)}%
                                <span style={{ marginLeft: 8, fontSize: 13, color: '#c41e3a', fontWeight: 400 }}>
                                    (多头{yearResult.bull_return !== undefined ? `${yearResult.bull_return >= 0 ? '+' : ''}${yearResult.bull_return.toFixed(2)}%` : '—'}，空头{yearResult.bear_return !== undefined ? `${yearResult.bear_return >= 0 ? '+' : ''}${yearResult.bear_return.toFixed(2)}%` : '—'})
                                </span>
                            </span>
                            {backtestResult?.benchmarkReturns.map(b => {
                                const ba = b.annualReturns.find(a => a.year === selectedYear);
                                if (!ba) return null;
                                return (
                                    <span key={b.name} style={{ marginLeft: 12, fontSize: 14, color: ba.return >= 0 ? '#c41e3a' : '#006400' }}>
                                        {b.name}：{ba.return >= 0 ? '+' : ''}{ba.return.toFixed(2)}%
                                    </span>
                                );
                            })}
                        </span>
                    );
                })()}
                open={selectedYear !== null}
                onCancel={() => setSelectedYear(null)}
                footer={null}
                width="90%"
                style={{ top: '5%' }}
                bodyStyle={{ padding: '20px 28px', height: 'calc(90vh - 110px)', overflow: 'auto' }}
            >
                {selectedYear !== null && backtestResult && (
                    <BacktestChart result={backtestResult} year={selectedYear} amvData={data} rankingMethod={strategyParams.rankingMethod} />
                )}
            </Modal>
        </div >
    );
};

export default ActiveMarket;