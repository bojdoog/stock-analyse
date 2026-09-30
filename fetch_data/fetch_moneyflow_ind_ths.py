#!/usr/bin/env python3
"""
拉取同花顺行业资金流向数据 (THS)
接口：moneyflow_ind_ths - 需要 6000 积分
保存到 ../public/data/moneyflow_ind_ths/{date}.csv

用法：
  python fetch_data/fetch_moneyflow_ind_ths.py
  python fetch_data/fetch_moneyflow_ind_ths.py --start 20230912 --end 20260731
  python fetch_data/fetch_moneyflow_ind_ths.py --date 20240927
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

try:
    from .storage_sqlite import save_dataframe, refresh_index, list_files, initialize, read_frame, has_file
except ImportError:
    from storage_sqlite import save_dataframe, refresh_index, list_files, initialize, read_frame, has_file
from typing import Optional

from etf_catalog import sector_mapping

import pandas as pd
import tushare as ts
from tqdm import tqdm

# --------------------------- 全局日志配置 --------------------------- #
LOG_FILE = Path(__file__).resolve().parent / "fetch_moneyflow_ind_ths.log"
logger = logging.getLogger("fetch_moneyflow_ind_ths")
logger.setLevel(logging.INFO)

# 文件日志 - 记录所有信息
file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s"))

# 控制台日志 - 只显示警告和错误
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter("%(message)s"))

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# --------------------------- 同花顺行业板块到 ETF 映射 --------------------------- #
# 同花顺行业板块名称 -> ETF代码/名称映射
# 基于东方财富行业映射，补充同花顺特有的行业名称

pro: Optional[ts.pro_api] = None


def set_api(session) -> None:
    """由外部注入已创建好的 ts.pro_api() 会话"""
    global pro
    pro = session


def fetch_moneyflow_ind_ths(start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取同花顺行业资金流向（批量查询）
    接口：moneyflow_ind_ths
    积分要求：6000
    单次最大可调取5000条数据（每天约90个行业，一周约5天=450条，安全）
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            df = pro.moneyflow_ind_ths(
                start_date=start_date,
                end_date=end_date,
            )
            break  # 成功则跳出重试循环
        except Exception as e:
            error_msg = str(e)
            if '频率超限' in error_msg or '访问频繁' in error_msg:
                if attempt < max_retries - 1:
                    wait_time = 15  # 频率超限等待15秒
                    logger.warning(f"频率超限，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
            logger.error(f"获取 {start_date}~{end_date} 行业资金流向失败: {e}")
            raise

    if df is None or df.empty:
        logger.debug(f"{start_date}~{end_date} 无数据")
        return pd.DataFrame()

    # 数据清洗
    df = df.rename(columns={
        "trade_date": "date",
        "industry": "industry_name",
        "net_amount": "net_inflow",  # 净额（亿元）
    })

    # 添加 ETF 映射
    INDUSTRY_TO_ETF = sector_mapping("ind_ths")
    df["etf_code"] = df["industry_name"].map(
        lambda x: INDUSTRY_TO_ETF.get(x, {}).get("code", "")
    )
    df["etf_name"] = df["industry_name"].map(
        lambda x: INDUSTRY_TO_ETF.get(x, {}).get("name", "")
    )

    # 过滤出有 ETF 映射的行业
    df = df[df["etf_code"] != ""].copy()

    # 按日期和净流入排序
    df = df.sort_values(["date", "net_inflow"], ascending=[True, False]).reset_index(drop=True)

    return df


def save_moneyflow_by_date(df: pd.DataFrame, out_dir: Path) -> None:
    """按日期保存资金流向数据"""
    if df.empty:
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    # 按日期分组保存
    for date, group in df.groupby("date"):
        csv_path = out_dir / f"{date}.csv"
        save_dataframe(group, csv_path, category='moneyflow_ind_ths')
        logger.debug(f"已保存 {date} 行业资金流向数据: {len(group)} 个行业")


def get_week_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """获取按周划分的时间段列表，避免单次数据量超过5000条限制"""
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")

    ranges = []
    current = start

    while current <= end:
        # 每7天一个区间
        week_end = current + dt.timedelta(days=6)
        if week_end > end:
            week_end = end

        ranges.append((current.strftime("%Y%m%d"), week_end.strftime("%Y%m%d")))
        current = week_end + dt.timedelta(days=1)

    return ranges


def get_all_dates_between(start_date: str, end_date: str) -> list[str]:
    """获取两个日期之间的所有日期列表（包含起始和结束）"""
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y%m%d"))
        current += dt.timedelta(days=1)
    return dates


def check_missing_dates(out_dir: Path, start_date: str, end_date: str) -> list[str]:
    """检查指定范围内缺失的日期"""
    all_dates = get_all_dates_between(start_date, end_date)
    initialize()
    available = set(list_files('moneyflow_ind_ths'))
    missing = []
    for date_str in all_dates:
        csv_path = out_dir / f"{date_str}.csv"
        if csv_path.name not in available:
            missing.append(date_str)
    return missing


def update_index_json(out_dir: Path) -> None:
    """重建 index.json，供前端按文件列表加载"""
    initialize()
    files = refresh_index(out_dir, category='moneyflow_ind_ths')
    logger.info(f'Database file index updated: {len(files)} files')


def main():
    initialize()
    parser = argparse.ArgumentParser(
        description="拉取同花顺行业资金流向数据 (需要 Tushare 6000 积分)"
    )
    parser.add_argument("--date", help="指定日期 YYYYMMDD")
    parser.add_argument("--start", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--out",
        default=Path(__file__).resolve().parents[1] / "data" / "moneyflow_ind_ths",
        help="输出目录",
    )
    parser.add_argument(
        "--check-missing",
        action="store_true",
        help="检查并补全缺失的日期",
    )
    args = parser.parse_args()

    # ---------- Tushare Token ---------- #
    os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    ts_token = "eb0e5fcfd014dfb595b4ca773f42d29570a3fb06edcca84fe19830db"
    if not ts_token:
        raise ValueError("请先设置环境变量 TUSHARE_TOKEN")
    ts.set_token(ts_token)
    global pro
    pro = ts.pro_api()

    out_dir = Path(args.out)

    # ---------- 确定日期范围 ---------- #
    if args.date:
        start_date = args.date
        end_date = args.date
    elif args.start and args.end:
        start_date = args.start
        end_date = args.end
    else:
        # 默认拉取最近一个月
        today = dt.date.today()
        month_ago = today - dt.timedelta(days=30)
        start_date = month_ago.strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")

    # ---------- 检查并补全缺失的日期 ---------- #
    if args.check_missing:
        print(f"检查缺失的日期 ({start_date} ~ {end_date})...")
        missing = check_missing_dates(out_dir, start_date, end_date)
        if not missing:
            print("没有缺失的日期！")
            return

        print(f"发现 {len(missing)} 个缺失日期，开始补全...")
        missing_set = set(missing)
        week_ranges = get_week_ranges(start_date, end_date)
        total_fixed = 0

        for week_start, week_end in tqdm(week_ranges, desc="补全进度", unit="周"):
            week_dates = get_all_dates_between(week_start, week_end)
            if not any(d in missing_set for d in week_dates):
                continue
            try:
                df = fetch_moneyflow_ind_ths(week_start, week_end)
                if not df.empty:
                    save_moneyflow_by_date(df, out_dir)
                    total_fixed += len(df.groupby('date'))
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"{week_start}~{week_end} 补全失败: {e}")

        print(f"\n补全完成！成功补全 {total_fixed} 天")
        update_index_json(out_dir)
        return

    # ---------- 拉取数据（按周分批） ---------- #
    week_ranges = get_week_ranges(start_date, end_date)
    print(f"准备拉取数据 ({start_date} ~ {end_date})，共 {len(week_ranges)} 周")

    total_days = 0
    failed_ranges = []
    for start, end in tqdm(week_ranges, desc="拉取进度", unit="周"):
        try:
            df = fetch_moneyflow_ind_ths(start, end)
            if not df.empty:
                save_moneyflow_by_date(df, out_dir)
                total_days += len(df.groupby('date'))
            time.sleep(0.3)  # 短暂间隔避免频率限制
        except Exception as e:
            logger.error(f"{start}~{end} 拉取失败: {e}")
            failed_ranges.append((start, end))

    # 重试失败的区间
    if failed_ranges:
        print(f"\n重试 {len(failed_ranges)} 个失败的区间...")
        for start, end in failed_ranges:
            try:
                df = fetch_moneyflow_ind_ths(start, end)
                if not df.empty:
                    save_moneyflow_by_date(df, out_dir)
                    total_days += len(df.groupby('date'))
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"重试 {start}~{end} 失败: {e}")

    print(f"\n完成！共保存 {total_days} 天的数据")
    update_index_json(out_dir)


if __name__ == "__main__":
    main()