# Stock-Line 项目会话上下文

## 项目概况
- **项目路径**：`C:\_allCode\stock-line`
- **技术栈**：React + TypeScript + Vite + Ant Design + ECharts
- **核心功能**：活跃市值（0AMV）K线图 + 策略回测 + ETF 排名推荐
- **入口文件**：`src/pages/ActiveMarket/index.tsx`

## 数据目录结构
```
public/data/
├── etf/              # 27个ETF CSV文件（3MB）
├── index/            # 2个指数CSV（0.39MB）
├── moneyflow_ind_dc/ # 697个东财行业资金流向（2.56MB）
├── moneyflow_cnt_ths/ # 464个同花顺概念资金流向（4.05MB）
├── moneyflow_ind_ths/ # 454个同花顺行业资金流向（3.46MB）
└── stock/            # 个股数据
```

## 核心代码文件
| 文件 | 功能 |
|------|------|
| `src/pages/ActiveMarket/index.tsx` | 主页面，状态管理、数据加载 |
| `src/pages/ActiveMarket/utils/backtest.ts` | **核心回测逻辑**（多头区间识别、排名、收益计算） |
| `src/pages/ActiveMarket/components/KLineChart.tsx` | K线图组件（支持多图联动） |
| `src/pages/ActiveMarket/components/BacktestChart.tsx` | 回测结果展示 |
| `tools/fetch_moneyflow_ind_dc.py` | 东财行业资金流向拉取 |
| `tools/fetch_moneyflow_cnt_ths.py` | 同花顺概念资金流向拉取 |
| `tools/fetch_moneyflow_ind_ths.py` | 同花顺行业资金流向拉取 |
| `tools/run_all_fetch.py` | 一键批量拉取所有数据 |

## 排名方式（4种）
1. `etf_gain` - ETF涨幅排名（启动日涨幅）
2. `ths_moneyflow` - 同花顺板块流入
3. `ths_concept` - 同花顺概念流入
4. `dc_moneyflow` - 东财板块流入

## 近期完成的修改

### 1. 多头区间持仓展示修复
- **问题**：资金流向为0或NaN时被当成有效数据，挤掉真实排名
- **修复**：`parseFloat` 解析保留 NaN，排名逻辑过滤 NaN

### 2. 三层兜底机制（backtest.ts 第793-890行）
当排名靠前的 ETF 在区间内无价格数据时：
1. **主排名**：按排名顺序尝试，跳过无数据 ETF
2. **替补池**：从同一次排名的后续候选补，权重按实际位置分配
3. **ETF 涨幅兜底**：用启动日 ETF 涨幅排名兜底

### 3. 板块指数兜底
当 ETF 无数据但资金流向有板块指数收盘价时，用板块指数涨跌计算收益：
```typescript
// 如果ETF数据缺失，尝试用板块指数收盘价
if (!data && item.industry_name) {
  startClose = getSectorClose(item.industry_name, startDate);
  endClose = getSectorClose(item.industry_name, endDate);
}
```

### 4. 展示格式动态判断
- 根据 `industry_name` 是否存在决定展示格式
- 有 → 显示板块名 + 资金流入 + 亿 + ETF类型
- 无 → 显示ETF名 + 启动涨幅 + %

### 5. 至今涨跌幅（KLineChart.tsx）
- 计算方式：`(最后一天收盘价 - 悬停日收盘价) / 悬停日收盘价`
- 只在上方独立副图中显示

### 6. 策略参数联动主图
主图多头区间识别现在跟随策略参数（`bullStartSingleDay`、`bullStartTwoDay`、`bullEndSingleDay`、`bullEndUseMA10`）

### 7. 年度明细新增多头/空头收益率
`BacktestYearResult` 新增 `bull_return`、`bear_return` 字段

## 当前技术状态
- ✅ TypeScript 编译无错误
- ✅ 权重分配逻辑正确（顶替者拿到正确位置的权重）
- ✅ 东财数据缺失时正确回退到 ETF 涨幅排名

## 待解决问题：数据加载性能

### 问题
前端加载 1644 个文件（13.46MB），其中 1615 个是资金流向 CSV，每个都要单独 HTTP 请求。

### 优化方案（已评估）

#### 方案1：前端文件合并（零架构改动）
- 合并 CSV 成少量 JSON 文件
- 请求数：1615 → 3~5
- 优点：不改架构
- 缺点：文件可能很大
- 推荐指数：⭐⭐⭐

#### 方案2：前端按需加载 + 缓存
- 根据年份范围只加载需要的日期
- 加 localStorage 缓存
- 优点：改动小
- 缺点：首次仍慢
- 推荐指数：⭐⭐⭐

#### 方案3：轻量 Node.js/Python 后端（推荐）
- 资金流向走后端 API
- ETF/Index 仍前端加载
- 架构：前端 → /api/moneyflow → 后端读 CSV → 返回 JSON
- 请求数：1644 → 30
- 优点：效果最好
- 缺点：需要部署后端
- 推荐指数：⭐⭐⭐⭐⭐

#### 方案4：Serverless 函数
- 无服务器后端
- 优点：不用维护服务器
- 缺点：冷启动
- 推荐指数：⭐⭐⭐⭐

#### 方案5：SQLite + 后端
- 数据库存储
- 优点：查询灵活
- 缺点：改动大
- 推荐指数：⭐⭐⭐

#### 方案6：预计算 JSON
- 构建时预计算常用数据
- 优点：前端零计算
- 缺点：需要定期重算
- 推荐指数：⭐⭐⭐⭐

### 推荐组合
**方案3（轻量后端）+ 方案2（ETF/Index 缓存）**
- 资金流向：后端 API 1 次请求
- ETF/Index：前端加载 + localStorage 缓存
- 总请求数：1644 → ~30

## ETF 映射关系
```typescript
const ETF_TO_INDUSTRY = {
  '游戏ETF': ['游戏'],
  '软件ETF': ['互联网服务', '软件开发', '算力概念', '数据要素', '云计算', '区块链', '数字货币', '网络安全'],
  '半导体ETF': ['半导体', '半导体概念', '芯片概念', '汽车芯片', '存储芯片', '国产芯片'],
  '有色ETF': ['能源金属', '小金属', '贵金属', '有色金属'],
  // ... 共26个ETF映射
};
```

## 特殊规则
- 银行 ETF 永远排在最后（空头区间持有）
- 权重总和必须为 100%
- 跨年收益计入开始年份
- 东财数据起始于 2023-09
- 同花顺数据起始于 2024-09

## 快速启动
```powershell
# 安装依赖
npm install

# 开发
npm run dev

# 拉取数据
python tools/run_all_fetch.py

# 构建
npm run build
```

## 注意事项
- 东财/同花顺资金流向数据起始日期不同，2023年之前的多头区间会回退到 ETF 涨幅排名
- CSV 文件必须包含 `index.json` 才能被前端加载
- `fetch_moneyflow_ind_dc.py` 修改后需要用 `--check-missing` 补全数据