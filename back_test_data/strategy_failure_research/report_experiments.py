"""Generate a readable report and static comparison figure from completed experiments."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
data = pd.read_csv(OUT / 'experiment_metrics.csv').set_index('rule')
report = json.loads((OUT / 'experiments.json').read_text(encoding='utf-8'))
labels = {'baseline': '原策略', 'stage_half': '首批半仓', 'stage_third': '首批三分之一',
          'stage_weak_half': '弱趋势首批半仓', 'stage_weak_third': '弱趋势首批三分之一',
          'select_5d': '5日强度选品', 'select_20d': '20日强度选品', 'select_blend': '单日＋20日混合选品',
          'select_csi300': '固定沪深300ETF', 'protect_2_1': '浮盈2%／回撤1%减半',
          'protect_4_2': '浮盈4%／回撤2%减半', 'protect_5_3': '浮盈5%／回撤3%减半',
          'combo_original_True_True': '弱趋势半仓＋4/2保护', 'combo_blend_False_True': '混合选品＋4/2保护',
          'combo_blend_True_False': '混合选品＋弱趋势半仓', 'combo_blend_True_True': '混合选品＋弱趋势半仓＋4/2保护'}
chosen = ['baseline', 'stage_half', 'select_20d', 'select_blend', 'protect_4_2', 'combo_blend_False_True']
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout='constrained')
colors = ['#718096', '#839eb2', '#daac48', '#148c92', '#87976d', '#c54d66']
panels = [('2023_bull_pct', '2023 年多头区间复合收益'), ('2024H1_bull_pct', '2024 上半年多头区间复合收益'),
          ('reversal_feb24_pct', '2024-02-06 启动波段收益'), ('reversal_sep24_pct', '2024-09-24 启动波段收益')]
for ax, (field, title) in zip(axes.flat, panels):
    values = data.loc[chosen, field].to_numpy()
    bars = ax.barh(np.arange(len(chosen)), values, color=colors, height=.65)
    ax.set_yticks(np.arange(len(chosen)), [labels[name] for name in chosen], fontsize=10)
    ax.invert_yaxis()
    ax.axvline(0, color='#cbd5e0', linewidth=.8)
    ax.set_title(title, loc='left', fontsize=13, pad=15)
    ax.set_xlabel('收益率（%）')
    ax.grid(axis='x', alpha=.15)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for bar, value in zip(bars, values):
        ax.annotate(f'{value:+.2f}%', (value, bar.get_y() + bar.get_height()/2),
                    xytext=(5 if value >= 0 else -5, 0), textcoords='offset points',
                    va='center', ha='left' if value >= 0 else 'right', fontsize=10)
    low, high = ax.get_xlim()
    ax.set_xlim(low - (high-low)*.15, high + (high-low)*.2)
fig.suptitle('AMV 管理规则第一轮对照：改善亏损与保留反转收益的取舍', fontsize=17)
fig.savefig(OUT / 'experiment_comparison.png', dpi=150)
plt.close(fig)

lines = ['# 分批建仓、选品与部分盈利保护：第一轮结果', '',
    '沿用用户指定的原成交口径：信号当日收盘成交，不加入费用和滑点；正式策略未修改。', '',
    '本轮共 16 个预定义方案：12 个基线/单项方案，4 个组合。报告全部结果，不只展示表现最好的一段。', '',
    '**结果：测试的分批确认规则未改善 2023 年；混合选品有改善但未转正；适度部分保护主要降低全期回撤。尚无方案同时保持全部反转收益并消除弱市亏损。**', '',
    '![实验对照](experiment_comparison.png)', '',
    '## 统计口径', '',
    '- 多头区间收益：按启动日期分组，将完整已结束交易复合；不含银行 ETF 收益，不是自然年账户收益。',
    '- 账户回撤：2019 年至 2026-09-24 逐日收盘净值，包含原银行规则；每笔持仓按实际份额估值。',
    '- 份额口径逐笔核对了原 TypeScript 引擎的交易收益。旧页面每日曲线按固定权重日收益连乘，与其逐笔买入持有收益并非同一算法，因此这里原策略最大回撤 15.91% 不要求等于旧页面 16.17%。所有实验统一采用可与逐笔收益对账的份额口径；成交时点没有改变。',
    '- 使用现有 ETF 候选池和项目默认参数；不是对用户浏览器临时参数的精确恢复。',
    '- 历史已用于观察，以下均为回顾性比较，不能称作未触碰的盲测。', '',
    '## 全部实验', '',
    '| 方案 | 2019—2022多头 | 2023多头 | 2024上半年多头 | 2024下半年多头 | 2025多头 | 2026多头 | 全期账户最大回撤 |',
    '|---|---:|---:|---:|---:|---:|---:|---:|']
fields = ['2019_2022_bull_pct', '2023_bull_pct', '2024H1_bull_pct', '2024H2_bull_pct', '2025_bull_pct', '2026_bull_pct', 'max_drawdown_pct']
for name, row in data.iterrows():
    lines.append('| ' + labels[name] + ' | ' + ' | '.join(f'{row[field]:.2f}%' for field in fields) + ' |')
lines += ['', '## 规则定义', '',
    '- 原策略：启动日涨幅前五，仓位 30/30/20/10/10；AMV 原始进出条件不变。',
    '- 分批：首批半仓或三分之一；从下一交易日起，若 AMV 收盘突破启动日最高值，且启动日原组合仍盈利，按当日收盘价格补足剩余资金。只加一次，未确认部分留现金。',
    '- 弱趋势：启动日 AMV 在 MA60 下方，且 MA60 低于五个交易日前；只在满足这两个条件时分批。',
    '- 5日/20日选品：按截至启动日收盘的对应涨幅选前五，权重不变。',
    '- 混合选品：当日涨幅横截面百分位与20日涨幅百分位各占一半，选前五，权重不变。',
    '- 盈利保护：按启动日原组合的收盘净值观察，达到浮盈门槛后，从已发生的最高收盘净值回撤达到门槛时，按当日实际收盘值卖出一半持仓。不是假定卖在门槛价格。另一半沿用原退出。',
    '- 保护仅触发一次，触发后不加仓、不在原区间内重新买入；卖出部分留现金。组合方案采用混合选品、弱趋势半仓和4%/2%保护的固定搭配。', '',
    '## 为什么分批反而恶化2023年', '',
    '首批半仓降低了2023-12-29那笔直接下跌交易的损失（-3.78%→-1.89%），但另外几次短暂上涨同样满足加仓条件。',
    '2023-01-30波段在02-01补仓，最终-2.28%→-2.88%；2023-08-28波段在08-29补仓，最终+0.08%→-0.62%。确认条件没有区分持续上涨与短反弹，补仓反而抬高成本。',
    '因此只能否定本轮这些分批规则，不能推论所有分批方式都无效。', '',
    '## 为什么不选单看2023年最好的20日排名', '',
    '20日排名将2023年亏损减至-1.66%，但2024上半年多头收益只有+1.74%。2024-02-06大反转波段收益由+12.95%降至+4.46%，说明反转初期的此前弱势资产可能被中期排名排除。', '',
    '## 为什么保护不能保证不回吐', '',
    '2%/1%保护把全期回撤降至11.57%，但2023年收益恶化至-7.29%。2023-04-03波段曾达到盈利门槛，04-10收盘已跌到组合-3.59%才触发减半，不能假设成交在盈利保护线上。另一笔10月盈利波段被过早减仓，收益由+5.14%降至+3.00%。',
    '4%/2%保护没有改变2023年的交易，却把全期回撤由15.91%降至13.11%；其价值更接近控制部分大波段回吐，而非修复所有弱市亏损。', '',
    '## 大反转收益', '', '| 方案 | 2024-02-06波段 | 2024-09-24波段 |', '|---|---:|---:|']
for name in chosen:
    lines.append(f'| {labels[name]} | {data.loc[name,"reversal_feb24_pct"]:.2f}% | {data.loc[name,"reversal_sep24_pct"]:.2f}% |')
lines += ['', '## 本轮值得保留的对照', '',
    '保留原策略、混合选品、混合选品＋4%/2%保护三条对照，不直接替换正式策略。',
    '混合选品降低2023年亏损，但2024上半年收益低于原策略，且全期回撤略高。叠加保护将全期回撤降至13.09%，但2024上半年收益进一步降至7.49%，2月反转波段从原12.95%降至8.24%。',
    '混合选品在2023年只有1笔盈利，而原策略有2笔，但最终亏损更小；胜率不应作为唯一目标。',
    '下一轮如继续，宜检查行业集中度或选择稳定性、保护阈值的小范围稳定性及时间滚动表现，而不是继续叠加许多规则后寻找最漂亮的一条曲线。', '',
    '## 复现与核验', '',
    '```powershell', 'python back_test_data/strategy_failure_research/experiments.py',
    'python -m unittest discover -s back_test_data/strategy_failure_research -p test_experiments.py',
    'python back_test_data/strategy_failure_research/report_experiments.py', '```', '',
    '验证了原策略逐笔收益一致、加仓使用确认日价格、未加仓资金留现金、跳跌不假设按保护价成交、未来价格修改不影响此前净值和操作。',
    '完整结果：experiment_metrics.csv、experiments.json；逐日净值：experiment_nav.csv。']
(OUT / 'EXPERIMENTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('Saved EXPERIMENTS.md and experiment_comparison.png')
