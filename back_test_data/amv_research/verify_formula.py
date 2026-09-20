"""Check standalone parity, prefix causality and arbitrary index-base invariance."""
import json
import numpy as np
import pandas as pd
from formula import BASE, calculate

codes = json.loads((BASE / 'metadata/industry_universe.json').read_text(encoding='utf-8'))['codes']
source = pd.read_csv(BASE / 'ths_daily/all_industries.csv')
actual = calculate(source, codes)
research = pd.read_csv(BASE / 'amv_research/daily_comparison.csv')
overlap = research[['date', 'revalued_turnover_ema_20']].merge(actual, on='date', validate='one_to_one')
assert len(overlap) == len(research), 'Missing original research dates'
np.testing.assert_allclose(overlap.close, overlap.revalued_turnover_ema_20, rtol=1e-12)
prefix = calculate(source[source.trade_date <= 20251231], codes)
np.testing.assert_allclose(prefix.close, actual.close.iloc[:len(prefix)], rtol=1e-12)
rebased = source.copy()
factors = dict(zip(codes, np.linspace(.1, 10, len(codes))))
rebased['close'] *= rebased.ts_code.map(factors)
np.testing.assert_allclose(calculate(rebased, codes).close, actual.close, rtol=1e-12)
summary = {'standalone_matches_research': True, 'future_append_does_not_change_past': True,
           'constant_industry_index_rebasing_invariant': True, 'rows': len(actual)}
(BASE / 'amv_research/formula_checks.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
