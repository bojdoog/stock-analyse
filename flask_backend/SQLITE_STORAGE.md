# SQLite 数据存储

> 历史说明：项目默认存储已切换为 MySQL。当前配置、迁移和验证方法见
> [MySQL 存储说明](MYSQL_STORAGE.md)。以下内容用于显式设置 `DATABASE_PATH` 为 SQLite 文件路径时的兼容模式。

项目的数据主存储是 `flask_backend/instance/stock_analyse.sqlite3`。
Flask、抓取脚本及研究脚本共用 `DATABASE_PATH` 环境变量；未设置时均使用该绝对默认路径，不受工作目录影响。
`data/` 的 CSV/JSON 保留为备份和导出文件，接口不再依赖这些文件存在。
`back_test_data/` 的研究输入与报告不属于本次 `data/` 迁移范围，仍保留原格式。

## 表结构

| 表 | 内容及唯一键 |
| --- | --- |
| `indicators` | 指标定义，沿用原有 ID；代码唯一 |
| `indicator_daily` | 指标日值，`indicator_id + date` |
| `instruments` | 标的名称、分类、市场、代码及来源文件 |
| `daily_bars` | 个股、ETF、指数行情，`category + exchange + code + date` |
| `moneyflow_ind_dc` | 东财行业资金流向 |
| `moneyflow_ind_ths` | 同花顺行业资金流向 |
| `moneyflow_cnt_ths` | 同花顺概念资金流向 |
| `source_files` | 全部 CSV/JSON 原始字节、SHA256、行数、起止日期、导入时间 |
| `import_events` | 每次成功变更的来源文件、校验值、行数、时间 |

数据库日期统一为 `YYYY-MM-DD`，代码使用 TEXT 保留前导零。股票与指数 `000001` 使用不同市场和资产类别，不会冲突。
现有指数文件均为上交所指数；引入其他市场指数时须扩展 `instrument_identity` 的市场映射。
数值沿用源文件单位，不擅自转换资金流向金额的单位。缺失数值在库中保存为 NULL。
候选指标的 close 由反推公式计算。按用户指定补成合成 K 线：open 使用上一交易日 close（首日使用自身 close），
high/low 分别为 open 和 close 的最大/最小值；volume/amount 使用同日上证指数 `000001.SH`。
这些 high/low 不代表真实盘中高低价。成交量单位为手，成交额为千元，沿用 [Tushare 指数日线口径](https://tushare.pro/document/2?doc_id=95)。

资金流向唯一键为 `date + sector_key + occurrence`。原数据有 110 条同日同业的额外记录，其中 rank 等字段存在差异；迁移保留全部记录及顺序，不替用户决定删哪条。相同文件重复导入不会增加记录。
`source_files` 额外保留原始内容，便于无损导出及审计；这会增加数据库体积。

## 首次导入、重新导入及校验

在项目根目录运行：

```powershell
python flask_backend/migrate_market_data.py
python flask_backend/migrate_market_data.py --verify-only --report flask_backend/market_verify_report.json
```

可用 `--database` 指定目标 SQLite，`--data-dir` 指定待导入目录。
脚本只导入内容发生变化的文件，并按单个文件执行事务；出错会回滚该文件并以非零状态退出，之前成功的文件可在重跑时跳过。
对于手工导入，CSV 是对应文件的完整快照：修改后重新导入会替换该来源的旧记录。因此不要用过期 CSV 覆盖最新数据库。
校验逐文件比较原始字节、行数、日期和各字段值，并执行完整性与外键检查。

首次迁移结果见 `market_migration_report.json`：6,807 个文件，977,473 行。
迁移前原数据库已备份到 `instance/backups/before_market_migration_*.sqlite3`。

## 后续更新

- 现有 `fetch-data.ps1`、`run_all_fetch.py` 和各单独抓取脚本仍可使用。
- 统一入口 `fetch_data/` 接入共用 SQLite 写入层。
- 日线抓取按日期合并：保留旧历史，同日新数据覆盖旧值；空抓取不删除历史。
- 资金流向按日快照更新；缺失日期检查及 `index.json` 从数据库生成。
- `python back_test_data/amv_research/formula.py` 生成候选指标后，按库中上证指数补齐合成 OHLC、成交量和成交额，再入库并导出 `data/core_index/candidate_amv_close.csv`（沿用文件名，现包含全部七列）。生成前应先更新指数，缺少对应日量额时会报错，不跨日期填充。
- 指南针原始文件手动更新后，再执行迁移命令即可更新原始指标。
- SQLite 启用 WAL 和 60 秒锁等待；网络抓取在事务外执行，入库通过短事务串行写入。
- 后端已移除行情的永久内存缓存，写入完成后的下一次请求即可读取更新。

## API 兼容

原 `/api/amv`、`/api/kline/...`、`/api/sector-data`、`/api/moneyflow/...` 地址继续使用。
日期和条数过滤由 SQL 执行；三类资金流向响应仍使用原有 `YYYYMMDD` 日期格式。
为兼容原前端，资金流向 API 的部分展示字段仍将空值映射为 0；数据库原始字段保留 NULL，`net_inflow` 仍返回 null。
`/data/<目录>/<文件>` 和 CSV 下载接口从数据库中的原始快照提供内容，不再读取磁盘上的导出文件。

## 查看数据

用 SQLite 客户端打开上述数据库文件，即可查看各表。例如：

```sql
SELECT category, COUNT(*) AS rows FROM daily_bars GROUP BY category;
SELECT i.name, COUNT(*) AS rows, MIN(d.date), MAX(d.date)
FROM indicators i JOIN indicator_daily d ON d.indicator_id = i.id GROUP BY i.id;
SELECT * FROM indicator_daily
WHERE indicator_id = (SELECT id FROM indicators WHERE code = 'AMV_EMA20') ORDER BY date DESC LIMIT 10;
```

备份正在使用的数据库时使用 SQLite 的 backup API，避免只复制主文件而漏掉尚未归并的 WAL。

## 验证

```powershell
python -m unittest discover -s flask_backend/tests -v
python back_test_data/amv_research/verify_formula.py
```

测试覆盖无 CSV 目录读取、精度与 NULL、重复导入、失败回滚、资金流向重复记录、增量更新及代码隔离。
