"""Schema and validation for observed Compass intraday snapshots."""
from datetime import datetime
import math


def ensure_schema(db):
    mysql = getattr(db, 'dialect', None) == 'mysql'
    db.execute('''CREATE TABLE IF NOT EXISTS indicator_intraday (
        indicator_id BIGINT NOT NULL, date VARCHAR(10) NOT NULL, time VARCHAR(8) NOT NULL,
        amv DOUBLE NOT NULL, volume_candidate DOUBLE NOT NULL, amount_candidate DOUBLE NOT NULL,
        source_file VARCHAR(255) NOT NULL, source_path VARCHAR(512) NOT NULL,
        PRIMARY KEY(indicator_id,date,time),
        FOREIGN KEY(indicator_id) REFERENCES indicators(id),
        FOREIGN KEY(source_path) REFERENCES source_files(path))''' +
        (' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin' if mysql else ''))
    if not mysql:
        db.execute('CREATE INDEX IF NOT EXISTS indicator_intraday_source ON indicator_intraday(source_path)')


def records(rows, filename):
    day = filename.removesuffix('.csv')
    if datetime.strptime(day, '%Y-%m-%d').strftime('%Y-%m-%d') != day or not rows:
        raise ValueError('Invalid intraday date or empty snapshot')
    result = []
    previous = ''
    for row in rows:
        clock = row['time']
        if (row['date'] != day or clock <= previous or
                datetime.strptime(clock, '%H:%M:%S').strftime('%H:%M:%S') != clock):
            raise ValueError('Intraday date/time mismatch or duplicate/unordered time')
        values = tuple(float(row[key]) for key in ('amv', 'volume_candidate', 'amount_candidate'))
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError('Invalid intraday values')
        result.append((day, clock, *values, row['source_file']))
        previous = clock
    return result
