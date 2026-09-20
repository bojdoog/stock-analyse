"""Causal candidate-formula research. No AMV lags or AMV volume enter models."""
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
import io
import sys
sys.path.insert(0, str(ROOT.parent / 'flask_backend'))
from market_store import file_content
OUT = ROOT / 'amv_research'
OUT.mkdir(exist_ok=True)

amv = pd.read_csv(io.BytesIO(file_content('core_index/0AMV-2013-2026.csv')), parse_dates=['date']).set_index('date').sort_index()
prices = pd.read_csv(ROOT / 'ths_daily/all_industries.csv')
prices['date'] = pd.to_datetime(prices.trade_date.astype(str))
dates = pd.DatetimeIndex(sorted(prices.date.unique()))
y = amv.reindex(dates)['close'].to_numpy(float)
mv = prices.pivot(index='date', columns='ts_code', values='float_mv').reindex(dates).to_numpy(float) / 1e8
tau = prices.pivot(index='date', columns='ts_code', values='turnover_rate').reindex(dates).to_numpy(float) / 100
close = prices.pivot(index='date', columns='ts_code', values='close').reindex(dates).to_numpy(float)
ret = prices.pivot(index='date', columns='ts_code', values='pct_change').reindex(dates).to_numpy(float) / 100
codes = prices.pivot(index='date', columns='ts_code', values='close').columns.to_list()
market = pd.read_csv(ROOT / 'daily_info/20240910_20260911.csv')
market['date'] = pd.to_datetime(market.trade_date.astype(str))
mp = market.pivot(index='date', columns='ts_code', values='amount').reindex(dates)
# SH_A and STAR are distinct rows in this data. SZ_MAIN can include B shares;
# this is a documented market-turnover proxy, not a claimed exact A-share total.
amount = mp[['SH_A', 'SH_STAR', 'SZ_MAIN', 'SZ_GEM']].sum(axis=1).to_numpy(float)
cap = mv.sum(axis=1)
turnover_value = (mv * tau).sum(axis=1)
weighted_return = (np.vstack([mv[0], mv[:-1]]) * ret).sum(axis=1) / np.vstack([mv[0], mv[:-1]]).sum(axis=1)
train = (dates >= '2024-12-10') & (dates <= '2025-06-30')
valid = (dates >= '2025-07-01') & (dates <= '2025-12-31')
test = dates >= '2026-01-01'
assert np.isfinite(y).all() and (y > 0).all()
assert np.isfinite(mv).all() and np.isfinite(tau).all()


def ema(x, span):
    return pd.DataFrame(x).ewm(span=span, adjust=False).mean().to_numpy().squeeze()


def rolling(x, window):
    return pd.DataFrame(x).rolling(window, min_periods=1).sum().to_numpy().squeeze()


def scale(x):
    # Multiplicative calibration, fit on TRAIN ONLY with squared log loss.
    return float(np.exp(np.mean(np.log(y[train]) - np.log(np.maximum(x[train], 1e-12)))))


def metrics(pred, mask):
    obs, p = y[mask], pred[mask]
    er = p - obs
    r2 = 1 - (er @ er) / np.sum((obs - obs.mean()) ** 2)
    yr = np.r_[np.nan, np.diff(y) / y[:-1]]
    pr = np.r_[np.nan, np.diff(pred) / pred[:-1]]
    good = mask & np.isfinite(yr) & np.isfinite(pr)
    correlation = float(np.corrcoef(yr[good], pr[good])[0, 1]) if np.std(pr[good]) > 1e-12 else None
    return {'n': int(mask.sum()), 'mape_pct': float(np.mean(np.abs(er / obs)) * 100),
            'r2': float(r2), 'log_rmse': float(np.sqrt(np.mean(np.log(p / obs)**2))),
            'return_corr': correlation,
            'return_mae_pp': float(np.mean(np.abs(pr[good] - yr[good])) * 100),
            'direction_accuracy_pct': float(np.mean(np.sign(pr[good]) == np.sign(yr[good])) * 100)}


candidates = []
predictions = {}


def add(name, family, x, params):
    k = scale(x)
    pred = np.maximum(k * x, 1e-12)
    predictions[name] = pred
    candidates.append({'name': name, 'family': family, 'params': {**params, 'scale': k},
                       **{f'{s}_{k}': v for s, m in [('train', train), ('validation', valid), ('test', test)]
                          for k, v in metrics(pred, m).items()}})


add('market_cap', 'market_cap', cap, {})
add('market_amount', 'market_amount', amount, {})
for span in [2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120]:
    add(f'amount_ema_{span}', 'amount_ema', ema(amount, span), {'span': span})
    add(f'turnover_value_ema_{span}', 'turnover_value_ema', ema(turnover_value, span), {'span': span})
    # Revalue a smoothed volume proxy at today's sector index price.
    x = (ema(mv * tau / close, span) * close).sum(axis=1)
    add(f'revalued_turnover_ema_{span}', 'revalued_turnover_ema', x, {'span': span})
    for lam in [0.25, 0.5, 1, 2, 4]:
        activity = -np.expm1(-lam * rolling(tau, span))
        add(f'saturation_{span}_{lam}', 'rolling_saturation', (mv * activity).sum(axis=1), {'window': span, 'lambda': lam})


def recurrence(delta, lam):
    a = np.zeros_like(tau)
    # Fixed deterministic initial condition, never initialized from target AMV.
    state = np.zeros(tau.shape[1])
    for t in range(len(dates)):
        surviving = (1 - delta) * state
        state = surviving + (1 - surviving) * (-np.expm1(-lam * tau[t]))
        a[t] = state
    return (mv * a).sum(axis=1)


# Fit a small, interpretable two-parameter recurrence on train, with a few starts.
def residual(params):
    delta, lam = np.exp(params)
    x = recurrence(delta, lam)
    return np.log(scale(x) * x[train] / y[train])

for initial_delta in [0.02, 0.08, 0.25]:
    fit = least_squares(residual, np.log([initial_delta, 1]),
                        bounds=(np.log([0.002, 0.01]), np.log([0.95, 20])), max_nfev=180)
    delta, lam = np.exp(fit.x)
    add(f'recurrence_{initial_delta}', 'active_share_recurrence', recurrence(delta, lam),
        {'delta': float(delta), 'lambda': float(lam), 'initial_activity': 0})

# Generalized activity elasticities; no 90 independent industry coefficients.
for span in [5, 10, 20, 30, 60]:
    smoothed_tau = ema(tau, span)
    def power_residual(z):
        x = (mv * np.maximum(smoothed_tau, 1e-10) ** z[0]).sum(axis=1)
        return np.log(scale(x) * x[train] / y[train])
    fit = least_squares(power_residual, [0.5], bounds=([0], [2]))
    power = float(fit.x[0])
    add(f'power_activity_{span}', 'power_activity', (mv * np.maximum(smoothed_tau, 1e-10)**power).sum(axis=1),
        {'span': span, 'power': power})

scores = pd.DataFrame([{k:v for k,v in c.items() if k != 'params'} for c in candidates])
scores.to_csv(OUT / 'all_candidate_metrics.csv', index=False, encoding='utf-8-sig')
# Select families and the overall result using VALIDATION ONLY.
best_by_family = scores.sort_values('validation_log_rmse').groupby('family', sort=False).head(1)
winner = str(best_by_family.iloc[0]['name'])
winner_record = next(c for c in candidates if c['name'] == winner)
selected_names = best_by_family.name.to_list()
best_by_family.to_csv(OUT / 'selected_family_metrics.csv', index=False, encoding='utf-8-sig')


def signals(series):
    ma = pd.Series(series).rolling(10).mean().to_numpy()
    r = np.r_[0., np.diff(series)/series[:-1]*100]
    prev_r = np.r_[0., r[:-1]]
    entry = ((r > 4) | ((r > 0) & (prev_r > 0) & (r+prev_r > 4))) & (series > ma)
    exit_ = (r < -2.3) | (series < ma)
    state = False
    states, entries, exits = [], [], []
    for t in range(len(series)):
        e, x = False, False
        if not state and entry[t]:
            state, e = True, True
        elif state and exit_[t]:
            state, x = False, True
        states.append(state); entries.append(e); exits.append(x)
    return np.array(states), np.array(entries), np.array(exits)


truth_state, truth_entry, truth_exit = signals(y)
signal_metrics = []
for name in selected_names:
    state, entry, exit_ = signals(predictions[name])
    for period, mask in [('validation', valid), ('test', test)]:
        tp = int(np.sum(entry & truth_entry & mask))
        n_actual, n_pred = int(np.sum(truth_entry & mask)), int(np.sum(entry & mask))
        signal_metrics.append({'model': name, 'period': period,
            'state_agreement_pct': float(np.mean(state[mask] == truth_state[mask]) * 100),
            'actual_entries': n_actual, 'predicted_entries': n_pred, 'same_day_entries': tp,
            'entry_precision': tp/n_pred if n_pred else None, 'entry_recall': tp/n_actual if n_actual else None,
            'actual_exits': int(np.sum(truth_exit & mask)), 'predicted_exits': int(np.sum(exit_ & mask)),
            'same_day_exits': int(np.sum(exit_ & truth_exit & mask))})
pd.DataFrame(signal_metrics).to_csv(OUT / 'signal_metrics.csv', index=False, encoding='utf-8-sig')

frame = pd.DataFrame({'date': dates, 'amv': y, 'market_turnover_proxy_yi': amount,
                      'sector_float_mv_yi': cap, 'sector_turnover_value_proxy_yi': turnover_value,
                      'period': np.where(test, 'test', np.where(valid, 'validation', np.where(train, 'train', 'warmup')))})
for name in selected_names:
    frame[name] = predictions[name]
frame['amv_return_pct'] = frame.amv.pct_change()*100
frame['candidate_return_pct'] = pd.Series(predictions[winner]).pct_change()*100
frame['relative_error_pct'] = (predictions[winner]/y-1)*100
frame.to_csv(OUT / 'daily_comparison.csv', index=False, encoding='utf-8-sig')
frame.loc[test].assign(abs_error=lambda d:d.relative_error_pct.abs()).nlargest(15,'abs_error').to_csv(
    OUT/'largest_test_errors.csv', index=False, encoding='utf-8-sig')

# Residual diagnostics: flow data is never silently zero-filled.
flows = pd.read_csv(ROOT / 'moneyflow_ind_ths/20240910_20260911.csv')
flows['date'] = pd.to_datetime(flows.trade_date.astype(str))
invalid_flow_days = pd.to_datetime(['20240910','20240911','20240912','20240913','20240918','20240919',
    '20240920','20240923','20240924','20240925','20240926','20240927','20240930'])
flow_sum = flows[~flows.date.isin(invalid_flow_days)].groupby('date').net_amount.sum().reindex(dates)
dc = pd.read_csv(ROOT / 'moneyflow_mkt_dc/20240910_20260911.csv')
dc['date'] = pd.to_datetime(dc.trade_date.astype(str))
dc_flow = dc.set_index('date').net_amount.reindex(dates)/1e8
diagnostic = pd.DataFrame({'amv_return': pd.Series(y,index=dates).pct_change(),
    'amount_change': pd.Series(amount,index=dates).pct_change(),
    'cap_change': pd.Series(cap,index=dates).pct_change(),
    'weighted_sector_return': weighted_return,
    'sector_up_fraction': (ret>0).mean(axis=1),
    'ths_net_flow_over_cap': flow_sum / cap,
    'dc_net_flow_over_cap': dc_flow / cap,
    'candidate_return': pd.Series(predictions[winner],index=dates).pct_change()}, index=dates)
diagnostic.corr().to_csv(OUT/'diagnostic_correlations.csv', encoding='utf-8-sig')

fig, axes = plt.subplots(3,1,figsize=(14,11),sharex=True,gridspec_kw={'height_ratios':[2,1,1]})
axes[0].plot(dates,y,label='Original AMV',color='#111827',lw=1.8)
axes[0].plot(dates,predictions[winner],label=winner,color='#2563eb',lw=1.5)
axes[0].set_ylabel('AMV units'); axes[0].legend(); axes[0].set_title('AMV reconstruction: chronological out-of-sample evaluation')
axes[1].plot(dates,frame.relative_error_pct,color='#dc2626',lw=1)
axes[1].axhline(0,color='gray',lw=.8); axes[1].set_ylabel('Level error (%)')
axes[2].plot(dates,frame.amv_return_pct,label='Original daily change',color='#111827',lw=.8,alpha=.8)
axes[2].plot(dates,frame.candidate_return_pct,label='Candidate daily change',color='#2563eb',lw=.8,alpha=.8)
axes[2].set_ylabel('Daily change (%)'); axes[2].legend()
for ax in axes:
    ax.axvline(pd.Timestamp('2025-07-01'),ls='--',color='#a16207')
    ax.axvline(pd.Timestamp('2026-01-01'),ls='--',color='#16a34a')
    ax.axvspan(pd.Timestamp('2026-01-01'),dates[-1],alpha=.05,color='green')
    ax.grid(alpha=.15)
fig.tight_layout(); fig.savefig(OUT/'comparison.png',dpi=160); plt.close(fig)

result = {'selected_by':'lowest validation log RMSE; no model selection on test',
          'winner':winner_record, 'n_candidates':len(candidates),
          'splits':{s:{'start':str(dates[m][0].date()),'end':str(dates[m][-1].date()),'n':int(m.sum())}
                    for s,m in [('train',train),('validation',valid),('test',test)]},
          'selected_families':[{**next(c for c in candidates if c['name']==name)} for name in selected_names],
          'winner_signals':[s for s in signal_metrics if s['model']==winner],
          'limitations':['Candidate formulas, not identified proprietary formula',
              'Only 486 days; same-period data vendor history may be revised',
              'No point-in-time industry membership, market-universe differences remain',
              'Original AMV volume/amount and target lags are not model inputs',
              'Test statistics are descriptive; any subsequent tuning requires a new holdout',
              'Signals are replication diagnostics, not a strategy profitability backtest']}
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({'winner':winner_record,'splits':result['splits'],'signals':result['winner_signals']},ensure_ascii=True))
print(best_by_family[['name','validation_mape_pct','test_mape_pct','test_return_corr','test_direction_accuracy_pct']].to_string(index=False))
