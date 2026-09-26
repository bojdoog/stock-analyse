# 数据拉取脚本

从项目根目录运行，也可双击根目录的 `fetch-data.bat`。

```powershell
python fetch_data/run_all_fetch.py
python fetch_data/fetch_kline.py --help
python fetch_data/fetch_one.py 000001
python fetch_data/download_amv_research.py
python fetch_data/update_latest.py --help
```

`run_all_fetch.py` 统一执行项目使用的 ETF、指数、三类资金流向和活跃市值推导原始数据拉取，不拉取个股日线。研究数据从 2024-09-10 拉到当天。个股脚本仅保留供手动使用。

统一流程首先调用 `fetch_compass_amv_daily.py`，读取 `C:\Compass\WavMain\ANALYSE\Data\ChinaStk\Z_SK\day.vdat`，校验块索引、日期及 OHLC 后，向 `data/core_index/0AMV-2013-2026.csv` 和共用数据库增量写入新日期。已有日期保留原值，重叠日期 OHLC 不一致时停止写入；成交量/额差异记录到报告。写入前自动备份 CSV 到 `back_test_data/compass_amv_cache/`。运行前正常退出指南针，释放文件锁；数据截止日期取决于软件已缓存的行情，不会联网补齐指南针缓存。可用 `python fetch_data/fetch_compass_amv_daily.py --check-only` 只检查不更新日线。

随后调用 `parse_compass_amv_cache.py`，只读解析 `C:\Compass\WavMain\Temp` 中的 `Z_SK0AMV*.fde`，输出分时 CSV 到 `back_test_data/compass_amv_cache/`。分时数据不用于合成日线，其成交量、成交额字段口径尚待确认。任一步骤失败时，后续拉取仍继续，最终统一入口返回失败状态。

研究数据包括同花顺行业量价、换手率、流通/总市值、行业资金流、行业目录及成分快照、沪深市场每日统计、大盘资金流和交易日历，同时保留本地原始 AMV 及行业数据参考副本。原始 AMV 副本仅覆盖现有文件日期，不会生成新的原始观测值。

研究下载支持 `--start YYYYMMDD --end YYYYMMDD`。历史成功请求复用缓存，当天数据和行业/成分快照重新获取。失败请求写入报告，并让统一入口返回失败状态。`update_latest.py` 是推导结果更新工具，仍按需单独运行。

行情仍写入项目根目录的 `data/` 及现有数据库，研究数据仍写入 `back_test_data/`。`stocklist.csv` 为股票池，`storage_sqlite.py` 对接后端共用存储层。

原 `flask_backend/utils/fetch_data/`、`stock-line/tools/` 中的重复拉取脚本已统一到本目录。
# 活跃市值分时入库

`python fetch_data/import_compass_amv_intraday.py` 将 `data/core_index/0AMV-intraday/YYYY-MM-DD.csv` 写入共用 SQLite 和 MySQL 的 `indicator_intraday` 表。唯一键为 `(indicator_id, date, time)`，`indicator_id` 对应 `indicators.code='0AMV'`。字段保留 `amv`、`volume_candidate`、`amount_candidate` 和原始缓存文件名；量额字段的含义及单位仍未核实。

原始 CSV 字节保存在 `source_files`，SQLite 待同步队列支持失败后重跑；相同文件重复导入不新增记录。脚本逐日核对双库所有分时值和归档字节，结果写入输出目录的 `database_import_report.json`。此命令只导入已有 CSV；新增缓存需先运行 `python fetch_data/parse_compass_amv_cache.py --split-by-date --output data/core_index/0AMV-intraday`。
