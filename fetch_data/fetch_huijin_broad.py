#!/usr/bin/env python3
"""
汇金系宽基 ETF 日线抓取（19 只）。

用途：为分析提供一组固定的"国家队宽基底仓"行情：中央汇金投资与中央汇金资管
重点持有的沪深300 / 上证50 / 中证500 / 中证1000 / 科创50 / 创业板 ETF。

隔离说明：数据写入 category='etf_hj'，与 ETF 选股池（category='etf' +
etf_catalog）互不影响，不会进入 etf_blend20 候选排名。

- 基于 Tushare Pro，fund_daily + fund_adj 前复权
- 从各 ETF 上市日开始，拉到默认结束日期
- 写入 data/etf_hj/{code}_{name}.csv，同时入库

用法：
  python fetch_data/fetch_huijin_broad.py          # 抓取全部 19 只
  python fetch_data/fetch_huijin_broad.py 510300 510500   # 只抓指定代码
  python fetch_data/fetch_huijin_broad.py --list   # 列出清单
"""
import sys
import time
from pathlib import Path

try:
    from .storage_sqlite import initialize, refresh_index, save_dataframe
except ImportError:
    from storage_sqlite import initialize, refresh_index, save_dataframe

try:
    from .trading_date import default_end_date
except ImportError:
    from trading_date import default_end_date

try:
    from . import fetch_etf as base
except ImportError:
    import fetch_etf as base

CATEGORY = 'etf_hj'
DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / CATEGORY

# 中央汇金投资 / 中央汇金资管重点持有的宽基 ETF。
ETFS: list[tuple[str, str]] = [
    ('510300', '沪深300ETF华泰柏瑞'),
    ('510310', '沪深300ETF易方达'),
    ('510330', '沪深300ETF华夏'),
    ('159919', '沪深300ETF嘉实'),
    ('510050', '上证50ETF华夏'),
    ('510100', '上证50ETF易方达'),
    ('510500', '中证500ETF南方'),
    ('512500', '中证500ETF华夏'),
    ('159922', '中证500ETF嘉实'),
    ('512100', '中证1000ETF南方'),
    ('159845', '中证1000ETF华夏'),
    ('560010', '中证1000ETF广发'),
    ('159629', '中证1000ETF富国'),
    ('588000', '科创50ETF华夏'),
    ('588080', '科创50ETF易方达'),
    ('588050', '科创50ETF工银'),
    ('159915', '创业板ETF易方达'),
    ('159977', '创业板ETF天弘'),
    ('159952', '创业板ETF广发'),
]


def ts_code(code: str) -> str:
    return f"{code}.{'SH' if code.startswith('5') else 'SZ'}"


def main():
    if '--list' in sys.argv:
        for code, name in ETFS:
            print(f'{code} {ts_code(code)} {name}')
        return

    targets = [a for a in sys.argv[1:] if not a.startswith('-')]
    items = ETFS
    if targets:
        items = [item for item in ETFS if item[0] in targets or item[1] in targets]
        unknown = sorted(set(targets) - {item[0] for item in items} - {item[1] for item in items})
        if unknown:
            raise ValueError(f"未知 ETF: {', '.join(unknown)}")

    initialize()
    base.setup_tushare()
    end = default_end_date()
    total = 0
    failed = []

    for code, name in items:
        code_ts = ts_code(code)
        print(f'{code_ts} {name}')
        try:
            start = base.fetch_listing_date(code_ts)
            if start > end:
                raise ValueError('ETF 尚未上市')
        except Exception as exc:
            print(f'  [失败] 无法确定上市日期，保留原数据：{exc}')
            failed.append(code)
            continue
        print(f'  上市日期：{start}，拉取至 {end}')
        df = base.fetch_kline(code_ts, start, end)
        if df.empty:
            print('  未取得行情，保留原数据')
            failed.append(code)
            continue
        save_dataframe(df, DATA_DIR / f'{code}_{name}.csv', category=CATEGORY)
        total += len(df)
        print(f'  已保存 {len(df)} 条')
        time.sleep(0.5)

    refresh_index(DATA_DIR, category=CATEGORY)
    print(f'完成，共 {total} 条记录，写入 {CATEGORY}')
    if failed:
        print(f"失败：{', '.join(failed)}")
        raise SystemExit(1)


if __name__ == '__main__':
    main()
