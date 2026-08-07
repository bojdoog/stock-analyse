#!/usr/bin/env python3
"""
活跃市值(0AMV)多空区间策略回测

规则：
1. 根据 0AMV 日K识别多头/空头区间（与前端 KLineChart 逻辑一致）
2. 多头区间确认启动当天收盘，买入启动日涨幅前5的板块 ETF：
   仓位分配 30%, 30%, 20%, 10%, 10%
3. 持有多头组合至该多头区间结束当日收盘卖出
4. 进入空头区间后买入银行 ETF（512800），持有至空头区间结束当日收盘卖出
5. 统计每年（以 1 月 1 日为界）的收益率；跨年交易的收益全部计入开始年份

用法：
  python tools/backtest_zones.py
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
AMV_FILE = BASE_DIR / "public" / "0AMV-2013-2026.csv"

# 板块 ETF 选项（排除指数）
ETF_OPTIONS = [
    ("510050", "上证50ETF"),
    ("510300", "沪深300ETF"),
    ("563300", "中证2000ETF"),
    ("159915", "创业板ETF"),
    ("512480", "半导体ETF"),
    ("588710", "科创半导体设备ETF"),
    ("515880", "通信ETF"),
    ("159381", "创业板人工智能ETF"),
    ("516160", "新能源ETF"),
    ("515030", "新能源车ETF"),
    ("512400", "有色ETF"),
    ("510150", "消费ETF"),
    ("515220", "煤炭ETF"),
    ("512690", "白酒ETF"),
    ("512880", "证券ETF"),
    ("512800", "银行ETF"),
    ("562500", "机器人ETF"),
    ("510660", "创新药ETF"),
    ("159869", "游戏ETF"),
    ("516290", "光伏ETF"),
    ("561380", "电网设备ETF"),
    ("159206", "卫星ETF"),
    ("159638", "高端装备ETF"),
    ("512660", "军工ETF"),
    ("159929", "医药ETF"),
]

WEIGHTS = [0.30, 0.30, 0.20, 0.10, 0.10]
BANK_ETF_NAME = "银行ETF"


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def calc_ma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(window=n, min_periods=n).mean()


def identify_zones(amv: pd.DataFrame):
    """
    复现前端 KLineChart 的多空区间识别逻辑。
    返回:
      zones: list[dict] 每个元素含 start_idx, end_idx, start_date, end_date, type
    """
    data = amv.to_dict("records")
    ma10 = calc_ma(amv["close"], 10)

    special_marks = []
    bull_zones = []
    is_bull_zone = False
    last_bull_mark_index = -1
    current_bull_start = -1

    for i, item in enumerate(data):
        change = 0.0
        if i > 0:
            prev = data[i - 1]
            change = (item["close"] - prev["close"]) / prev["close"] * 100

        bull_start = False
        two_day_bull = False

        if change > 4:
            bull_start = True
        elif change > 0 and i > 1:
            prev = data[i - 1]
            prev_prev = data[i - 2]
            prev_change = (prev["close"] - prev_prev["close"]) / prev_prev["close"] * 100
            if prev_change > 0 and change + prev_change > 4:
                bull_start = True
                two_day_bull = True

        if bull_start and not is_bull_zone:
            if two_day_bull and i - 1 > last_bull_mark_index:
                special_marks.append({"index": i - 1, "type": "bull"})
            special_marks.append({"index": i, "type": "bull"})
            last_bull_mark_index = i
            is_bull_zone = True
            current_bull_start = i
            continue

        if is_bull_zone:
            ma10_value = ma10.iloc[i]
            break_ma10 = pd.notna(ma10_value) and item["close"] < ma10_value
            if change < -2.3 or break_ma10:
                special_marks.append({"index": i, "type": "bear"})
                is_bull_zone = False
                bull_zones.append({"start": current_bull_start, "end": i})
                current_bull_start = -1

    if is_bull_zone and current_bull_start >= 0:
        bull_zones.append({"start": current_bull_start, "end": len(data) - 1})

    # 计算空头区间（多头区间以外的区域）
    bear_zones = []
    current_bear_start = -1
    for i in range(len(data)):
        in_bull = any(z["start"] <= i <= z["end"] for z in bull_zones)
        if not in_bull:
            if current_bear_start == -1:
                current_bear_start = i
        else:
            if current_bear_start != -1:
                bear_zones.append({"start": current_bear_start, "end": i - 1})
                current_bear_start = -1
    if current_bear_start != -1:
        bear_zones.append({"start": current_bear_start, "end": len(data) - 1})

    zones = []
    for z in bull_zones:
        zones.append({
            "start_idx": z["start"],
            "end_idx": z["end"],
            "start_date": data[z["start"]]["date"],
            "end_date": data[z["end"]]["date"],
            "type": "bull",
        })
    for z in bear_zones:
        zones.append({
            "start_idx": z["start"],
            "end_idx": z["end"],
            "start_date": data[z["start"]]["date"],
            "end_date": data[z["end"]]["date"],
            "type": "bear",
        })

    zones.sort(key=lambda x: x["start_idx"])
    return zones


def get_close(df: pd.DataFrame, dt: pd.Timestamp) -> float | None:
    row = df[df["date"] == dt]
    if row.empty:
        return None
    return float(row.iloc[0]["close"])


def get_prev_date(amv: pd.DataFrame, dt: pd.Timestamp) -> pd.Timestamp | None:
    prev_rows = amv[amv["date"] < dt]
    if prev_rows.empty:
        return None
    return prev_rows.iloc[-1]["date"]


def backtest(amv: pd.DataFrame, etf_data: dict[str, pd.DataFrame], zones: list[dict]):
    """执行回测，返回交易记录与年度收益。"""
    trades = []

    for zone in zones:
        start_date = zone["start_date"]
        end_date = zone["end_date"]

        if zone["type"] == "bull":
            # 计算启动日（start_date）各 ETF 相对前一天的涨幅
            prev_date = get_prev_date(amv, start_date)
            if prev_date is None:
                continue

            gains = []
            for name, df in etf_data.items():
                if name == BANK_ETF_NAME:
                    continue
                prev_close = get_close(df, prev_date)
                start_close = get_close(df, start_date)
                if prev_close is None or start_close is None or prev_close == 0:
                    continue
                day_change = (start_close - prev_close) / prev_close * 100
                gains.append({"name": name, "day_change": day_change})

            top5 = sorted(gains, key=lambda x: x["day_change"], reverse=True)[:5]
            if len(top5) < 5:
                print(f"[WARN] 多头区间 {start_date.date()} 可选 ETF 不足 5 只，实际 {len(top5)} 只")

            # 计算持有期收益
            total_return = 0.0
            holdings = []
            for idx, item in enumerate(top5):
                weight = WEIGHTS[idx]
                df = etf_data[item["name"]]
                start_close = get_close(df, start_date)
                end_close = get_close(df, end_date)
                if start_close is None or end_close is None or start_close == 0:
                    continue
                holding_return = end_close / start_close - 1
                total_return += weight * holding_return
                holdings.append({
                    "name": item["name"],
                    "weight": weight,
                    "day_change": item["day_change"],
                    "holding_return": holding_return,
                })

            trades.append({
                "type": "bull",
                "start_date": start_date,
                "end_date": end_date,
                "year": start_date.year,
                "return": total_return,
                "holdings": holdings,
            })

        else:
            # 空头区间买入银行 ETF
            df = etf_data.get(BANK_ETF_NAME)
            if df is None:
                continue
            start_close = get_close(df, start_date)
            end_close = get_close(df, end_date)
            if start_close is None or end_close is None or start_close == 0:
                continue
            holding_return = end_close / start_close - 1
            trades.append({
                "type": "bear",
                "start_date": start_date,
                "end_date": end_date,
                "year": start_date.year,
                "return": holding_return,
                "holdings": [{"name": BANK_ETF_NAME, "weight": 1.0, "holding_return": holding_return}],
            })

    return trades


def aggregate_by_year(trades: list[dict], start_year: int = 2019):
    """按开始年份聚合收益，跨年交易收益全部计入开始年份。"""
    trades_sorted = sorted(trades, key=lambda x: x["start_date"])

    # 初始化每年净值
    year_nav = {}
    current_nav = 1.0
    for t in trades_sorted:
        y = t["year"]
        if y not in year_nav:
            year_nav[y] = current_nav
        year_nav[y] *= (1 + t["return"])
        current_nav = year_nav[y]

    # 补齐 start_year 到最新年份
    all_years = list(range(start_year, datetime.now().year + 1))
    results = []
    prev_year_end_nav = 1.0
    for y in all_years:
        if y in year_nav:
            end_nav = year_nav[y]
        else:
            end_nav = prev_year_end_nav
        annual_return = end_nav / prev_year_end_nav - 1
        results.append({
            "year": y,
            "start_nav": round(prev_year_end_nav, 4),
            "end_nav": round(end_nav, 4),
            "annual_return": round(annual_return * 100, 2),
        })
        prev_year_end_nav = end_nav

    return results


def print_trades(trades: list[dict]):
    print("\n交易明细：")
    print("-" * 100)
    for t in trades:
        sign = "+" if t["return"] >= 0 else ""
        print(
            f"{t['type'].upper():4} {t['start_date'].date()} ~ {t['end_date'].date()} "
            f"收益: {sign}{t['return']*100:.2f}%"
        )
        for h in t["holdings"]:
            print(
                f"     {h['name']:12s} 权重:{h['weight']*100:4.0f}% "
                f"启动日涨幅:{h.get('day_change', 0):+.2f}% 区间收益:{h['holding_return']*100:+.2f}%"
            )


def main():
    print("加载活跃市值数据...")
    amv = load_csv(AMV_FILE)
    amv = amv[amv["date"] >= "2019-01-01"].reset_index(drop=True)

    print("加载 ETF 数据...")
    etf_data = {}
    for code, name in ETF_OPTIONS:
        path = DATA_DIR / "etf" / f"{code}_{name}.csv"
        if path.exists():
            etf_data[name] = load_csv(path)
        else:
            print(f"  [跳过] 文件不存在: {path}")

    print("识别多空区间...")
    zones = identify_zones(amv)
    bull_count = sum(1 for z in zones if z["type"] == "bull")
    bear_count = sum(1 for z in zones if z["type"] == "bear")
    print(f"  多头区间: {bull_count} 个，空头区间: {bear_count} 个")

    print("执行回测...")
    trades = backtest(amv, etf_data, zones)

    print_trades(trades)

    print("\n年度收益统计（跨年交易收益计入开始年份）：")
    print("-" * 60)
    results = aggregate_by_year(trades, start_year=2019)
    total_return = 1.0
    for r in results:
        total_return *= (1 + r["annual_return"] / 100)
        print(
            f"{r['year']}  年初净值: {r['start_nav']:.4f}  "
            f"年末净值: {r['end_nav']:.4f}  年收益: {r['annual_return']:+.2f}%"
        )

    print("-" * 60)
    print(f"2019 年至今累计净值: {total_return:.4f}")
    print(f"2019 年至今总收益率: {(total_return - 1) * 100:.2f}%")


if __name__ == "__main__":
    main()
