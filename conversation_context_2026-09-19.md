# 活跃市值项目：对话上下文与工作交接

整理日期：2026-09-19（Asia/Shanghai）。

这是本次对话的结构化上下文摘要，便于新对话继续工作，不是逐字聊天记录。已省略 API token、鉴权地址中的凭证及其他敏感信息。本文记录事实和建议，后续行动仍以用户的新请求为准。

## 1. 项目位置与目标

- 项目根目录：`C:\_allCode\stock_analyse`
- 前端：`stock-line`，React / Umi Max / Ant Design / Ant Design Pro Components / ECharts。
- 后端：`flask_backend`，Flask，通常使用端口 5000；前端开发代理将 `/api/` 转发至该端口。
- 原始行情和资金流数据：`data` 下的 CSV。
- 研究下载数据与第一轮反推结果：`back_test_data`。
- 当前新增的 SQLite 只存指标定义，行情和研究数据仍保存在 CSV。

用户的项目以指南针活跃市值（0AMV）划分市场多空状态，并在多头阶段选择强势 ETF，防守阶段按配置持有银行 ETF。

用户希望反推 0AMV，原因有三点：

1. 担心指标未来不再免费提供，希望能够独立计算。
2. 用户观察到部分科技板块（以半导体为代表）显著上涨，而 AMV 反应较弱，希望理解指标机制和背离原因。
3. 在理解原指标的基础上研究改进公式及策略。

区分两个目标：复现原指标与开发更好的策略指标。拟合很接近不代表找到专有原公式，也不代表策略有效或主力资金确实进出。

## 2. 原策略实现与初步审阅

主要代码：

- `stock-line/src/pages/ActiveMarket/utils/backtest.ts`
- `stock-line/src/pages/ActiveMarket/index.tsx`
- `stock-line/src/pages/ActiveMarket/components/KLineChart.tsx`
- `flask_backend/services/data_service.py`

当前默认逻辑：

| 环节 | 行为 |
|---|---|
| 多头启动 | AMV 单日涨幅 >4%，或连续两日都上涨且日涨幅之和 >4%；默认还要求收盘高于 MA10 |
| 选 ETF | 启动日按 ETF 当日涨幅排名，排除银行 ETF，买前五名 |
| 权重 | 30%、30%、20%、10%、10% |
| 区间持仓 | 维持选出的这组标的，不每日重新排序换股 |
| 多头结束 | AMV 单日涨幅 <-2.3%，或收盘低于 MA10 |
| 防守 | 默认从 2024 年开始转持银行 ETF，之前防守期不持仓 |

支持的其他排名方式：同花顺行业、同花顺概念、东财行业资金流。

初步读代码发现、尚未在本次工作中修复的问题：

- 总收益按区间持仓收益加权，每日净值却每日使用初始固定权重，等价于不同的再平衡假设，可能导致收益与回撤口径不一致。
- 收盘信号和排名确认后仍按同日收盘价交易，尚未明确可成交时点；没有手续费、滑点。
- 跨年持仓的整段收益记在开仓年份，而非按年末市值切分。
- 页面上的基准 ETF 收益只计算多头区间，不是整个期间买入持有收益。
- 最优权重是在当前回测区间上优化后再评价同一区间，属于样本内优化。

不要把本次反推研究当成上述回测问题已经修复。

## 3. Tushare MCP 连接状态

用户有 6000 积分，并提供了包含 token 的 Tushare MCP 地址。凭证不在本文中复述。

- MCP 协议握手成功，服务标识 `tushare`。
- `tools/list` 实际返回 254 个工具。
- 调用方式：Python / PowerShell 向 MCP 服务发送 JSON-RPC，读取 SSE 或 JSON 返回。
- 当前没有将其注册成会话内的原生 Tushare 工具；直接通过 MCP 协议已经成功取数和完成批量下载。
- `daily_basic` 已实际查询成功；`ths_daily`、`daily_info`、`moneyflow_mkt_dc` 等已经批量成功调用。
- 沙箱内 HTTPS 曾失败，联网命令使用获准的沙箱外执行；不能把 SSL 错误误判为积分不足。
- 下载脚本优先读取环境变量 `TUSHARE_TOKEN`，未配置时从项目现有 `flask_backend/utils/fetch_data/fetch_etf.py` 的配置读取。不要输出其中 token。
- 6000 积分不是所有数据权限。积分是访问门槛，不是每次调用扣减余额；分钟及部分特殊数据可能需独立权限。

主要已发现的接口：

`daily`、`daily_basic`、`adj_factor`、`stock_basic`、`trade_cal`、`ths_index`、`ths_daily`、`ths_member`、`moneyflow_ind_ths`、`moneyflow_mkt_dc`、`daily_info`、`sz_daily_info`、`index_dailybasic`、`moneyflow`、`stk_mins` 等。

## 4. 数据下载：已完成

用户明确要求先下载板块和市场汇总数据，并分文件夹放到：

`C:\_allCode\stock_analyse\back_test_data`

时间范围：2024-09-10 至 2026-09-11，共 486 个交易日。用户顾虑五千多只个股数据量大，因此本轮没有下载全市场个股历史。

| 目录 | 内容与数量 |
|---|---|
| `amv` | 原始 AMV 完整副本与研究区间 486 行 |
| `ths_daily` | 90 个行业 × 486 日 = 43,740 行；逐行业 CSV 及 `all_industries.csv` |
| `moneyflow_ind_ths` | 未按 ETF 映射筛选的行业资金流，43,560 行，484 日 |
| `daily_info` | 市场交易统计，5,784 行，486 日 |
| `sz_daily_info` | 深圳补充统计，6,764 行，485 日 |
| `moneyflow_mkt_dc` | 大盘资金流，486 行，486 日 |
| `ths_index` | 完整行业目录快照及 90 行业研究目录 |
| `ths_member` | 90 行业成分快照，5,578 行 |
| `trade_cal` | SSE、SZSE 交易日历 |
| `local_industry_reference` | 项目原有 74 行业资金流的 484 份 CSV 副本 |
| `metadata` | MCP 工具定义、研究行业代码集合 |
| `raw` | 各查询的参数、抓取时间、原始响应及解析记录；无 token |
| `supplemental_classifications` | 初次目录查询涉及的其他分类数据，仅供参考，不并入主要 90 行业 |
| `quality` | 数据检查文字说明和资金字段算术异常明细 |

为什么新增数据有 90 行业而原项目只有 74：原采集脚本会过滤没有 ETF 映射的行业。本次保留源接口的完整 90 行业。

`ths_index(type=I)` 返回 777 条，包含多套重叠行业分类。主研究代码集合来自历史行业资金流及本地数据的并集，不将全部 777 条直接相加。

脚本和说明：

- `back_test_data/download_amv_research.py`：MCP 下载，可复用成功请求缓存续跑。
- `back_test_data/verify_download.py`：离线覆盖和字段验证。
- `back_test_data/README.md`
- `back_test_data/DATA_DICTIONARY.md`
- `back_test_data/download_manifest.json`
- `back_test_data/quality_report.json`
- `back_test_data/quality/README.md`

### 已确认的数据问题

1. 行业资金流缺 2024-11-04、2025-01-20，单日补查仍空。
2. 2024-09-10 至 2024-09-27 共 12 个交易日，行业资金三个字段全部为零；不能当成真实“无资金活动”。
3. 2024-09-30 全部 90 行行业资金流存在买入−卖出与净额的算术异常；已输出明细，不擅自修复小数点。
4. 深圳统计缺 2024-11-12；`vol`、`total_share`、`float_share` 全为空。
5. 当前行业成分快照的纳入/剔除日期全空，无法当作历史成分。
6. 成分快照有 5,578 条、5,558 个唯一股票代码，包含北交所及跨行业重复，不能假定严格互斥或与指南针市场范围完全相同。
7. 行业行情核心数值字段完整，唯一键、日期×行业网格、OHLC 及非负量等检查通过。
8. 原 AMV 文件名为 `0AMV-2013-2026.csv`，内容首条实际上为 1993-01-03，末条为 2026-09-11；本轮仅用近两年交集。

### 单位与字段陷阱

- `ths_daily.float_mv/total_mv`：元；`turnover_rate`：百分数；`vol`：手。
- `moneyflow_ind_ths.close` 是行业指数，`close_price` 是领涨股股价，不要混用。
- `moneyflow_ind_ths` 金额文档标注亿元，但存在上述异常，不能未经核验直接使用总量。
- `daily_info` 市值、成交额为亿元，股本和成交量为亿股；总计与子市场不可重复相加。
- `sz_daily_info` 官方字段表未明确单位，本次保留原值。
- `moneyflow_mkt_dc` 金额为元，`buy_elg_amount` 等实际是分档净额，可为负。
- 原 AMV 数值尺度的单位没有核实，不直接认定为亿元。

## 5. 指标管理页面：已完成

用户要求新增“指标管理”菜单，用 Ant Design Pro 的 ProTable 显示数据库接口返回的指标列表，并将原活跃市值中文名设为 `活跃市值(默认)`。

实现：

- 菜单 `/indicators`，组件 `stock-line/src/pages/IndicatorManagement/index.tsx`。
- 使用 ProTable，支持名称/代码搜索、分页、刷新、加载失败提示和重试。
- 服务封装：`stock-line/src/services/indicators.ts`。
- SQLite 数据库：`flask_backend/instance/stock_analyse.sqlite3`。
- 数据库初始化：`flask_backend/database.py`；应用启动建表并幂等写入默认记录。
- 表名：`indicators`。
- 默认记录：`code=0AMV`、`name=活跃市值(默认)`、`source=指南针`、`is_default=true`。
- 字段：`id, code, name, source, description, is_default, created_at, updated_at`。
- API：`GET /api/indicators`，路由文件 `flask_backend/routes/indicators.py`。
- 参数：`current` 默认 1；`pageSize` 默认 10，范围 1–100；`name/code` 为包含匹配。
- 响应：`code, message, success, data, total, current, pageSize`。
- `DATABASE_PATH` 环境变量可覆盖数据库路径，默认放后端 instance 目录。
- 原菜单和 ActiveMarket 标题也已改为“活跃市值(默认)”。

目前只有列表功能，没有新增/编辑/删除接口。没有将候选反推指标自动注册进数据库。用户没有要求把研究 CSV 导入 SQLite。

验证情况：

- `python -m unittest discover -s flask_backend/tests -v`：3 项通过，覆盖默认初始化幂等、持久化、搜索分页、输入校验。
- `npm run build`：通过。
- `node node_modules/typescript/bin/tsc --noEmit`：通过。
- 实际浏览器验证菜单、数据库记录显示、搜索无结果和重置恢复正常。

浏览器当时打开 `http://127.0.0.1:5000/#/indicators`。当时为预览启动的 Flask 会话编号为 25789（该运行状态可能随会话变化，继续工作时先检查端口，不要假定仍在运行）。

## 6. 第一轮 AMV 反推：已完成

用户明确要求用 `back_test_data` 中数据反推原始活跃市值，文件现位于 `data/core_index/0AMV-2013-2026.csv`。

研究脚本：`back_test_data/research_amv.py`。
结果目录：`back_test_data/amv_research`。

使用 90 行业近两年数据比较 106 个候选，分 8 类：

1. 流通市值；
2. 当天市场成交额；
3. 市场成交额 EMA；
4. 换手市值 EMA；
5. 平滑换手量代理后按现价重估；
6. 滚动换手饱和模型；
7. 活跃筹码衰减递推；
8. 换手弹性模型。

### 时间划分

| 区间 | 日期 | 交易日数 | 用途 |
|---|---|---:|---|
| 预热 | 2024-09-10～2024-12-09 | 58 | 平滑初始化，不计入训练指标 |
| 训练 | 2024-12-10～2025-06-30 | 133 | 系数和部分参数拟合 |
| 验证 | 2025-07-01～2025-12-31 | 126 | 按对数 RMSE 选模型 |
| 测试 | 2026-01-05～2026-09-11 | 169 | 报告样本外表现 |

测试期已经看过，后续不能在这段数据上继续调参后仍称其为全新盲测。可采用滚动验证或新增留出样本。

### 验证期选出的固定公式

模型标识：`revalued_turnover_ema_20`。

```text
M[i,t] = float_mv[i,t] / 1e8        # 行业流通市值，亿元
h[i,t] = turnover_rate[i,t] / 100  # 换手率，小数
P[i,t] = close[i,t]                # 行业指数收盘点位
q[i,t] = M[i,t] * h[i,t] / P[i,t]  # 换手量代理，不是真实股数

alpha = 2 / 21
Q[i,0] = q[i,0]
Q[i,t] = alpha*q[i,t] + (1-alpha)*Q[i,t-1]

AMV_hat[t] = 7.695442042177039 * sum(P[i,t] * Q[i,t])
```

EMA 对应 Pandas `ewm(span=20, adjust=False)`。
比例系数仅用训练期的对数误差拟合，不是已知商业算法常数。
固定实现需要从 2024-09-10 开始的历史输入，以保持初始化一致；续算可以保留完整历史或 EMA 状态。

公式仅使用独立 THS 数据，不读取原 AMV 的昨日值、volume 或 amount。没有生成伪造的 OHLC，只输出估算 close。

### 结果

| 指标 | 训练 | 验证 | 测试 |
|---|---:|---:|---:|
| 数值 MAPE | 4.8934% | 2.0525% | 3.3919% |
| 数值 R² | 0.6539 | 0.9737 | 0.8799 |
| 日涨跌幅相关 | 0.9799 | 0.9569 | 0.9695 |
| 日涨跌幅平均绝对误差 | 0.4165 个百分点 | 0.3713 个百分点 | 0.4159 个百分点 |
| 日涨跌方向一致率 | 95.49% | 96.03% | 95.86% |

测试期最大数值相对误差 8.01%。
2026-09-11：原值 172364.30，估算值 162709.55，偏低 5.60%。

对照：成交额 EMA20 测试 MAPE 4.60%、日涨跌相关 0.571；市场流通市值测试 MAPE 26.62%。某些候选日涨跌相关更高，但数值误差更大，因此没有按单一相关系数宣称找到原公式。

### 现有策略信号对照

按默认 4%、两日相加 4%、-2.3%、MA10 规则，连续生成状态后分区间统计：

- 测试期多空状态一致率 85.80%。
- 原指标启动 5 次，候选启动 4 次，3 次同日启动；启动召回率 60%。
- 原指标退出 5 次，候选退出 4 次，2 次同日退出。
- 验证期没有新启动信号，其状态一致率 99.21% 不能用于宣称启动识别能力。

结论：找到了较接近、可独立运行的替代公式，**尚未识别原公式，不能无差别替换现有交易阈值**。也没有做收益验证或宣称盈利能力。

### 解释与局限

候选支持“近期参与交易的量经过平滑后按当前价格估值”的机制解释；成交转弱时即使部分板块上涨，合计指标也可能不涨。
这是候选机制，不证明“主力没有进场”，也没有对用户描述的某段科技行情做因果归因。

下一步可能的误差来源：

- 指南针的股票范围与 THS 行业池不同，尤其北交所、重复成分和历史成分未知。
- 个股换手和价格聚合为板块后丢失细节。
- 自由流通股、长期不交易筹码、除权处理、平滑参数未知。
- 历史数据可能经供应商修订，缺少当时快照。
- 只有两年左右有效样本，跨市场阶段证据不足。

资金流仅用于全样本探索性相关诊断，没有作为最终公式输入；异常与缺失未补零纳入相关计算。

### 研究产物

`back_test_data/amv_research` 中：

- `README.md`：完整中文研究报告与口径说明。
- `comparison.png`：原值/估算值、相对误差、日涨跌幅图；绿色区域是测试期。
- `formula.py`：冻结参数的独立公式实现，不读取 AMV。
- `data/core_index/candidate_amv_close.csv`（已移至项目根目录下的 `data/core_index`）：486 日估算 close。
- `daily_comparison.csv`：原值、各候选、误差、时间分组。
- `results.json`：参数、分组及模型成绩。
- `all_candidate_metrics.csv`：全部 106 候选成绩。
- `selected_family_metrics.csv`：每类按验证期选出的代表模型。
- `signal_metrics.csv`：交易信号对照。
- `largest_test_errors.csv`：测试误差最大日期。
- `diagnostic_correlations.csv`：全样本探索性相关，不是样本外成绩。
- `verify_formula.py` / `formula_checks.json`：计算一致性与因果性检查。

已通过三项检查：独立实现与研究结果一致；追加未来数据不改变历史输出；行业指数固定基点缩放不改变结果。

复现命令（项目根目录）：

```powershell
python back_test_data/research_amv.py
python back_test_data/amv_research/formula.py
python back_test_data/amv_research/verify_formula.py
```

所用 Python 环境已有 numpy、pandas、scipy、sklearn、matplotlib、requests。

## 7. 后续工作边界

- 用户最新请求是导出对话上下文；本文件即交付物。
- 暂未获用户新的具体要求来改进公式、补拉个股或将候选接入 UI。
- 可以建议下一步核对股票范围及个股聚合口径，或补充更早板块历史做跨阶段验证；建议不等于已经执行。
- 如用户要求加入候选指标，应保留原 `0AMV / 活跃市值(默认)`，区分候选名称和来源，不把候选标成原指标。
- 原工作区已有大量用户未提交修改，包括行情、回测、页面和后端文件。不得整体重置或覆盖这些更改；本次只按任务做局部修改。
- 本次未提交 Git commit、未创建 PR、未部署到外部服务器。

## 8. 已核对过的公开资料

- 指南针对 0AMV 的公开说明：https://www.compass.cn/shownews.php?nid=1976015
- 指南针活筹流通盘说明：https://www.compass.cn/help/wuji/4-1-3.html
- Tushare MCP：https://tushare.pro/document/1?doc_id=463
- 积分与频次：https://tushare.pro/document/1?doc_id=290
- 每日指标：https://tushare.pro/document/2?doc_id=32
- 板块行情：https://tushare.pro/document/2?doc_id=260
- 行业资金流：https://tushare.pro/document/2?doc_id=343
- 市场统计：https://tushare.pro/document/2?doc_id=215
- 深圳统计：https://tushare.pro/document/2?doc_id=268
- 大盘资金流：https://tushare.pro/document/2?doc_id=345

公开资料提供原理线索和字段说明，没有确认上述候选就是指南针原公式。接口及权限可能变化，必要时重新核对。
