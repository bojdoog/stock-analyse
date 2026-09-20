# 活跃市值反推研究数据

使用前请阅读 [字段与单位说明](DATA_DICTIONARY.md) 和 [数据质量检查](quality/README.md)。

研究区间：20240910—20260911。交易日历覆盖 486 个交易日。

通过 Tushare MCP 只读下载；token 不写入数据。原始返回保存在 raw，清单保存在 download_manifest.json。

| 目录 | 内容 |
|---|---|
| amv | 原始 AMV 文件副本及研究区间 CSV |
| ths_daily | 各行业量价、换手率和市值；另有合并 CSV |
| moneyflow_ind_ths | 未做 ETF 映射过滤的行业资金流 |
| daily_info / sz_daily_info | 市场每日统计及深圳补充统计 |
| moneyflow_mkt_dc | 东方财富大盘资金流 |
| ths_index / ths_member | 行业目录和成分快照 |
| trade_cal | 沪深交易日历 |
| local_industry_reference | 现有 74 行业数据副本，用于核对 |
| metadata | MCP 接口定义及行业代码全集 |

## 使用注意

- 空值、零值、日期缺口保留原样，不插值、不把缺失补零。详见 quality_report.json。
- 行业及概念不能未经检查直接相加；交易所总计与分项存在重叠。
- 行业目录含多套重叠分类；主要行情与成分使用资金流接口中的行业代码。supplemental_classifications 为另外下载的分类数据，仅供参考。
- 成分是下载时快照，即使带纳入/剔除日期也需验证历史完整性；不能直接作为历史成分使用。
- moneyflow_ind_ths 的 close 是板块指数，close_price 是领涨股价格，不能混用。
- ths_daily 的流通市值已包含价格，不应再乘指数点位。
- 尚未加入模型预热期；当前只提供约定研究区间。
- 单次抽样成功不能保证全区间字段完整，字段空值比例见质量报告。

## 下载结果

- moneyflow_ind_ths: 43560 行，484 个日期，缺 2 个交易日。
- daily_info: 5784 行，486 个日期，缺 0 个交易日。
- sz_daily_info: 6764 行，485 个日期，缺 1 个交易日。
- moneyflow_mkt_dc: 486 行，486 个日期，缺 0 个交易日。
- ths_daily: 43740 行，486 个日期，缺 0 个交易日。
- amv: 486 行，486 个日期，缺 0 个交易日。
- local_industry_reference: 35816 行，484 个日期，缺 2 个交易日。

全零行业资金日：['20240910', '20240911', '20240912', '20240913', '20240918', '20240919', '20240920', '20240923', '20240924', '20240925', '20240926', '20240927']
失败请求：0

重复运行 python back_test_data/download_amv_research.py 可复用成功请求缓存并重试失败部分。
