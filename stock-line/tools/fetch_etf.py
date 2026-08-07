#!/usr/bin/env python3
"""
热门ETF日K线数据抓取脚本
- 基于 Tushare Pro，前复权日线
- 内置近6年热门板块的经典 ETF（规模大、流动性好）
- 时间从 2013-01-04 至今
- 保存到 ../public/data/etf/{板块}_{简称}_{code}.csv

用法：
  python tools/fetch_etf.py                          # 抓取所有板块
  python tools/fetch_etf.py 白酒 半导体              # 只抓取指定板块
  python tools/fetch_etf.py --list                   # 列出可抓取的板块
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
DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data" / "etf"

# ---------- 板块 → 经典ETF代码（按成交活跃度、规模优选） ----------
# 格式: (ts_code, 简称)
SECTOR_ETFS = {
    "沪深300": [
        ("510300.SH", "华泰柏瑞沪深300ETF"),
        ("159919.SZ", "嘉实沪深300ETF"),
    ],
    "上证50": [
        ("510050.SH", "华夏上证50ETF"),
        ("510850.SH", "工银上证50ETF"),
    ],
    "中证2000": [
        ("563300.SH", "华泰柏瑞中证2000ETF"),
        ("159531.SZ", "南方中证2000ETF"),
    ],
    "白酒": [
        ("512690.SH", "鹏华中证酒ETF"),
    ],
    "半导体": [
        ("512480.SH", "国联安中证半导体ETF"),
        ("512760.SH", "国泰CES半导体芯片ETF"),
    ],
    "通信": [
        ("515880.SH", "国泰中证全指通信设备ETF"),
        ("159994.SZ", "银华中证5G通信主题ETF"),
    ],
    "新能源": [
        ("516160.SH", "南方中证新能源ETF"),
        ("159875.SZ", "嘉实中证新能源ETF"),
    ],
    "新能源车": [
        ("515030.SH", "华夏中证新能源汽车ETF"),
    ],
    "消费": [
        ("159928.SZ", "汇添富中证主要消费ETF"),
        ("510150.SH", "招商上证消费80ETF"),
    ],
    "医药": [
        ("512010.SH", "易方达沪深300医药ETF"),
        ("159929.SZ", "汇添富中证医药卫生ETF"),
    ],
    "军工": [
        ("512660.SH", "国泰中证军工ETF"),
        ("512670.SH", "鹏华中证国防ETF"),
    ],
    "证券": [
        ("512880.SH", "国泰中证全指证券公司ETF"),
        ("159841.SZ", "天弘中证全指证券公司ETF"),
    ],
    "银行": [
        ("512800.SH", "华宝中证银行ETF"),
        ("159887.SZ", "华夏中证银行ETF"),
    ],
    "煤炭": [
        ("515220.SH", "国泰中证煤炭ETF"),
    ],
    "有色": [
        ("512400.SH", "南方中证申万有色金属ETF"),
    ],
    "创业板人工智能": [
        ("159381.SZ", "华夏创业板人工智能ETF"),
    ],
    "创业板": [
        ("159915.SZ", "易方达创业板ETF"),
        ("159952.SZ", "广发创业板ETF"),
    ],
    "科创半导体设备": [
        ("588710.SH", "嘉实上证科创板半导体设备材料ETF"),
    ],
    "机器人": [
        ("159530.SZ", "华夏中证机器人ETF"),
        ("562500.SH", "华夏中证机器人ETF"),
    ],
    "创新药": [
        ("510660.SH", "华夏上证科创板生物医药ETF"),
    ],
    "游戏": [
        ("159869.SZ", "华夏中证动漫游戏ETF"),
    ],
    "光伏": [
        ("516290.SH", "华泰柏瑞中证光伏产业ETF"),
    ],
    "电网设备": [
        ("561380.SH", "银华中证电网设备主题ETF"),
    ],
    "卫星": [
        ("159206.SZ", "华泰柏瑞中证卫星产业ETF"),
    ],
    "高端装备": [
        ("159638.SZ", "嘉实中证高端装备细分50ETF"),
    ],
    "软件": [
        ("515230.SH", "国泰中证全指软件ETF"),
    ],
    "传媒": [
        ("512980.SH", "广发中证传媒ETF"),
    ],
}


def setup_tushare():
    os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    ts.set_token(TOKEN)


def fetch_adj_factor(ts_code: str, start: str, end: str) -> pd.DataFrame:
    """获取 ETF 复权因子（fund_adj 接口）"""
    try:
        df = ts.pro_api().fund_adj(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[["trade_date", "adj_factor"]].copy()
        df["date"] = pd.to_datetime(df["trade_date"])
        df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce")
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
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
        df = ts.pro_api().fund_daily(ts_code=ts_code, start_date=start, end_date=end)
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
        print(f"    [失败] {ts_code}: {e}")
        return pd.DataFrame()


def main():
    # ---- 参数解析 ----
    if "--list" in sys.argv:
        print("可抓取的板块：")
        for s in SECTOR_ETFS:
            codes = ", ".join(c for c, _ in SECTOR_ETFS[s])
            print(f"  {s}: {codes}")
        return

    target_sectors = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not target_sectors:
        target_sectors = list(SECTOR_ETFS.keys())

    # ---- 初始化 ----
    setup_tushare()
    end = dt.date.today().strftime("%Y%m%d")
    start = START_DEFAULT

    # ---- 逐板块抓取 ----
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    for sector in target_sectors:
        if sector not in SECTOR_ETFS:
            print(f"\n未知板块: {sector}，跳过")
            continue

        etfs = SECTOR_ETFS[sector]
        print(f"\n{'='*60}")
        print(f"【{sector}】")

        best_df: pd.DataFrame = pd.DataFrame()
        best_name = ""
        best_code = ""
        best_ts_code = ""

        for ts_code, name in etfs:
            code = ts_code.split(".")[0]
            print(f"  {ts_code} {name}")
            df = fetch_kline(ts_code, start, end)

            if df.empty:
                print(f"    - 无数据")
                continue

            cnt = len(df)
            print(f"    ✓ {cnt} 条  {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")

            if cnt > len(best_df):
                best_df = df
                best_name = name
                best_code = code
                best_ts_code = ts_code

            time.sleep(0.5)  # 避免请求过快

        if best_df.empty:
            print(f"    该板块无可用数据")
            continue

        # 统一输出文件名: {code}_{板块}ETF.csv，不保留基金公司名
        short_name = f"{sector}ETF"
        filename = f"{best_code}_{short_name}.csv"
        out_path = DATA_DIR / filename
        best_df.to_csv(out_path, index=False)
        total += len(best_df)
        print(f"  → 保留日K最多: {best_ts_code} {best_name}，共 {len(best_df)} 条")
        print(f"    保存: {out_path}")

    if total:
        print(f"\n{'='*60}")
        print(f"全部完成！共抓取 {total} 条记录")
        print(f"保存至: {DATA_DIR.resolve()}")
    else:
        print("\n未抓取到任何数据")


if __name__ == "__main__":
    main()
