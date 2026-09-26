"""Controlled AMV management experiments, preserving the current same-close convention.

No production strategy edits. Baseline trade P&L must reconcile to the TS engine.
All incremental rules use only prices observed up to the decision date.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Rule:
    name: str
    selection: str = 'original'
    initial: float = 1.0
    weak_only: bool = False
    arm: float = 0.0
    trail: float = 0.0


SINGLES = [Rule('baseline'),
    Rule('stage_half', initial=.5), Rule('stage_third', initial=1/3),
    Rule('stage_weak_half', initial=.5, weak_only=True), Rule('stage_weak_third', initial=1/3, weak_only=True),
    Rule('select_5d', selection='5d'), Rule('select_20d', selection='20d'),
    Rule('select_blend', selection='blend'), Rule('select_csi300', selection='csi300'),
    Rule('protect_2_1', arm=.02, trail=.01), Rule('protect_4_2', arm=.04, trail=.02),
    Rule('protect_5_3', arm=.05, trail=.03)]


class Experiment:
    def __init__(self):
        source = json.loads((OUT / 'inputs.json').read_text(encoding='utf-8'))
        self.baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
        self.amv = pd.DataFrame(source['amv']).set_index('date').sort_index()
        self.raw = pd.DataFrame({item['name']: pd.Series({row['date']: row['close'] for row in item['data']}) for item in source['etfs']})
        self.raw = self.raw.reindex(self.amv.index)
        self.prices = self.raw.ffill()  # Past quotes for valuation only; never back-fill.
        self.returns = {n: self.prices / self.prices.shift(n) - 1 for n in (1, 5, 20)}
        self.ma60 = self.amv.close.rolling(60).mean()
        self.weak = (self.amv.close < self.ma60) & (self.ma60 < self.ma60.shift(5))
        self.start = self.amv.index.searchsorted('2019-01-01')

    def holdings(self, trade, rule):
        if rule.selection == 'original' or trade['type'] != 'bull':
            return [(h['name'], h['weight']) for h in trade['holdings']]
        date = trade['start_date']
        if rule.selection == 'csi300':
            return [('沪深300ETF', 1.0)] if pd.notna(self.raw.loc[date, '沪深300ETF']) else []
        if rule.selection == 'blend':
            # Cross-sectional percentile average, fixed before inspecting results.
            score = (self.returns[1].loc[date].rank(pct=True) + self.returns[20].loc[date].rank(pct=True)) / 2
        else:
            score = self.returns[int(rule.selection[:-1])].loc[date].copy()
        score = score.where(self.raw.loc[date].notna()).drop(labels=['银行ETF'], errors='ignore').dropna()
        names = score.sort_values(ascending=False, kind='stable').head(5).index
        return list(zip(names, [.3, .3, .2, .1, .1]))

    def trade(self, trade, rule):
        start, end = trade['start_date'], trade['end_date']
        holdings = self.holdings(trade, rule)
        days = self.amv.loc[start:end].index
        names = [name for name, _ in holdings]
        weights = np.array([weight for _, weight in holdings])
        matrix = self.prices.loc[days, names].to_numpy(float)
        if not np.isfinite(matrix).all() or (matrix <= 0).any():
            raise ValueError(f'Missing/nonpositive price in {start}: {names}')
        # The residual uninvested fraction is cash, including unavailable choices.
        basket = 1 - weights.sum() + (matrix / matrix[0] * weights).sum(axis=1)
        bull = trade['type'] == 'bull'
        initial = rule.initial if bull and (not rule.weak_only or self.weak.loc[start]) else 1.0
        units = initial * weights / matrix[0]
        cash = 1 - initial * weights.sum()
        reserve = 1 - initial
        protected = False
        peak = 1.0
        values, exposures, actions = [], [], []
        missing = int(self.raw.loc[days, names].isna().sum().sum())
        for i, date in enumerate(days):
            price = matrix[i]
            nav = cash + units @ price
            peak = max(peak, basket[i])
            if bull and i > 0 and date != end:
                if rule.arm and not protected and peak >= 1 + rule.arm and basket[i] / peak - 1 <= -rule.trail:
                    proceeds = .5 * (units @ price)
                    units *= .5
                    cash += proceeds
                    reserve = 0  # No re-entry or delayed addition after protection.
                    protected = True
                    actions.append({'date': date, 'action': 'sell_half', 'basket_return_pct': (basket[i] - 1) * 100})
                if reserve and self.amv.loc[date, 'close'] > self.amv.loc[start, 'high'] and basket[i] > 1:
                    units += reserve * weights / price
                    cash -= reserve * weights.sum()
                    reserve = 0
                    actions.append({'date': date, 'action': 'add_remaining', 'basket_return_pct': (basket[i] - 1) * 100})
            after = cash + units @ price
            if not np.isclose(nav, after, atol=1e-12) or cash < -1e-10:
                raise AssertionError('Self-financing/cash constraint failed')
            values.append(nav)
            exposures.append(float(units @ price / nav))
        actual = values[-1] - 1
        if rule.name == 'baseline' and not np.isclose(actual, trade['return'], atol=1e-10):
            raise AssertionError(f'Baseline trade mismatch {start}: {actual} vs {trade["return"]}')
        return pd.Series(values, index=days), {
            'rule': rule.name, 'type': trade['type'], 'start': start, 'end': end,
            'is_open': trade.get('is_open', False), 'return_pct': actual * 100,
            'baseline_return_pct': trade['return'] * 100, 'initial_exposure': float(exposures[0]),
            'mean_exposure': float(np.mean(exposures)), 'max_close_profit_pct': (max(values) - 1) * 100,
            'giveback_pp': (max(values) - values[-1]) * 100, 'actions': actions,
            'entry_weak': bool(self.weak.loc[start]), 'missing_valuation_quotes': missing,
            'holdings': [{'name': name, 'weight': float(weight)} for name, weight in holdings]}

    def run(self, rule):
        account = pd.Series(np.nan, index=self.amv.index[self.start:])
        account.iloc[0] = 1.0
        nav = 1.0
        detail = []
        for trade in sorted(self.baseline['trades'], key=lambda t: t['start_date']):
            curve, record = self.trade(trade, rule)
            account.loc[curve.index] = curve * nav
            nav *= 1 + record['return_pct'] / 100
            detail.append(record)
        account = account.ffill()
        if not np.isclose(account.iloc[-1], nav):
            raise AssertionError('Account trade stitching failed')
        return account, detail


def dd(nav):
    return float((1 - nav / nav.cummax()).max() * 100)


PERIODS = [('2019_2022', '2019-01-01', '2022-12-31'), ('2023', '2023-01-01', '2023-12-31'),
           ('2024H1', '2024-01-01', '2024-06-30'), ('2024H2', '2024-07-01', '2024-12-31'),
           ('2025', '2025-01-01', '2025-12-31'), ('2026', '2026-01-01', '2026-09-24')]


def metrics(rule, nav, trades):
    result = {'rule': rule.name, 'total_account_return_pct': float((nav.iloc[-1] - 1) * 100), 'max_drawdown_pct': dd(nav)}
    for label, start, end in PERIODS:
        chosen = [t for t in trades if t['type'] == 'bull' and not t['is_open'] and start <= t['start'] <= end]
        returns = np.array([t['return_pct'] / 100 for t in chosen])
        result[label + '_bull_pct'] = float((np.prod(1 + returns) - 1) * 100)
        result[label + '_wins'] = int((returns > 0).sum())
        result[label + '_n'] = len(returns)
        sub = nav.loc[start:end]
        if len(sub):
            prior = nav.loc[nav.index < sub.index[0]]
            base = prior.iloc[-1] if len(prior) else 1
            result[label + '_calendar_account_pct'] = float((sub.iloc[-1] / base - 1) * 100)
            result[label + '_drawdown_pct'] = dd(pd.concat([pd.Series([base]), sub.reset_index(drop=True)], ignore_index=True))
    for date, label in [('2024-02-06', 'reversal_feb24'), ('2024-09-24', 'reversal_sep24')]:
        target = next((t for t in trades if t['type'] == 'bull' and t['start'] == date), None)
        result[label + '_pct'] = target['return_pct'] if target else None
    bull = [t for t in trades if t['type'] == 'bull' and not t['is_open']]
    losses = [t['return_pct'] for t in bull if t['return_pct'] <= 0]
    result['mean_losing_trade_pct'] = float(np.mean(losses)) if losses else 0
    result['profit_2pct_to_loss_count'] = sum(t['return_pct'] <= 0 and t['max_close_profit_pct'] >= 2 for t in bull)
    result['additional_actions'] = sum(len(t['actions']) for t in bull)
    return result


def main():
    experiment = Experiment()
    rows, details, curves = [], [], {}
    # Predefined factorial: 3 independent choices, not a search over fitted thresholds.
    combinations = [Rule(f'combo_{selection}_{stage}_{protect}', selection=selection,
                         initial=.5 if stage else 1, weak_only=True,
                         arm=.04 if protect else 0, trail=.02 if protect else 0)
                    for selection in ('original', 'blend') for stage in (False, True) for protect in (False, True)
                    if sum((selection != 'original', stage, protect)) >= 2]
    rules = SINGLES + combinations
    for rule in rules:
        nav, trades = experiment.run(rule)
        rows.append(metrics(rule, nav, trades))
        details.extend(trades)
        curves[rule.name] = nav
    results = pd.DataFrame(rows)
    results.to_csv(OUT / 'experiment_metrics.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(curves).rename_axis('date').to_csv(OUT / 'experiment_nav.csv', encoding='utf-8-sig')
    report = {'rules': [asdict(rule) for rule in rules], 'metrics': rows, 'trades': details,
              'baseline_trade_parity': True,
              'conventions': ['Same-close execution retained at user request, no fees/slippage.',
                'Fixed units within each tranche; account curve reconciles with trade P&L, unlike daily constant-weight rebalancing.',
                'Bear positions unchanged; unused bull capital remains cash, no interest.',
                'Weak state: AMV below MA60 and MA60 below its five-session-ago value.',
                'Add once after entry when AMV close exceeds signal-day high and original entry basket is profitable.',
                'Protection: original entry basket reaches arm threshold then draws down trail fraction from observed closing peak; sell half once.',
                'Protection cancels further adds; no re-entry until next original AMV signal.',
                'Cohort metrics group whole closed bull trades by start date; calendar account metrics mark to market daily.',
                'All periods are retrospective research, not untouched out-of-sample validation.']}
    (OUT / 'experiments.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
        default=lambda value: value.item() if isinstance(value, np.generic) else str(value)), encoding='utf-8')
    print(results[['rule', '2023_bull_pct', '2024H1_bull_pct', '2024H2_bull_pct', '2025_bull_pct',
                   '2026_bull_pct', 'max_drawdown_pct', 'reversal_feb24_pct', 'reversal_sep24_pct']].round(3).to_string(index=False))


if __name__ == '__main__':
    main()
