# stock-line

A股策略回测与资金流向分析工具。

## 功能

- **活跃市值 K 线图** — 展示 0AMV 活跃市值走势，支持叠加指数/ETF
- **多空区间识别** — 基于涨跌幅和 MA10 自动识别多头/空头区间
- **策略回测** — 支持多种买入排名方式（ETF 涨幅、同花顺板块/概念流入、东财板块流入），可调参数（启动阈值、结束条件、ETF 权重）
- **最佳权重计算** — 等权、收益加权、增长最优、夏普最优
- **资金流向分析** — 东财行业资金流向（2023年起）、同花顺行业/概念资金流向（2024年起）

## 技术栈

- React + TypeScript + Umi Max
- ECharts（K 线图）
- Ant Design（UI 组件）
- Tushare Pro（数据接口）

## 快速开始

```bash
# 安装依赖
pnpm install

# 开发模式
pnpm dev

# 构建
pnpm build
```

## 数据拉取

数据通过 Tushare Pro 接口获取，需配置 token（已内置在脚本中）。

```bash
# 统一拉取所有数据
python tools/run_all_fetch.py

# 单独拉取
python tools/fetch_etf.py                    # ETF 行情
python tools/fetch_index.py                  # 指数行情
python tools/fetch_moneyflow_ind_dc.py       # 东财行业资金流向
python tools/fetch_moneyflow_cnt_ths.py      # 同花顺概念资金流向
python tools/fetch_moneyflow_ind_ths.py      # 同花顺行业资金流向
```

## 数据目录

| 目录 | 内容 | 来源 |
|------|------|------|
| `public/data/etf/` | ETF 日 K 线 | Tushare |
| `public/data/index/` | 指数日 K 线 | Tushare |
| `public/data/stock/` | 个股日 K 线 | Tushare |
| `public/data/moneyflow_ind_dc/` | 东财行业资金流向 | `moneyflow_ind_dc` |
| `public/data/moneyflow_cnt_ths/` | 同花顺概念资金流向 | `moneyflow_cnt_ths` |
| `public/data/moneyflow_ind_ths/` | 同花顺行业资金流向 | `moneyflow_ind_ths` |