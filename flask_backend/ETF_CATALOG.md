# ETF 品种统一管理

`etf_catalog` 是唯一运行时 ETF 清单；`etf_sector_mapping` 管理东财行业、同花顺行业和概念到 ETF 的映射。`instruments` / `daily_bars` 继续保存行情历史，不承担启用清单的职责。

- `GET /api/etf-types`：启用的 ETF，包含 code、name、exchange、ts_code、file、enabled、sort_order。
- `/api/list/etf`、`/api/lists`、`/api/sector-data`、活跃市值前端、ETF 抓取与 Python 回测读取同一张表。
- 资金流向接口和三个抓取脚本读取同一映射表；停用 ETF 的旧资金流向记录保留，但不再附带可选 ETF 映射。
- 停用不删除历史行情。重导 CSV 不会注册或重新启用 ETF。
- 显示名称和 source_path 分离，改名不需要搬迁行情文件。当前回测仍按名称匹配，因此禁止启用两个同名 ETF。

首次部署（已有清单时不会覆盖）：

```powershell
flask_backend/venv/Scripts/python.exe flask_backend/etf_catalog.py --bootstrap
```

初始化迁移文件 `migrations/etf_catalog_initial.json` 保留原28个代码，停用159381、159929、512010、512660、516160，启用23个。它只用于首次迁移，不是运行时清单。

后续管理：

```powershell
flask_backend/venv/Scripts/python.exe flask_backend/etf_catalog.py --disable 159381
flask_backend/venv/Scripts/python.exe flask_backend/etf_catalog.py --export etfs.json
# 编辑导出的 etfs / mappings 后导入，可新增、改名、调序、启用或停用。
flask_backend/venv/Scripts/python.exe flask_backend/etf_catalog.py --import-file etfs.json
```

默认 auto 模式将变更先存 SQLite，并通过现有持久队列同步 MySQL；MySQL 暂不可用时会稍后补写。配置快照保存在数据库的 `source_files` 中（`catalog/etfs.json`）。请通过上述命令修改，以保证两库和配置快照一致；直接改其中一个库不会自动同步。`--database` 仅用于独立库迁移或测试。

保留的历史研究快照不回写，避免改变既有研究结果；重新运行应用回测使用最新启用品种。
