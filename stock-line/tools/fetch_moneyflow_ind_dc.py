#!/usr/bin/env python3
"""
拉取东方财富板块资金流向数据 (DC)
接口：moneyflow_ind_dc - 需要 6000 积分
保存到 ../public/data/moneyflow_ind_dc/{date}.csv

用法：
  python tools/fetch_moneyflow_ind_dc.py
  python tools/fetch_moneyflow_ind_dc.py --start 20230912 --end 20260731
  python tools/fetch_moneyflow_ind_dc.py --date 20240927
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import tushare as ts
from tqdm import tqdm

# --------------------------- 全局日志配置 --------------------------- #
LOG_FILE = Path(__file__).resolve().parent / "fetch_moneyflow_ind_dc.log"
logger = logging.getLogger("fetch_moneyflow_ind_dc")
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

# --------------------------- 板块到 ETF 映射 --------------------------- #
# 东方财富板块名称 -> ETF代码/名称映射
INDUSTRY_TO_ETF = {
    "互联网服务": {"code": "515230", "name": "软件ETF"},
    "软件开发": {"code": "515230", "name": "软件ETF"},
    "证券": {"code": "512880", "name": "证券ETF"},
    "酿酒行业": {"code": "512690", "name": "白酒ETF"},
    "电池": {"code": "516160", "name": "新能源ETF"},
    "半导体": {"code": "512480", "name": "半导体ETF"},
    "银行": {"code": "512800", "name": "银行ETF"},
    "光伏设备": {"code": "516290", "name": "光伏ETF"},
    "通信设备": {"code": "515880", "name": "通信ETF"},
    "医药商业": {"code": "159929", "name": "医药ETF"},
    "医疗器械": {"code": "159929", "name": "医药ETF"},
    "化学制药": {"code": "159929", "name": "医药ETF"},
    "中药": {"code": "159929", "name": "医药ETF"},
    "医疗服务": {"code": "510660", "name": "创新药ETF"},
    "生物制品": {"code": "510660", "name": "创新药ETF"},
    "游戏": {"code": "159869", "name": "游戏ETF"},
    "文化传媒": {"code": "512980", "name": "传媒ETF"},
    "航天航空": {"code": "512660", "name": "军工ETF"},
    "船舶制造": {"code": "512660", "name": "军工ETF"},
    "风电设备": {"code": "516160", "name": "新能源ETF"},
    "电网设备": {"code": "561380", "name": "电网设备ETF"},
    "汽车整车": {"code": "515030", "name": "新能源车ETF"},
    "汽车零部件": {"code": "515030", "name": "新能源车ETF"},
    "能源金属": {"code": "512400", "name": "有色ETF"},
    "小金属": {"code": "512400", "name": "有色ETF"},
    "贵金属": {"code": "512400", "name": "有色ETF"},
    "有色金属": {"code": "512400", "name": "有色ETF"},
    "煤炭行业": {"code": "515220", "name": "煤炭ETF"},
    "石油行业": {"code": "510300", "name": "沪深300ETF"},
    "电力行业": {"code": "561380", "name": "电网设备ETF"},
    "公用事业": {"code": "561380", "name": "电网设备ETF"},
    "燃气": {"code": "561380", "name": "电网设备ETF"},
    "水泥建材": {"code": "510300", "name": "沪深300ETF"},
    "房地产": {"code": "510300", "name": "沪深300ETF"},
    "工程建设": {"code": "510300", "name": "沪深300ETF"},
    "装修装饰": {"code": "510300", "name": "沪深300ETF"},
    "家电行业": {"code": "510150", "name": "消费ETF"},
    "旅游酒店": {"code": "510150", "name": "消费ETF"},
    "食品饮料": {"code": "510150", "name": "消费ETF"},
    "商业百货": {"code": "510150", "name": "消费ETF"},
    "农牧饲渔": {"code": "510150", "name": "消费ETF"},
    "猪肉概念": {"code": "510150", "name": "消费ETF"},
    "鸡肉概念": {"code": "510150", "name": "消费ETF"},
    "机器人": {"code": "562500", "name": "机器人ETF"},
    "人工智能": {"code": "159381", "name": "创业板人工智能ETF"},
    "算力概念": {"code": "515230", "name": "软件ETF"},
    "数据要素": {"code": "515230", "name": "软件ETF"},
    "云计算": {"code": "515230", "name": "软件ETF"},
    "区块链": {"code": "515230", "name": "软件ETF"},
    "数字货币": {"code": "515230", "name": "软件ETF"},
    "网络安全": {"code": "515230", "name": "软件ETF"},
    "物联网": {"code": "515880", "name": "通信ETF"},
    "5G概念": {"code": "515880", "name": "通信ETF"},
    "光通信模块": {"code": "515880", "name": "通信ETF"},
    "CPO概念": {"code": "515880", "name": "通信ETF"},
    "ChatGPT概念": {"code": "159381", "name": "创业板人工智能ETF"},
    "AIGC概念": {"code": "159381", "name": "创业板人工智能ETF"},
    "元宇宙概念": {"code": "159869", "name": "游戏ETF"},
    "虚拟现实": {"code": "159869", "name": "游戏ETF"},
    "增强现实": {"code": "159869", "name": "游戏ETF"},
    "半导体概念": {"code": "512480", "name": "半导体ETF"},
    "芯片概念": {"code": "512480", "name": "半导体ETF"},
    "汽车芯片": {"code": "512480", "name": "半导体ETF"},
    "存储芯片": {"code": "512480", "name": "半导体ETF"},
    "国产芯片": {"code": "512480", "name": "半导体ETF"},
    "EDA概念": {"code": "588710", "name": "科创半导体设备ETF"},
    "光刻机": {"code": "588710", "name": "科创半导体设备ETF"},
    "中芯概念": {"code": "588710", "name": "科创半导体设备ETF"},
    "固态电池": {"code": "516160", "name": "新能源ETF"},
    "钠离子电池": {"code": "516160", "name": "新能源ETF"},
    "锂电池": {"code": "516160", "name": "新能源ETF"},
    "储能": {"code": "516160", "name": "新能源ETF"},
    "氢能源": {"code": "516160", "name": "新能源ETF"},
    "充电桩": {"code": "516160", "name": "新能源ETF"},
    "特高压": {"code": "561380", "name": "电网设备ETF"},
    "智能电网": {"code": "561380", "name": "电网设备ETF"},
    "虚拟电厂": {"code": "561380", "name": "电网设备ETF"},
    "核能核电": {"code": "561380", "name": "电网设备ETF"},
    "超导概念": {"code": "561380", "name": "电网设备ETF"},
    "新能源车": {"code": "515030", "name": "新能源车ETF"},
    "无人驾驶": {"code": "515030", "name": "新能源车ETF"},
    "特斯拉": {"code": "515030", "name": "新能源车ETF"},
    "比亚迪概念": {"code": "515030", "name": "新能源车ETF"},
    "北斗导航": {"code": "159206", "name": "卫星ETF"},
    "航天概念": {"code": "159206", "name": "卫星ETF"},
    "大飞机": {"code": "512660", "name": "军工ETF"},
    "军民融合": {"code": "512660", "name": "军工ETF"},
    "航母概念": {"code": "512660", "name": "军工ETF"},
    "国产航母": {"code": "512660", "name": "军工ETF"},
    "军工": {"code": "512660", "name": "军工ETF"},
    "无人机": {"code": "512660", "name": "军工ETF"},
    "人形机器人": {"code": "562500", "name": "机器人ETF"},
    "工业母机": {"code": "159638", "name": "高端装备ETF"},
    "高端装备": {"code": "159638", "name": "高端装备ETF"},
    "海工装备": {"code": "159638", "name": "高端装备ETF"},
    "海洋经济": {"code": "159638", "name": "高端装备ETF"},
}

pro: Optional[ts.pro_api] = None


def set_api(session) -> None:
    """由外部注入已创建好的 ts.pro_api() 会话"""
    global pro
    pro = session


def fetch_moneyflow_ind_dc(start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取东方财富板块资金流向（批量查询）
    接口：moneyflow_ind_dc
    积分要求：6000
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 使用 start_date 和 end_date 批量查询
            df = pro.moneyflow_ind_dc(
                start_date=start_date,
                end_date=end_date,
                content_type='行业',  # 只查行业板块
                fields='trade_date,name,pct_change,close,net_amount,net_amount_rate,buy_elg_amount,buy_lg_amount,rank'
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
            logger.error(f"获取 {start_date}~{end_date} 板块资金流向失败: {e}")
            raise

    if df is None or df.empty:
        logger.debug(f"{start_date}~{end_date} 无数据")
        return pd.DataFrame()

    # 数据清洗
    df = df.rename(columns={
        "trade_date": "date",
        "name": "industry_name",
        "net_amount": "net_inflow",  # 主力净流入（元）
        "buy_elg_amount": "super_large_inflow",  # 超大单净流入
        "buy_lg_amount": "large_inflow",  # 大单净流入
    })

    # 转换为亿元
    df["net_inflow"] = df["net_inflow"] / 1e8
    df["super_large_inflow"] = df["super_large_inflow"] / 1e8
    df["large_inflow"] = df["large_inflow"] / 1e8

    # 添加 ETF 映射
    df["etf_code"] = df["industry_name"].map(
        lambda x: INDUSTRY_TO_ETF.get(x, {}).get("code", "")
    )
    df["etf_name"] = df["industry_name"].map(
        lambda x: INDUSTRY_TO_ETF.get(x, {}).get("name", "")
    )

    # 过滤出有 ETF 映射的板块
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
        group.to_csv(csv_path, index=False)
        logger.debug(f"已保存 {date} 资金流向数据: {len(group)} 个板块")


def get_month_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """获取按月划分的时间段列表，用于批量查询"""
    start = dt.datetime.strptime(start_date, "%Y%m%d")
    end = dt.datetime.strptime(end_date, "%Y%m%d")

    ranges = []
    current = start

    while current <= end:
        # 当月最后一天
        if current.month == 12:
            month_end = current.replace(year=current.year + 1, month=1, day=1) - dt.timedelta(days=1)
        else:
            month_end = current.replace(month=current.month + 1, day=1) - dt.timedelta(days=1)

        if month_end > end:
            month_end = end

        ranges.append((current.strftime("%Y%m%d"), month_end.strftime("%Y%m%d")))

    return ranges


def get_week_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """获取按周划分的时间段列表，避免单月数据量过大导致API截断"""
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
    missing = []
    for date_str in all_dates:
        csv_path = out_dir / f"{date_str}.csv"
        if not csv_path.exists():
            missing.append(date_str)
    return missing


def update_index_json(out_dir: Path) -> None:
    """重建 index.json，供前端按文件列表加载"""
    files = sorted(p.name for p in out_dir.glob("*.csv"))
    index_path = out_dir / "index.json"
    index_path.write_text(
        json.dumps(files, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"已更新 {index_path}（{len(files)} 个文件）")


def main():
    parser = argparse.ArgumentParser(
        description="拉取东方财富板块资金流向数据 (需要 Tushare 6000 积分)"
    )
    parser.add_argument("--date", help="指定日期 YYYYMMDD")
    parser.add_argument("--start", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--out",
        default=Path(__file__).resolve().parent.parent / "public" / "data" / "moneyflow_ind_dc",
        help="输出目录",
    )
    parser.add_argument(
        "--check-missing",
        action="store_true",
        help="检查并补全缺失的日期",
    )
    args = parser.parse_args()

    # ---------- Tushare Token ---------- #
    import os

    os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    ts_token = "eb0e5fcfd014dfb595b4ca773f42d29570a3fb06edcca84fe19830db"
    if not ts_token:
        raise ValueError("请先设置环境变量 TUSHARE_TOKEN")
    ts.set_token(ts_token)
    global pro
    pro = ts.pro_api()

    out_dir = Path(args.out)

    # ---------- 检查并补全缺失的日期 ---------- #
    if args.check_missing and args.start and args.end:
        print(f"检查缺失的日期 ({args.start} ~ {args.end})...")

        # 按月检查，批量补全（避免逐日查询触发频率限制）
        month_ranges = get_month_ranges(args.start, args.end)
        total_fixed = 0
        total_missing = 0

        for month_start, month_end in tqdm(month_ranges, desc="检查各月", unit="月"):
            # 获取该月所有交易日
            month_dates = []
            curr = dt.datetime.strptime(month_start, "%Y%m%d")
            end = dt.datetime.strptime(month_end, "%Y%m%d")
            while curr <= end:
                month_dates.append(curr.strftime("%Y%m%d"))
                curr += dt.timedelta(days=1)

            # 检查该月缺失的日期
            missing_in_month = [d for d in month_dates if not (out_dir / f"{d}.csv").exists()]

            if missing_in_month:
                total_missing += len(missing_in_month)
                # 批量拉取整月数据
                try:
                    df = fetch_moneyflow_ind_dc(month_start, month_end)
                    if not df.empty:
                        save_moneyflow_by_date(df, out_dir)
                        fixed = len(df.groupby('date'))
                        total_fixed += fixed
                        logger.info(f"{month_start[:6]} 补全 {fixed} 天")
                    time.sleep(2)  # 月与月之间间隔2秒
                except Exception as e:
                    logger.error(f"{month_start}~{month_end} 补全失败: {e}")

        print(f"\n补全完成！发现缺失: {total_missing} 天, 成功补全: {total_fixed} 天")
        update_index_json(out_dir)
        return

    # ---------- 确定日期范围 ---------- #
    if args.date:
        dates = [args.date]
        start_val = args.date
        end_val = args.date
    elif args.start and args.end:
        # 生成所有日期列表，一次性逐日拉取
        dates = get_all_dates_between(args.start, args.end)
        start_val = args.start
        end_val = args.end
    else:
        # 默认拉取最近一个月
        today = dt.date.today()
        month_ago = today - dt.timedelta(days=30)
        start_val = month_ago.strftime("%Y%m%d")
        end_val = today.strftime("%Y%m%d")
        dates = get_all_dates_between(start_val, end_val)

    # 按周分批拉取，避免单月数据量过大导致API截断
    week_ranges = get_week_ranges(start_val, end_val)
    print(f"准备拉取数据 ({start_val} ~ {end_val})，共 {len(week_ranges)} 周")

    total_days = 0
    failed_ranges = []
    for start, end in tqdm(week_ranges, desc="拉取进度", unit="周"):
        try:
            df = fetch_moneyflow_ind_dc(start, end)
            if not df.empty:
                save_moneyflow_by_date(df, out_dir)
                total_days += len(df.groupby('date'))
            time.sleep(0.3)  # 短暂间隔避免频率限制
        except Exception as e:
            logger.error(f"{start}~{end} 拉取失败: {e}")
            failed_ranges.append((start, end))

    # 重试失败的区间（逐日）
    if failed_ranges:
        print(f"\n重试 {len(failed_ranges)} 个失败的区间...")
        for start, end in failed_ranges:
            try:
                df = fetch_moneyflow_ind_dc(start, end)
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
