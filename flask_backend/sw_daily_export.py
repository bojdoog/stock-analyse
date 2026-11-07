"""Export normalized SW candles as one CSV per day from database snapshots."""
import io
from pathlib import Path
import pandas as pd
from market_store import connect


def export_daily(output_dir, database=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with connect(database) as db:
        sources = db.execute("SELECT content FROM source_files WHERE category='sw_index' ORDER BY path").fetchall()
    if not sources:
        return {'files': 0, 'rows': 0}
    frame = pd.concat([pd.read_csv(io.BytesIO(row['content']), dtype={'trade_date': str})
                       for row in sources], ignore_index=True)
    if frame.duplicated(['date', 'ts_code']).any():
        raise ValueError('Duplicate SW industry/day observations')
    count = 0
    for date, daily in frame.groupby('date', sort=True):
        name = pd.Timestamp(date).strftime('%Y%m%d') + '.csv'
        target = output_dir / name
        content = daily.sort_values('ts_code').to_csv(index=False).encode('utf-8-sig')
        if not target.exists() or target.read_bytes() != content:
            temporary = target.with_suffix('.csv.tmp')
            temporary.write_bytes(content)
            temporary.replace(target)
        count += 1
    return {'files': count, 'rows': len(frame)}
