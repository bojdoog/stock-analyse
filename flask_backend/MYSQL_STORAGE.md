# MySQL 数据存储

项目默认使用自动模式，优先读取本机 MySQL 8：`127.0.0.1:3306 / stock_analyse`。
Flask、两套抓取脚本和回测脚本共用 `market_store.py`，行情、指标与资金流向均从数据库读取。
每次抓取会更新 SQLite、CSV/JSON 导出副本，并同步 MySQL。
`instance/stock_analyse.sqlite3` 是持续更新的本地副本，不再只是旧迁移备份。

## 连接配置

安装 `flask_backend/requirements.txt`（独立抓取脚本使用各自的 requirements.txt）。
本机配置在 `flask_backend/instance/mysql.json`，该目录已被 Git 忽略。
其他电脑可创建如下文件并填写密码：

```json
{
  "host": "127.0.0.1",
  "port": 3306,
  "user": "root",
  "password": "填写本机密码",
  "database": "stock_analyse"
}
```

环境变量 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`
优先于 JSON；配置文件位置不受启动目录影响。`DATABASE_PATH` 未设置或设为 `auto` 时：

- 写入先将数据和待同步标记一起提交到 SQLite，然后导出 CSV/JSON，再同步 MySQL。
- 未安装 MySQL/PyMySQL、服务未启动、连接失败或账号无权登录时，继续用 SQLite 读写。
- 故障后每个进程有 30 秒重试间隔；后续读写请求会重试，并先补写待同步数据再恢复 MySQL 查询。
- 没有后台定时任务；恢复后需要有一次查询或写入触发补写。
- 数据校验、SQL 语法和约束错误会报告，不冒充网络故障。

`SQLITE_DATABASE_PATH` 可指定本地副本，默认 `instance/stock_analyse.sqlite3`。
`DATABASE_PATH=mysql` 是只用 MySQL 的显式维护模式；指定 SQLite 路径则只操作该文件。
日常运行不要设置这两种维护模式。正常启动仍使用项目原有启动脚本。
`/api/health` 返回实际使用的 `storage: mysql` 或 `sqlite` 和库名/文件路径，不返回凭据。

## 迁移与核对

从项目根目录执行（首次迁移时先停止抓取任务及后端）：

```powershell
python flask_backend/migrate_sqlite_to_mysql.py
```

脚本读取 SQLite 一致性快照，创建 MySQL 数据库及 9 张 InnoDB 表，保持指标 ID、
导入事件 ID、时间戳、空值、浮点精度、重复行业记录和原始文件字节。
复制操作在事务内完成，逐行逐字段核对通过后提交。已有数据的目标库会被拒绝覆盖。
源 SQLite 文件不会被修改或删除。核对报告在 `flask_backend/instance/mysql_migration_report.json`。

仅核对已经完成的迁移：

```powershell
python flask_backend/migrate_sqlite_to_mysql.py --verify-only
```

首次启用自动模式前，使用 `python flask_backend/sync_sqlite_backup.py` 将现有 MySQL
完整复制到 SQLite；脚本先备份原 SQLite，再在事务中复制和逐字段核对。
已有待同步数据时拒绝覆盖，必须先恢复 MySQL 完成补写。
日常同步按文件合并最新快照，两端导入事件和更新时间可能不同，但行情和原始文件内容应一致。
如果需要把 CSV/JSON 导入当前数据库，使用 `python flask_backend/migrate_market_data.py`；
此命令会更新对应文件的数据，和 SQLite 完整迁移脚本用途不同。

## 日常读写与测试

价格数据按日期合并，资金流向保留完整当日快照。SQLite 的 `mysql_pending` 表保存待补写文件，
同步成功后删除标记，重复补写不会重复插入行情。SQLite 写锁协调本地合并与导出，MySQL 使用命名锁。
`storage_sqlite.py` 保留旧模块名兼容导入，实际使用统一存储层的自动配置。
两端不是分布式原子事务；SQLite 提交后即使远端失败，数据仍保留且可重试。

反推研究下载器也会把 MCP JSON 和研究 CSV 以保留原始字节的方式归档到两库的
`source_files` 表（`research/` 分类），本地 CSV/JSON 同时保留；研究缓存读取优先使用自动模式。
反推公式读取归档的行业历史，更新后最终指标仍写入行情表。

```powershell
python -m unittest discover -s flask_backend/tests -v
$env:MYSQL_INTEGRATION_TESTS = '1'
python -m unittest discover -s flask_backend/tests -v
Remove-Item Env:MYSQL_INTEGRATION_TESTS
```

集成测试使用随机名称 `stock_test_*` 的临时数据库，测试结束自动删除，只操作测试库。
测试账号因此需要建库和删库权限。测试涵盖查询、搜索、分页、文件下载、事务回滚、
幂等导入、历史保留及并发抓取。

临时读取迁移时点的旧备份，可在启动进程之前设置：

```powershell
$env:DATABASE_PATH = 'C:\_allCode\stock_analyse\flask_backend\instance\stock_analyse.sqlite3'
```

此设置绕过自动同步。日常恢复自动模式时移除该变量或将其设为 `auto`。
