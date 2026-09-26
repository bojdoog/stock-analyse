"""Read observed Compass 0AMV 2ACR intraday caches; never modify source files.

Layout inferred from local files, not an official specification. The last two
floats appear to be cumulative volume/amount; their units remain unverified.
These intraday snapshots are not complete daily OHLC bars.
"""

import argparse
import csv
import json
import math
import struct
from itertools import groupby
from datetime import datetime
from pathlib import Path


def parse_fde(path):
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError('Truncated header')
    magic, date, record_size, end_time, payload_size = struct.unpack_from('<4s4I', data)
    if magic != b'2ACR' or record_size != 16:
        raise ValueError('Unsupported format or record size')
    if payload_size != len(data) - 20 or payload_size % record_size:
        raise ValueError('Payload length mismatch')
    day = datetime.strptime(str(date), '%Y%m%d').strftime('%Y-%m-%d')
    rows = []
    previous_time = -1
    for clock, value, volume, amount in struct.iter_unpack('<Ifff', data[20:]):
        hour, minute, second = clock // 10000, clock // 100 % 100, clock % 100
        if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
            raise ValueError(f'Invalid time: {clock}')
        if clock <= previous_time or not all(math.isfinite(x) and x >= 0 for x in (value, volume, amount)):
            raise ValueError('Invalid record ordering or values')
        rows.append({
            'date': day, 'time': f'{hour:02}:{minute:02}:{second:02}',
            'amv': value, 'volume_candidate': volume, 'amount_candidate': amount,
            'source_file': path.name,
        })
        previous_time = clock
    return rows, {'source_file': path.name, 'date': day, 'records': len(rows),
                  'header_end_time': end_time, 'first_time': rows[0]['time'] if rows else None,
                  'last_time': rows[-1]['time'] if rows else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(r'C:\Compass\WavMain\Temp'))
    parser.add_argument('--output', type=Path, default=Path('back_test_data/compass_amv_cache'))
    parser.add_argument('--split-by-date', action='store_true', help='Write YYYY-MM-DD.csv for each date')
    args = parser.parse_args()
    rows, files, errors = [], [], []
    for path in sorted(args.source.glob('Z_SK0AMV*.fde')):
        try:
            records, metadata = parse_fde(path)
            rows.extend(records)
            files.append(metadata)
        except (OSError, ValueError, struct.error) as error:
            errors.append({'source_file': path.name, 'error': str(error)})
    if not rows:
        raise SystemExit(f'No readable records: {errors}')
    rows.sort(key=lambda row: (row['date'], row['time'], row['source_file']))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.split_by_date:
        keys = [(row['date'], row['time']) for row in rows]
        if len(keys) != len(set(keys)):
            raise SystemExit('Duplicate date/time records; resolve overlapping source caches before export')
        targets = ((args.output / f'{day}.csv', records)
                   for day, records in groupby(rows, key=lambda row: row['date']))
    else:
        targets = [(args.output / '0AMV_intraday.csv', rows)]
    output_files = 0
    for target, records in targets:
        with target.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(records)
        output_files += 1
    report = {
        'format': '2ACR: 20-byte header (<4s4I), 16-byte records (<Ifff)',
        'limitations': ['Intraday snapshots, not daily OHLC; may omit closing data.',
                        'Volume/amount field meanings and units are inferred, not verified.',
                        'CDE and locked VDAT files are not parsed by this script.'],
        'records': len(rows), 'output_files': output_files, 'files': files, 'errors': errors,
    }
    (args.output / 'parse_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Exported {len(rows)} records from {len(files)} files to {args.output} ({output_files} CSV files); errors={len(errors)}')


if __name__ == '__main__':
    main()
