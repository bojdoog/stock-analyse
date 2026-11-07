#!/usr/bin/env python3
"""
热门ETF日K线数据抓取脚本
- 基于 Tushare Pro，前复权日线
- 从数据库读取启用的 ETF 清单
- 时间从各 ETF 上市日期至今
- 保存到 ../public/data/etf/{板块}_{简称}_{code}.csv

用法：
  python fetch_data/fetch_etf.py                          # 抓取所有板块
  python fetch_data/fetch_etf.py 白酒 半导体              # 只抓取指定板块
  python fetch_data/fetch_etf.py --list                   # 列出可抓取的板块
"""
import datetime as dt
import os
import sys
import time
from pathlib import Path

try:
    from .storage_sqlite import save_dataframe, refresh_index, list_files, initialize, read_frame, has_file
except ImportError:
    from storage_sqlite import save_dataframe, refresh_index, list_files, initialize, read_frame, has_file

try:
    from .trading_date import default_end_date
except ImportError:
    from trading_date import default_end_date

from etf_catalog import list_etfs

import pandas as pd
try:
    from .tushare_client import create_client
except ImportError:
    from tushare_client import create_client

pro = None

# ---------- 配置 ----------
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "etf"

# ETF 清单由 etf_catalog 统一管理。


try:
    from .permission_errors import skip_if_permission_denied
except ImportError:
    from permission_errors import skip_if_permission_denied


def setup_tushare():
    global pro
    pro = create_client()


def fetch_listing_date(ts_code: str) -> str:
    """Use exchange listing date, never fund inception or first cached bar."""
    frame = pro.fund_basic(ts_code=ts_code, market='E', fields='ts_code,list_date')
    if frame is None or not {'ts_code', 'list_date'}.issubset(frame.columns):
        raise ValueError('未取得 ETF 上市日期')
    dates = frame.loc[frame['ts_code'] == ts_code, 'list_date'].dropna().astype(str).unique()
    if len(dates) != 1 or len(dates[0]) != 8 or not dates[0].isdigit():
        raise ValueError('ETF 上市日期缺失或不唯一')
    dt.datetime.strptime(dates[0], '%Y%m%d')
    return dates[0]


def fetch_adj_factor(ts_code: str, start: str, end: str) -> pd.DataFrame:
    """获取 ETF 复权因子（fund_adj 接口）"""
    try:
        df = pro.fund_adj(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[["trade_date", "adj_factor"]].copy()
        df["date"] = pd.to_datetime(df["trade_date"])
        df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce")
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        skip_if_permission_denied(e, 'fund_adj')
        print(f"    [复权因子失败] {ts_code}: {e}")
        return pd.DataFrame()


def adjust_prices(df: pd.DataFrame, adj_df: pd.DataFrame) -> pd.DataFrame:
    """
    用复权因子计算前复权价格
    前复权 = 当日价格 * 当日复权因子 / 最新复权因子
    """
    if adj_df is None or adj_df.empty:
        return df

    merged = df.merge(adj_df[["date", "adj_factor"]], on="date", how="left")
    merged["adj_factor"] = merged["adj_factor"].ffill().bfill()

    latest_adj = merged["adj_factor"].iloc[-1]
    if not pd.notna(latest_adj) or latest_adj == 0:
        return df

    for col in ["open", "close", "high", "low"]:
        merged[col] = merged[col] * merged["adj_factor"] / latest_adj

    return merged[["date", "open", "close", "high", "low", "volume"]]


def fetch_kline(ts_code: str, start: str, end: str, adjust: bool = True) -> pd.DataFrame:
    """抓取单只ETF日K线（使用 fund_daily 接口，默认前复权）"""
    try:
        df = pro.fund_daily(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"trade_date": "date", "vol": "volume"})[
            ["date", "open", "close", "high", "low", "volume"]
        ].copy()
        df["date"] = pd.to_datetime(df["date"])
        for c in ["open", "close", "high", "low", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)

        if adjust:
            adj_df = fetch_adj_factor(ts_code, start, end)
            if not adj_df.empty:
                df = adjust_prices(df, adj_df)
                print(f"      已应用前复权")
            else:
                print(f"      未获取到复权因子，使用原始价格")

        return df
    except Exception as e:
        skip_if_permission_denied(e, 'fund_daily')
        print(f"    [失败] {ts_code}: {e}")
        return pd.DataFrame()


def main():
    initialize()
    items = list_etfs()
    if "--list" in sys.argv:
        for item in items:
            print(f"{item['ts_code']} {item['name']}")
        return
    targets = [a for a in sys.argv[1:] if not a.startswith("-")]
    if targets:
        def matches(item, target):
            return target in (item['code'], item['ts_code'], item['name'], item['name'].removesuffix('ETF'))
        unknown = [t for t in targets if not any(matches(i, t) for i in items)]
        if unknown:
            raise ValueError(f"未启用或未知 ETF: {', '.join(unknown)}")
        items = [i for i in items if any(matches(i, t) for t in targets)]
    if not items:
        raise ValueError('数据库没有启用的 ETF，请先初始化 ETF 清单')
    setup_tushare()
    end = default_end_date()
    total = 0
    failed = []
    for item in items:
        print(f"{item['ts_code']} {item['name']}")
        try:
            start = fetch_listing_date(item['ts_code'])
            if start > end:
                raise ValueError('ETF 尚未上市')
        except Exception as exc:
            skip_if_permission_denied(exc, 'fund_basic')
            print(f"  [失败] 无法确定上市日期，保留原数据：{exc}")
            failed.append(item['ts_code'])
            continue
        print(f"  上市日期：{start}，拉取至 {end}")
        df = fetch_kline(item['ts_code'], start, end)
        if df.empty:
            print('  未取得行情，保留原数据')
            failed.append(item['ts_code'])
            continue
        # Stable registered source path, independent of the display name.
        out_path = DATA_DIR.parent / item['source_path']
        save_dataframe(df, out_path, category='etf')
        total += len(df)
        print(f"  已保存 {len(df)} 条")
        time.sleep(0.5)
    refresh_index(DATA_DIR, category='etf')
    print(f"完成，共 {total} 条记录")
    if failed:
        print(f"失败：{', '.join(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
