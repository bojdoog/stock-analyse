#!/usr/bin/env python3
"""
指数日K线数据抓取脚本
- 基于 Tushare Pro，使用 index_daily 接口
- 默认抓取上证指数(000001.SH)、沪深300(000300.SH)
- 时间从 2013-01-04 至今
- 保存到 ../public/data/index/{指数代码}.csv

用法：
  python tools/fetch_index.py                    # 抓取默认指数
  python tools/fetch_index.py 000001 399006      # 抓取指定指数代码
  python tools/fetch_index.py --list             # 列出常见指数代码
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
DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data" / "index"

# ---------- 常见指数代码 ----------
COMMON_INDEXES = {
    "000001": ("000001.SH", "上证指数"),
    "000300": ("000300.SH", "沪深300"),
    "000016": ("000016.SH", "上证50"),
    "000905": ("000905.SH", "中证500"),
    "000852": ("000852.SH", "中证1000"),
    "399001": ("399001.SZ", "深证成指"),
    "399006": ("399006.SZ", "创业板指"),
    "399005": ("399005.SZ", "中小板指"),
    "000688": ("000688.SH", "科创50"),
    "000010": ("000010.SH", "上证180"),
    "000009": ("000009.SH", "上证380"),
    "399673": ("399673.SZ", "创业板50"),
    "000015": ("000015.SH", "红利指数"),
    "000922": ("000922.SH", "中证红利"),
}


def setup_tushare():
    os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    ts.set_token(TOKEN)


def to_ts_code(code: str) -> str:
    """把6位指数代码映射到标准 ts_code 后缀"""
    code = str(code).zfill(6)
    if code.startswith(("0", "9")):
        return f"{code}.SH"
    else:
        return f"{code}.SZ"


def fetch_index_kline(ts_code: str, start: str, end: str) -> pd.DataFrame:
    """抓取单只指数日K线（使用 index_daily 接口）"""
    try:
        df = ts.pro_api().index_daily(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"trade_date": "date", "vol": "volume"})[
            ["date", "open", "close", "high", "low", "volume"]
        ].copy()
        df["date"] = pd.to_datetime(df["date"])
        for c in ["open", "close", "high", "low", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        print(f"    [失败] {ts_code}: {e}")
        return pd.DataFrame()


def main():
    # ---- 参数解析 ----
    if "--list" in sys.argv:
        print("常见指数代码：")
        for code, (ts_code, name) in COMMON_INDEXES.items():
            print(f"  {code}  {ts_code}  {name}")
        return

    # 解析参数
    codes = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not codes:
        # 默认抓取上证指数和沪深300
        codes = ["000001", "000300"]

    # ---- 初始化 ----
    setup_tushare()
    end = dt.date.today().strftime("%Y%m%d")
    start = START_DEFAULT

    # ---- 逐指数抓取 ----
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    print(f"开始抓取 {len(codes)} 只指数...")
    print("=" * 60)

    for code in codes:
        # 标准化代码
        if code in COMMON_INDEXES:
            ts_code, name = COMMON_INDEXES[code]
        else:
            ts_code = to_ts_code(code)
            name = "未知指数"

        print(f"\n【{code}】{name} ({ts_code})")
        df = fetch_index_kline(ts_code, start, end)

        if df.empty:
            print(f"  - 无数据")
            continue

        # 保存，统一文件名: {code}_{名称}.csv
        filename = f"{code}_{name}.csv"
        out_path = DATA_DIR / filename
        df.to_csv(out_path, index=False)

        cnt = len(df)
        total += cnt
        print(f"  ✓ {cnt} 条记录")
        print(f"    日期范围: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")
        print(f"    保存: {out_path}")

        time.sleep(0.3)  # 避免请求过快

    if total:
        print(f"\n{'='*60}")
        print(f"全部完成！共抓取 {total} 条记录")
        print(f"保存至: {DATA_DIR.resolve()}")
    else:
        print("\n未抓取到任何数据")


if __name__ == "__main__":
    main()
