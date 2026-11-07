"""Resume industry amount backfill without rerunning unrelated fetch jobs."""
import json
import time

try:
    from . import download_amv_research as fetch
except ImportError:
    import download_amv_research as fetch


def main():
    catalog = fetch.read_csv(fetch.ROOT / 'ths_index/research_industries.csv')
    pending = [r['ts_code'] for r in catalog]
    errors = {}
    for attempt in range(1, 6):
        failed = []
        print(f'Round {attempt}: {len(pending)} industries', flush=True)
        for code in pending:
            path = fetch.ROOT / 'ths_daily' / f'{code}.csv'
            old = fetch.read_csv(path)
            missing = [r for r in old if r.get('avg_price') in (None, '') or r.get('amount') in (None, '')]
            if not missing:
                continue
            try:
                rows = fetch.query('ths_daily', dict(ts_code=code,
                    start_date=min(r['trade_date'] for r in missing), end_date=max(r['trade_date'] for r in missing),
                    fields=fetch.THS_DAILY_FIELDS), code + '_amount_backfill')
                updates = {r['trade_date']: r for r in rows if r.get('amount') is not None}
                # Keep established dates/other fields; never erase history on an incomplete response.
                merged = [({**r, **updates[r['trade_date']]} if r['trade_date'] in updates else r) for r in old]
                fetch.write_csv(path, merged)
                remaining = sum(r.get('amount') in (None, '') for r in merged)
                print(f'{code}: saved {len(merged)}, missing amount {remaining}', flush=True)
                if remaining:
                    failed.append(code)
                    errors[code] = f'{remaining} missing amount rows'
                else:
                    errors.pop(code, None)
            except fetch.InterfacePermissionDenied:
                print('Permission denied; stopped.', flush=True)
                return 1
            except Exception as exc:
                failed.append(code)
                errors[code] = fetch.redact(exc)
                print(f'{code}: {errors[code][:160]}', flush=True)
            time.sleep(.5)
        pending = failed
        if not pending:
            break
        if attempt < 5:
            time.sleep(5)
    combined = []
    for row in catalog:
        combined.extend(fetch.read_csv(fetch.ROOT / 'ths_daily' / (row['ts_code'] + '.csv')))
    fetch.write_csv(fetch.ROOT / 'ths_daily/all_industries.csv', combined)
    report = dict(industries=len(catalog), rows=len(combined),
                  missing_amount=sum(r.get('amount') in (None, '') for r in combined),
                  formula='vol * 100 * avg_price', unit='CNY', errors=errors)
    fetch.write_json(fetch.ROOT / 'metadata/ths_amount_backfill.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return int(bool(pending))


if __name__ == '__main__':
    raise SystemExit(main())
