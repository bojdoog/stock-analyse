# 数据拉取脚本

从项目根目录运行，也可双击根目录的 `fetch-data.bat`。

```powershell
python fetch_data/run_all_fetch.py
python fetch_data/fetch_kline.py --help
python fetch_data/fetch_one.py 000001
python fetch_data/download_amv_research.py
python fetch_data/update_latest.py --help
```

`run_all_fetch.py` 统一执行 ETF、指数、三类资金流向、活跃市值推导原始数据和股票池日线拉取。股票日线从 2013-01-04 拉到当天，覆盖 `stocklist.csv` 中全部板块；研究数据从 2024-09-10 拉到当天。

研究数据包括同花顺行业量价、换手率、流通/总市值、行业资金流、行业目录及成分快照、沪深市场每日统计、大盘资金流和交易日历，同时保留本地原始 AMV 及行业数据参考副本。原始 AMV 副本仅覆盖现有文件日期，不会生成新的原始观测值。

研究下载支持 `--start YYYYMMDD --end YYYYMMDD`。历史成功请求复用缓存，当天数据和行业/成分快照重新获取。失败请求写入报告，并让统一入口返回失败状态。`update_latest.py` 是推导结果更新工具，仍按需单独运行。

行情仍写入项目根目录的 `data/` 及现有数据库，研究数据仍写入 `back_test_data/`。`stocklist.csv` 为股票池，`storage_sqlite.py` 对接后端共用存储层。

原 `flask_backend/utils/fetch_data/`、`stock-line/tools/` 中的重复拉取脚本已统一到本目录。
