#!/usr/bin/env python3
"""
个股日K线数据抓取脚本
- 基于 Tushare Pro，前复权日线
- 默认抓取 000001（平安银行），从 2013-01-04 至今
- 保存到 ../public/data/stock/{code}.csv

用法：
  python tools/fetch_one.py                  # 抓取 000001
  python tools/fetch_one.py 600519           # 抓取贵州茅台
  python tools/fetch_one.py 000001 20250101  # 抓取 000001 从2025-01-01开始
"""
import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
import tushare as ts

# ---------- 配置 ----------
TOKEN = "eb0e5fcfd014dfb595b4ca773f42d29570a3fb06edcca84fe19830db"
START_DEFAULT = "20130104"
DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data" / "stock"


def to_ts_code(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"{code}.SH"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def fetch_one(code: str, start: str, end: str) -> pd.DataFrame:
    ts_code = to_ts_code(code)
    print(f"  请求 {ts_code}  [{start} ~ {end}]")
    df = ts.pro_bar(ts_code=ts_code, adj="qfq", start_date=start, end_date=end, freq="D")

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"trade_date": "date", "vol": "volume"})[
        ["date", "open", "close", "high", "low", "volume"]
    ].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def main():
    # 参数
    code = sys.argv[1] if len(sys.argv) >= 2 else "000001"
    start = sys.argv[2] if len(sys.argv) >= 3 else START_DEFAULT
    end = dt.date.today().strftime("%Y%m%d")

    # 初始化 Tushare
    os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    ts.set_token(TOKEN)

    # 抓取
    print(f"抓取 {code} 日K线数据...")
    df = fetch_one(code, start, end)

    if df.empty:
        print(f"  无数据，请检查股票代码是否正确")
        sys.exit(1)

    # 保存
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{code}.csv"
    df.to_csv(out_path, index=False)
    print(f"  完成！共 {len(df)} 条记录")
    print(f"  日期范围: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")
    print(f"  保存到: {out_path.resolve()}")


if __name__ == "__main__":
    main()
