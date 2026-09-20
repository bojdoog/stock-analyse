# 字段与数据口径

本目录保存源接口数值，不统一改写金额单位，不对缺失值插值。CSV 使用 UTF-8 BOM 编码。
`raw/` 保存请求参数、抓取时间、MCP 返回内容及解析后的记录，不含 token。

| 数据 | 关键字段及单位 | 用途与限制 |
|---|---|---|
| AMV | `date,open,high,low,close,volume,amount` | 来自项目原始 CSV；数值单位尚未从导出设置核实，不直接假定 close 是亿元 |
| ths_daily | OHLC 为指数点位；`pct_change,turnover_rate` 为百分数；`vol` 为手；`float_mv,total_mv` 为元 | 百分数参与公式时除以 100；市值已包含价格，不能再乘指数点位 |
| moneyflow_ind_ths | `close` 为行业收盘指数；`pct_change` 为行业涨跌幅；`net_buy_amount,net_sell_amount,net_amount` 文档标注为亿元 | `close_price` 是领涨股价格，`pct_change_stock` 是领涨股涨跌幅。资金字段有全零和算术关系异常，研究前需核实；不能擅自改小数点 |
| daily_info | `total_mv,float_mv,amount` 为亿元；`total_share,float_share,vol` 为亿股；`tr` 为百分数 | 总计与子市场不能重复相加。缺字段保留空值；A/B 股、科创板的统计范围需要明确 |
| sz_daily_info | 金额、数量保留原值 | 官方字段表未明确单位，不能直接与 daily_info 相加；需按同日同市场核实数量级 |
| moneyflow_mkt_dc | 各金额为元，各 `*_rate` 为百分数 | `buy_elg_amount` 等实际为分档净流入额，可为负；并非买入总额 |
| trade_cal | `cal_date,pretrade_date` 为 YYYYMMDD；`is_open` 为 0/1 | 沪深交易日历分别保存，用于覆盖检查 |
| ths_index | 行业目录及上市日期 | 完整目录包含不同分类体系，主研究只使用 industry_universe.json 中的行业代码 |
| ths_member | `con_code,con_name,is_new,weight,in_date,out_date` | 下载时快照；历史有效日期可能缺失，不代表具备完整历史成分 |

原始字段语义来源：

- [板块指数行情](https://tushare.pro/document/2?doc_id=260)
- [同花顺行业资金流](https://tushare.pro/document/2?doc_id=343)
- [市场交易统计](https://tushare.pro/document/2?doc_id=215)
- [深圳市场统计](https://tushare.pro/document/2?doc_id=268)
- [大盘资金流](https://tushare.pro/document/2?doc_id=345)

这些数据用于构建与检验候选指标，不证明已获得指南针的原始算法。
