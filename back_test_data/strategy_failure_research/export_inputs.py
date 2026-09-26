"""Snapshot current database inputs and the UI ETF universe for default-strategy attribution."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'flask_backend'))
from market_store import connect

page = (ROOT / 'stock-line/src/pages/ActiveMarket/index.tsx').read_text(encoding='utf-8')
options = re.findall(r"value: '([^']+)', label: '([^']+)', file: '([^']+)'", page)
with connect() as db:
    amv = [dict(row) for row in db.execute('''SELECT date,open,high,low,close,volume,amount
        FROM indicator_daily WHERE indicator_id=(SELECT id FROM indicators WHERE code=?) ORDER BY date''', ('0AMV',))]
    etfs = []
    for code, name, filename in options:
        if not filename.startswith('etf/'):
            continue
        rows = [dict(row) for row in db.execute('''SELECT date,open,high,low,close,volume,amount
            FROM daily_bars WHERE category=? AND code=? ORDER BY date''', ('etf', code))]
        etfs.append({'id': code, 'name': name, 'data': rows})
target = Path(__file__).with_name('inputs.json')
target.write_text(json.dumps({'amv': amv, 'etfs': etfs}, ensure_ascii=False), encoding='utf-8')
print(f'Exported {len(amv)} AMV days and {len(etfs)} ETF histories')
