"""Read-only snapshot for ranking comparisons; never alter production data."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'flask_backend'))
from market_store import connect


def main():
    with connect() as db:
        catalog = [dict(r) for r in db.execute('SELECT * FROM etf_catalog WHERE enabled=1 ORDER BY sort_order,code')]
        mappings = [dict(r) for r in db.execute("SELECT * FROM etf_sector_mapping WHERE flow_type='ind_ths'")]
        amv = [dict(r) for r in db.execute('SELECT date,open,high,low,close,volume,amount FROM indicator_daily WHERE indicator_id=(SELECT id FROM indicators WHERE code=?) ORDER BY date', ('0AMV',))]
        etfs = []
        for item in catalog:
            bars = [dict(r) for r in db.execute("SELECT date,open,high,low,close,volume,amount FROM daily_bars WHERE category='etf' AND code=? ORDER BY date", (item['code'],))]
            etfs.append(dict(id=item['code'], name=item['name'], data=bars))
    industries = pd.read_csv(ROOT / 'back_test_data/ths_index/research_industries.csv')
    days = pd.Index([r['date'].replace('-', '') for r in amv])
    volumes, changes, source_hashes = {}, {}, {}
    for row in industries.itertuples():
        path = ROOT / 'back_test_data/ths_daily' / (row.ts_code + '.csv')
        source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        df = pd.read_csv(path, dtype={'trade_date': str}).drop_duplicates('trade_date').set_index('trade_date')
        volumes[row.name] = pd.to_numeric(df['vol'], errors='coerce').reindex(days)
        changes[row.name] = pd.to_numeric(df['pct_change'], errors='coerce').reindex(days)
    vol = pd.DataFrame(volumes, index=days)
    features, mapping_audit = {}, []
    for etf in catalog:
        names = sorted({r['sector_name'] for r in mappings if r['etf_code'] == etf['code']} & set(vol.columns))
        mapping_audit.append(dict(code=etf['code'], name=etf['name'], industries=names))
        if not names:
            continue
        # Fixed, exact-match database mappings; require every component on all 21 sessions.
        combined = vol[names].sum(axis=1, min_count=len(names))
        average = combined.shift(1).rolling(20, min_periods=20).mean()
        ratio = combined / average
        for day, value in ratio.items():
            if pd.notna(value) and np.isfinite(value) and value > 0:
                iso = f'{day[:4]}-{day[4:6]}-{day[6:]}'
                features.setdefault(iso, {})[etf['name']] = float(value)
    payload = dict(amv=amv, etfs=etfs, catalog=catalog, mappings=mapping_audit, volume_features=features,
                   sources=source_hashes, industry_count=len(vol.columns),
                   coverage=dict(first_raw=str(vol.dropna(how='all').index.min()),
                                 first_feature=min(features), last_feature=max(features)),
                   unavailable=['True industry turnover amount/share: ths_daily amount probe returned no amount field.'])
    (HERE / 'inputs.json').write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps(dict(last=amv[-1]['date'], etfs=len(etfs), coverage=payload['coverage'], mappings=mapping_audit), ensure_ascii=False))


if __name__ == '__main__':
    main()
