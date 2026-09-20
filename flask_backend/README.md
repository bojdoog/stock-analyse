# Flask 后端服务

股票分析系统的 Flask 后端 API 服务，提供数据访问接口和前端静态文件托管。

## 目录结构

```
flask_backend/
├── app.py                  # Flask 主入口
├── config.py               # 配置文件
├── requirements.txt        # Python 依赖
├── start.bat               # Windows 启动脚本
├── routes/
│   └── api.py              # API 路由
├── services/
│   └── data_service.py     # 数据服务层
└── utils/
    └── csv_parser.py       # CSV 解析工具
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
cd flask_backend
python -m venv venv

# Windows
venv\Scripts\activate.bat

# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动服务

**方式一：使用启动脚本（Windows）**
```bash
start.bat
```

**方式二：命令行启动**
```bash
# Windows
set FLASK_DEBUG=true
python app.py
```

### 3. 访问服务

- API 服务：http://localhost:5000
- 健康检查：http://localhost:5000/api/health
- 数据文件：http://localhost:5000/data/stock/000001.csv

## API 接口

### 指标管理

默认优先使用本机 MySQL 的 `stock_analyse` 数据库，连接或登录失败时自动使用 SQLite。
每次抓取同步更新 SQLite、CSV 和 MySQL；离线期间的更新会在恢复连接后补写。默认指标为
`0AMV / 活跃市值(默认)`。连接配置放在被 Git 忽略的 `instance/mysql.json`，
也可通过 `MYSQL_*` 环境变量设置。首次运行先按 [MySQL 存储说明](MYSQL_STORAGE.md)
配置连接并执行迁移。指标定义、指标日值、个股/ETF/指数行情和三类资金流向均存于 MySQL；
`data/` 的 CSV/JSON 和 SQLite 文件均持续更新，详见上述自动同步说明。

`GET /api/indicators` 返回数据库中的指标列表，支持：

- `current`：页码，默认 1。
- `pageSize`：每页数量，默认 10，范围 1–100。
- `name`、`code`：名称、代码的包含匹配，可组合查询。

响应包含 `code`、`success`、`data`、`total`、`current`、`pageSize`；
`data` 中包含指标 ID、代码、名称、来源、说明、默认标识及创建/更新时间。
前端菜单“指标管理”使用 ProTable 请求此接口，支持搜索、分页和刷新。

`GET /api/indicators/<id>/data` 按指标返回日值，支持 `start_date`、`end_date`、`limit`。
`meta.close_only=true` 表示仅有收盘值，前端绘制折线，其他 OHLC/成交量字段为 `null`。
导入候选公式后，列表包含 `AMV_EMA20 / 活跃市值(反推EMA20)`。

运行接口与持久化验证：在项目根目录执行
`python -m unittest discover -s flask_backend/tests -v`。

### 基础接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/categories` | GET | 获取数据分类列表 |
| `/api/lists` | GET | 获取所有数据列表 |

### K 线数据接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/kline/<category>/<code>` | GET | 获取 K 线数据（JSON） |
| `/api/kline/<category>/<code>/csv` | GET | 获取 K 线数据（CSV） |
| `/api/list/<category>` | GET | 获取分类文件列表 |

**category 可选值**: `stock`（个股）、`etf`（ETF）、`index`（指数）

**Query 参数**:
- `start_date`: 开始日期，格式 `YYYY-MM-DD`
- `end_date`: 结束日期
- `limit`: 限制返回条数

### 特殊数据接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/amv` | GET | 活跃市值数据 |
| `/api/moneyflow/<type>` | GET | 资金流向数据 |
| `/api/moneyflow/<type>/files` | GET | 资金流向文件列表 |
| `/api/moneyflow/<type>/file/<filename>` | GET | 单个资金流向文件 |

**flow_type 可选值**:
- `ind_dc`: 东财行业资金流向
- `cnt_ths`: 同花顺概念资金流向
- `ind_ths`: 同花顺行业资金流向

### 静态文件访问

直接通过 `/data/` 路径访问 CSV 文件，兼容前端 `fetch('/data/...')` 请求：

```
GET /data/stock/000001.csv
GET /data/etf/510050_上证50ETF.csv
GET /data/index/000001_上证指数.csv
GET /data/core_index/0AMV-2013-2026.csv
GET /data/core_index/candidate_amv_close.csv
```

## 生产部署

### 方式一：直接托管前端（推荐）

1. 构建前端：`cd stock-line && npm run build`
2. 启动后端：`cd flask_backend && python app.py`
3. Flask 会自动托管 `stock-line/dist` 下的前端文件

### 方式二：前后端分离

- 前端开发：`cd stock-line && npm run dev`（默认端口 8000）
- 后端 API：`cd flask_backend && python app.py`（默认端口 5000）
- 前端通过 `/api/` 访问后端，开发时需配置代理

## 配置说明

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FLASK_HOST` | `0.0.0.0` | 监听地址 |
| `FLASK_PORT` | `5000` | 监听端口 |
| `FLASK_DEBUG` | `true` | 调试模式 |
| `SECRET_KEY` | 自动生成 | 密钥 |
| `CORS_ORIGINS` | `*` | CORS 允许的来源 |
