#!/usr/bin/env python3
"""
汇金系宽基 ETF 分时数据抓取（新浪财经 1 分钟线）。

- 每只 ETF 一次请求，返回最近约 5 个交易日的 1 分钟行情
- 成交量统一换算为手，与日线口径一致
- 入库到 etf_intraday 表（按 code+date+time 去重覆盖）
- 同时导出 data/etf_mins/{code}_{name}.csv（该 ETF 全部分时历史）

因为免费接口只提供最近几天，脚本每天跑一次即可逐步积累历史。

用法：
  python fetch_data/fetch_etf_mins.py
"""
import sys
import time
from pathlib import Path

try:
    from .storage_sqlite import initialize
except ImportError:
    from storage_sqlite import initialize

try:
    from .fetch_huijin_broad import ETFS
except ImportError:
    from fetch_huijin_broad import ETFS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data' / 'etf_mins'
HEADER = ['date', 'time', 'open', 'high', 'low', 'close', 'volume', 'amount']


def export(db, code, name):
    import pandas as pd
    rows = db.execute('SELECT date, time, open, high, low, close, volume, amount FROM etf_intraday '
                      'WHERE code=? ORDER BY date, time', (code,)).fetchall()
    pd.DataFrame([dict(row) for row in rows], columns=HEADER).to_csv(
        DATA_DIR / f'{code}_{name}.csv', index=False, encoding='utf-8-sig')
    return len(rows)


def main():
    import etf_intraday
    from market_store import connect

    targets = [a for a in sys.argv[1:] if not a.startswith('-')]
    items = [item for item in ETFS if not targets or item[0] in targets]
    if not items:
        raise ValueError(f"未知 ETF: {', '.join(targets)}")

    initialize()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    days = set()

    with connect() as db:
        etf_intraday.ensure_schema(db)
        db.commit()
        purged = etf_intraday.purge_partial(db)
        db.commit()
        if purged:
            print(f'清理残日记录 {purged} 个（不足 {etf_intraday.MIN_MINUTES} 分钟的截断日）')
        for index, (code, name) in enumerate(items, start=1):
            try:
                raw = etf_intraday.fetch(code)
            except Exception as exc:
                print(f'[{index}/{len(items)}] {code} {name} 失败：{exc}')
                failed.append(code)
                time.sleep(3)
                continue
            fetched = etf_intraday.usable_days(raw)
            dropped = sorted(day for day in raw if day not in fetched)
            rows = [row for day in sorted(fetched) for row in fetched[day]]
            etf_intraday.upsert(db, code, rows)
            db.commit()
            days.update(fetched)
            total = export(db, code, name)
            extra = f'，丢弃截断日 {",".join(dropped)}' if dropped else ''
            print(f'[{index}/{len(items)}] {code} {name} 本次 {len(rows)} 条（{len(fetched)} 天），累计 {total} 条{extra}')
            time.sleep(0.6)

    print(f'完成：{len(items) - len(failed)} 只成功，{len(failed)} 只失败，覆盖日期 {", ".join(sorted(days))}')
    if failed:
        print(f"失败：{', '.join(failed)}")
        raise SystemExit(1)


if __name__ == '__main__':
    main()
