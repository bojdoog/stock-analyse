"""Readable results from run.cjs, including unavailable factors and mapping limitations."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
r = json.loads((HERE / 'results.json').read_text(encoding='utf-8'))
labels = {
    'baseline_50_50': '原方案：当天50 / 20日50',
    'day_only': '只按当天涨幅',
    'price_70_30': '当天70 / 20日30',
    'price_30_70': '当天30 / 20日70',
    'price_20d_only': '只按20日涨幅',
    'price_40_30_normalized': '当天57.14 / 20日42.86（4:3）',
    'price_30_40_normalized': '当天42.86 / 20日57.14（3:4）',
    'price_40_20_normalized': '当天66.67 / 20日33.33（2:1）',
    'volume_45_45_10': '当天45 / 20日45 / 放量10',
    'volume_40_40_20': '当天40 / 20日40 / 放量20',
    'volume_35_35_30': '当天35 / 20日35 / 放量30',
    'volume_35_35_20_no_amount': '35:35:20，缺成交额占比10项，非完整四因子',
    'volume_30_40_20_no_amount': '30:40:20，缺成交额占比10项，非完整四因子',
    'volume_40_30_20_no_amount': '40:30:20，缺成交额占比10项，非完整四因子',
    'volume_40_20_30_no_amount': '40:20:30，缺成交额占比10项，非完整四因子',
}
lines = [
    '买入排名对照回测（截至2026-10-23）', '',
    '截图复现：2019至今累计收益853.77%，逐日净值最大回撤13.45%。',
    '固定：单日+4%或两日+4%启动，不要求启动日站上MA10；单日-2.3%或跌破MA10退出；',
    '前五各20%，杠杆1；盈利保护13.5%启动、峰值回撤2.2%卖一半；2024年起空头持有银行。',
    '只在内存副本替换排序函数，没有更改正式回测、数据库或前端。', '',
    '一、2025-01-01至2026-10-23共同样本',
    '累计与年度收益按实际日历日净值分段，2026为年初至10月23日。',
    '成功率=已结束且收益>0的多头区间数/已结束多头区间数；共12段，10月23日新启动段不计成功率。',
    '方案 | 累计收益% | 最大回撤% | 成功率 | 2025收益% | 2026收益%',
]
for c in r['cases']:
    m = c['recent']
    lines.append(f"{labels[c['name']]} | {m['return_pct']:.2f} | {m['max_drawdown_pct']:.2f} | {m['wins']}/{m['completed_bulls']} ({m['win_rate_pct']:.2f}%) | {c['annual']['2025']['return_pct']:.2f} | {c['annual']['2026']['return_pct']:.2f}")
lines += ['', '二、2019至今完整历史：只含价格因子方案', '方案 | 累计收益% | 最大回撤% | 已结束多头成功率']
for c in r['cases']:
    if c['full']:
        m = c['full']
        lines.append(f"{labels[c['name']]} | {m['return_pct']:.2f} | {m['max_drawdown_pct']:.2f} | {m['wins']}/{m['completed_bulls']} ({m['win_rate_pct']:.2f}%)")
lines += ['', '三、收益年度口径说明',
          '网页将整段收益归属于区间开始年份，所以原方案网页2025为40.25%、2026为54.59%；',
          '按日历年净值分割是38.30%、54.03%。两者总收益一致，跨年持仓归属不同。',
          '', '四、限制与验证',
          '同花顺行业日线从2024-09-10开始，20交易日预热后最早2024-10-17可用；主比较选2025至今。',
          '板块量能来自THS行业vol，完全没有使用ETF成交量。合并固定映射的行业成交量后，与自身此前20个交易日均量比较。',
          '放量方向用ETF当日涨跌方向；仅在有板块量能的候选之间计算量能百分位。',
          '卫星、创业板、上证50、中证2000没有匹配的THS行业日线，保留候选并给量能中性分0.5；没有伪造数据或删除候选。',
          '映射沿用数据库，包含沪深300对应多个行业、半导体包含消费电子等宽泛映射；结果是该映射下的初步检验。',
          '实际调用ths_daily请求vol,amount，返回仅有vol，没有amount；未将净流入、买卖额或市值×换手率当作真实成交额。',
          '标注缺成交额项的方案仅检验其余三项比例，不能当作完整35/35/20/10等四因子策略结果。',
          '无成交额项的权重按比例合成排序，权重和0.9不影响顺序；不是将10%资金留现金。',
          '原生产引擎与50/50注入排序结果完全一致；各方案多空区间、银行交易完全一致；期末净值与区间收益复利对账通过。',
          '采用现有信号日收盘成交口径，未计费用/滑点，也未验证下一交易日成交；不代表实盘可实现收益。',
          '保留项目现有ETF池和历史价格口径，未重建历史品种池或独立审计复权来源。',
          '', '五、映射审计']
for item in r['mappings']:
    lines.append(f"{item['code']} {item['name']}：{', '.join(item['industries']) or '无行业映射，量能中性分'}")
lines += ['', '六、每个多头区间的持仓与收益（2025至今）']
for c in r['cases']:
    lines.append(labels[c['name']])
    for t in c['trades']:
        if t['type'] == 'bull' and t['start_date'] >= '2025-01-01':
            lines.append(f"  {t['start_date']} ~ {t['end_date']}：{t['return']*100:.2f}%；" + '、'.join(h['name'] for h in t['holdings']))
(HERE / 'report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines[:38]))
