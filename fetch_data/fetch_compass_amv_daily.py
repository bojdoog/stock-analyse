"""Export Compass's observed 28-byte AMV daily format, preserving existing dates.

The reverse-engineered layout is validated against its block index and existing
OHLC history before writing. Unknown layouts fail closed. Close Compass first.
"""
import argparse
import csv
import json
import math
import shutil
import struct
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']
MARKER = b'Z_SK0AMV' + bytes(24)


def day_string(value):
    return datetime.strptime(str(value), '%Y%m%d').strftime('%Y-%m-%d')


def parse_daily(data):
    if len(data) < 38 or struct.unpack_from('<H', data, 20)[0] != 28:
        raise ValueError('Unsupported daily record size')
    capacity = struct.unpack_from('<I', data, 30)[0]
    if capacity != 250:
        raise ValueError('Unsupported block capacity')
    positions, cursor = [], 0
    while True:
        pos = data.find(MARKER, cursor)
        if pos < 0:
            break
        positions.append(pos)
        cursor = pos + len(MARKER)
    # Index: symbol[32], latest_date, repeated (block_id, count, last_date).
    indexes = [p for p in positions if p + 45 <= len(data)
               and struct.unpack_from('<I', data, p + 36)[0] == 1
               and 0 < data[p + 40] <= capacity]
    if len(indexes) != 1:
        raise ValueError('AMV block index missing or ambiguous')
    index = indexes[0]
    latest = struct.unpack_from('<I', data, index + 32)[0]
    day_string(latest)
    entries, cursor = [], index + 36
    while cursor + 9 <= len(data):
        block_id, count, last = struct.unpack_from('<IBI', data, cursor)
        if block_id == count == last == 0:
            break
        if block_id != len(entries) + 1 or not 0 < count <= capacity:
            raise ValueError('Unsupported/nonsequential block index')
        day_string(last)
        entries.append((count, last))
        cursor += 9
    if not entries or entries[-1][1] != latest:
        raise ValueError('Incomplete daily index')
    stride = 16 + 32 + capacity * 28
    # Identify the contiguous data block chain by all indexed end dates.
    candidates = []
    for start in positions:
        if start <= index:
            continue
        if all(start + n * stride + 32 + count * 28 <= len(data)
               and data[start + n * stride:start + n * stride + 32] == MARKER
               and struct.unpack_from('<I', data, start + n * stride + 32 + (count - 1) * 28)[0] == last
               for n, (count, last) in enumerate(entries)):
            candidates.append(start)
    if len(candidates) != 1:
        raise ValueError('Daily block chain missing or ambiguous')
    rows = []
    for n, (count, _) in enumerate(entries):
        for i in range(count):
            date, *values = struct.unpack_from('<I6f', data, candidates[0] + n * stride + 32 + i * 28)
            day = day_string(date)
            op, hi, lo, cl, vol, amount = values
            if not all(math.isfinite(v) and v >= 0 for v in values) or not 0 < lo <= min(op, cl) <= max(op, cl) <= hi:
                raise ValueError(f'Invalid OHLC record: {day}')
            if rows and day <= rows[-1]['date']:
                raise ValueError(f'Non-increasing dates: {day}')
            rows.append(dict(zip(FIELDS, [day, *(round(v, 2) for v in values[:4]), vol, amount])))
    return rows


def merge_daily(existing, incoming):
    old = {r['date']: r for r in existing}
    if len(old) != len(existing):
        raise ValueError('Duplicate dates in existing CSV')
    overlap = [r for r in incoming if r['date'] in old]
    if existing and not overlap:
        raise ValueError('No overlapping dates to validate source')
    differences = []
    for row in overlap:
        for key in FIELDS[1:]:
            previous, current = float(old[row['date']][key]), float(row[key])
            if not math.isfinite(previous):
                raise ValueError('Non-finite existing data')
            if abs(previous - current) > 0.011:
                differences.append({'date': row['date'], 'field': key, 'existing': previous, 'cache': current})
                if key in FIELDS[1:5]:
                    raise ValueError(f'OHLC mismatch: {row["date"]} {key}')
    # Never overwrite existing observations, including volume/amount revisions.
    added = [r for r in incoming if r['date'] not in old]
    merged = sorted([*existing, *added], key=lambda r: r['date'])
    return merged, {'overlap': len(overlap), 'added': len(added), 'differences_preserved': differences}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(r'C:\Compass\WavMain\ANALYSE\Data\ChinaStk\Z_SK\day.vdat'))
    parser.add_argument('--target', type=Path, default=ROOT / 'data/core_index/0AMV-2013-2026.csv')
    parser.add_argument('--report-dir', type=Path, default=ROOT / 'back_test_data/compass_amv_cache')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        incoming = parse_daily(args.source.read_bytes())
    except PermissionError:
        parser.exit(1, 'Cannot read day.vdat. Close Compass and retry.\n')
    existing = []
    if args.target.exists():
        with args.target.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                raise ValueError('Unexpected target CSV columns')
            existing = list(reader)
    # A cache saved before market close can contain a provisional daily bar.
    now = datetime.now()
    incoming = [r for r in incoming if r['date'] < now.strftime('%Y-%m-%d')
                or (r['date'] == now.strftime('%Y-%m-%d') and now.hour >= 15
                    and datetime.fromtimestamp(args.source.stat().st_mtime).date() == now.date()
                    and datetime.fromtimestamp(args.source.stat().st_mtime).hour >= 15)]
    merged, report = merge_daily(existing, incoming)
    report.update(source=str(args.source), records=len(incoming), latest=incoming[-1]['date'] if incoming else None,
                  check_only=args.check_only)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    if not args.check_only:
        if args.target.exists():
            backup = args.report_dir / f'{args.target.stem}.{datetime.now():%Y%m%d_%H%M%S_%f}.bak.csv'
            shutil.copy2(args.target, backup)
            report['backup'] = str(backup)
        import pandas as pd
        try:
            from .storage_sqlite import save_dataframe
        except ImportError:
            from storage_sqlite import save_dataframe
        save_dataframe(pd.DataFrame(merged, columns=FIELDS), args.target, category='core_index')
    (args.report_dir / 'daily_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
