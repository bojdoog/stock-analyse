#!/usr/bin/env python3
"""
拉取同花顺概念板块资金流向数据 (THS)
接口：moneyflow_cnt_ths - 需要 6000 积分
保存到 ../public/data/moneyflow_cnt_ths/{date}.csv

用法：
  python tools/fetch_moneyflow_cnt_ths.py
  python tools/fetch_moneyflow_cnt_ths.py --start 20230912 --end 20260731
  python tools/fetch_moneyflow_cnt_ths.py --date 20250320
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
from typing import Optional

import pandas as pd
import tushare as ts
from tqdm import tqdm

# --------------------------- 全局日志配置 --------------------------- #
LOG_FILE = Path(__file__).resolve().parent / "fetch_moneyflow_cnt_ths.log"
logger = logging.getLogger("fetch_moneyflow_cnt_ths")
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

# --------------------------- 概念板块到 ETF 映射 --------------------------- #
# 同花顺概念板块名称 -> ETF代码/名称映射
# 用于将概念资金流向映射到可交易的 ETF
CONCEPT_TO_ETF = {
    # 半导体/芯片
    "半导体": {"code": "512480", "name": "半导体ETF"},
    "芯片": {"code": "512480", "name": "半导体ETF"},
    "集成电路": {"code": "512480", "name": "半导体ETF"},
    "第三代半导体": {"code": "512480", "name": "半导体ETF"},
    "汽车芯片": {"code": "512480", "name": "半导体ETF"},
    "存储芯片": {"code": "512480", "name": "半导体ETF"},
    "国产芯片": {"code": "512480", "name": "半导体ETF"},
    "Chiplet概念": {"code": "512480", "name": "半导体ETF"},
    "封测概念": {"code": "512480", "name": "半导体ETF"},
    "HBM概念": {"code": "512480", "name": "半导体ETF"},
    "半导体概念": {"code": "512480", "name": "半导体ETF"},
    "光刻机": {"code": "588710", "name": "科创半导体设备ETF"},
    "光刻胶": {"code": "588710", "name": "科创半导体设备ETF"},
    "EDA概念": {"code": "588710", "name": "科创半导体设备ETF"},
    "中芯概念": {"code": "588710", "name": "科创半导体设备ETF"},
    "设备更新": {"code": "588710", "name": "科创半导体设备ETF"},
    # 软件/IT
    "软件开发": {"code": "515230", "name": "软件ETF"},
    "信创": {"code": "515230", "name": "软件ETF"},
    "数据要素": {"code": "515230", "name": "软件ETF"},
    "云计算": {"code": "515230", "name": "软件ETF"},
    "大数据": {"code": "515230", "name": "软件ETF"},
    "网络安全": {"code": "515230", "name": "软件ETF"},
    "数字货币": {"code": "515230", "name": "软件ETF"},
    "区块链": {"code": "515230", "name": "软件ETF"},
    "国产软件": {"code": "515230", "name": "软件ETF"},
    "互联网服务": {"code": "515230", "name": "软件ETF"},
    "算力租赁": {"code": "515230", "name": "软件ETF"},
    "智慧政务": {"code": "515230", "name": "软件ETF"},
    "华为昇腾": {"code": "515230", "name": "软件ETF"},
    "华为欧拉": {"code": "515230", "name": "软件ETF"},
    "华为鲲鹏": {"code": "515230", "name": "软件ETF"},
    "华为概念": {"code": "515230", "name": "软件ETF"},
    "鸿蒙概念": {"code": "515230", "name": "软件ETF"},
    "操作系统": {"code": "515230", "name": "软件ETF"},
    "东数西算": {"code": "515230", "name": "软件ETF"},
    "液冷服务器": {"code": "515230", "name": "软件ETF"},
    # 通信/算力
    "5G": {"code": "515880", "name": "通信ETF"},
    "5G概念": {"code": "515880", "name": "通信ETF"},
    "光通信": {"code": "515880", "name": "通信ETF"},
    "CPO概念": {"code": "515880", "name": "通信ETF"},
    "算力概念": {"code": "515880", "name": "通信ETF"},
    "6G概念": {"code": "515880", "name": "通信ETF"},
    "通信设备": {"code": "515880", "name": "通信ETF"},
    "卫星导航": {"code": "515880", "name": "通信ETF"},
    "北斗导航": {"code": "159206", "name": "卫星ETF"},
    "商业航天": {"code": "159206", "name": "卫星ETF"},
    "航天概念": {"code": "159206", "name": "卫星ETF"},
    "卫星互联网": {"code": "159206", "name": "卫星ETF"},
    # 游戏/传媒/元宇宙
    "网络游戏": {"code": "159869", "name": "游戏ETF"},
    "手游": {"code": "159869", "name": "游戏ETF"},
    "云游戏": {"code": "159869", "name": "游戏ETF"},
    "元宇宙": {"code": "159869", "name": "游戏ETF"},
    "虚拟现实": {"code": "159869", "name": "游戏ETF"},
    "增强现实": {"code": "159869", "name": "游戏ETF"},
    "短剧互动游戏": {"code": "159869", "name": "游戏ETF"},
    "文化传媒": {"code": "512980", "name": "传媒ETF"},
    "传媒": {"code": "512980", "name": "传媒ETF"},
    "影视院线": {"code": "512980", "name": "传媒ETF"},
    "动漫游戏": {"code": "159869", "name": "游戏ETF"},
    # AI/机器人
    "人工智能": {"code": "159381", "name": "创业板人工智能ETF"},
    "AIGC概念": {"code": "159381", "name": "创业板人工智能ETF"},
    "ChatGPT概念": {"code": "159381", "name": "创业板人工智能ETF"},
    "大模型": {"code": "159381", "name": "创业板人工智能ETF"},
    "人形机器人": {"code": "562500", "name": "机器人ETF"},
    "机器人概念": {"code": "562500", "name": "机器人ETF"},
    "减速器": {"code": "562500", "name": "机器人ETF"},
    "工业母机": {"code": "159638", "name": "高端装备ETF"},
    "高端装备": {"code": "159638", "name": "高端装备ETF"},
    "海工装备": {"code": "159638", "name": "高端装备ETF"},
    "海洋经济": {"code": "159638", "name": "高端装备ETF"},
    "智能制造": {"code": "159638", "name": "高端装备ETF"},
    # 新能源/锂电/储能
    "锂电池": {"code": "516160", "name": "新能源ETF"},
    "钠离子电池": {"code": "516160", "name": "新能源ETF"},
    "固态电池": {"code": "516160", "name": "新能源ETF"},
    "储能": {"code": "516160", "name": "新能源ETF"},
    "氢能源": {"code": "516160", "name": "新能源ETF"},
    "燃料电池": {"code": "516160", "name": "新能源ETF"},
    "充电桩": {"code": "516160", "name": "新能源ETF"},
    "风电": {"code": "516160", "name": "新能源ETF"},
    "风电设备": {"code": "516160", "name": "新能源ETF"},
    "光伏": {"code": "516290", "name": "光伏ETF"},
    "光伏设备": {"code": "516290", "name": "光伏ETF"},
    "光伏概念": {"code": "516290", "name": "光伏ETF"},
    "TOPCon电池": {"code": "516290", "name": "光伏ETF"},
    "钙钛矿电池": {"code": "516290", "name": "光伏ETF"},
    "HJT电池": {"code": "516290", "name": "光伏ETF"},
    "特高压": {"code": "561380", "name": "电网设备ETF"},
    "智能电网": {"code": "561380", "name": "电网设备ETF"},
    "虚拟电厂": {"code": "561380", "name": "电网设备ETF"},
    "核能核电": {"code": "561380", "name": "电网设备ETF"},
    "超导概念": {"code": "561380", "name": "电网设备ETF"},
    "电网设备": {"code": "561380", "name": "电网设备ETF"},
    "电力物联网": {"code": "561380", "name": "电网设备ETF"},
    "碳中和": {"code": "516160", "name": "新能源ETF"},
    # 新能源车/汽车
    "新能源车": {"code": "515030", "name": "新能源车ETF"},
    "新能源汽车": {"code": "515030", "name": "新能源车ETF"},
    "特斯拉": {"code": "515030", "name": "新能源车ETF"},
    "比亚迪概念": {"code": "515030", "name": "新能源车ETF"},
    "无人驾驶": {"code": "515030", "name": "新能源车ETF"},
    "一体化压铸": {"code": "515030", "name": "新能源车ETF"},
    "汽车整车": {"code": "515030", "name": "新能源车ETF"},
    "汽车零部件": {"code": "515030", "name": "新能源车ETF"},
    "智能汽车": {"code": "515030", "name": "新能源车ETF"},
    "低空经济": {"code": "515030", "name": "新能源车ETF"},
    "飞行汽车": {"code": "515030", "name": "新能源车ETF"},
    "汽车热管理": {"code": "515030", "name": "新能源车ETF"},
    # 军工
    "军工": {"code": "512660", "name": "军工ETF"},
    "国防军工": {"code": "512660", "name": "军工ETF"},
    "大飞机": {"code": "512660", "name": "军工ETF"},
    "无人机": {"code": "512660", "name": "军工ETF"},
    "军民融合": {"code": "512660", "name": "军工ETF"},
    "航母概念": {"code": "512660", "name": "军工ETF"},
    "军工信息化": {"code": "512660", "name": "军工ETF"},
    "军工电子": {"code": "512660", "name": "军工ETF"},
    "航空发动机": {"code": "512660", "name": "军工ETF"},
    # 有色/资源
    "黄金概念": {"code": "512400", "name": "有色ETF"},
    "贵金属": {"code": "512400", "name": "有色ETF"},
    "稀土永磁": {"code": "512400", "name": "有色ETF"},
    "小金属": {"code": "512400", "name": "有色ETF"},
    "有色金属": {"code": "512400", "name": "有色ETF"},
    "锂矿": {"code": "512400", "name": "有色ETF"},
    "钴": {"code": "512400", "name": "有色ETF"},
    "镍": {"code": "512400", "name": "有色ETF"},
    "能源金属": {"code": "512400", "name": "有色ETF"},
    "固态电池概念": {"code": "512400", "name": "有色ETF"},
    "稀缺资源": {"code": "512400", "name": "有色ETF"},
    # 煤炭/能源
    "煤炭概念": {"code": "515220", "name": "煤炭ETF"},
    "煤炭": {"code": "515220", "name": "煤炭ETF"},
    "煤化工": {"code": "515220", "name": "煤炭ETF"},
    "焦炭": {"code": "515220", "name": "煤炭ETF"},
    # 医药
    "创新药": {"code": "510660", "name": "创新药ETF"},
    "医药": {"code": "159929", "name": "医药ETF"},
    "医药商业": {"code": "159929", "name": "医药ETF"},
    "化学制药": {"code": "159929", "name": "医药ETF"},
    "医疗器械": {"code": "159929", "name": "医药ETF"},
    "中药": {"code": "159929", "name": "医药ETF"},
    "医疗服务": {"code": "510660", "name": "创新药ETF"},
    "生物医药": {"code": "510660", "name": "创新药ETF"},
    "生物制品": {"code": "510660", "name": "创新药ETF"},
    "DRG/DIP": {"code": "159929", "name": "医药ETF"},
    "减肥药": {"code": "510660", "name": "创新药ETF"},
    "CRO概念": {"code": "510660", "name": "创新药ETF"},
    "仿制药": {"code": "159929", "name": "医药ETF"},
    # 证券/银行/金融
    "证券": {"code": "512880", "name": "证券ETF"},
    "券商概念": {"code": "512880", "name": "证券ETF"},
    "互联网金融": {"code": "512880", "name": "证券ETF"},
    "多元金融": {"code": "512880", "name": "证券ETF"},
    "银行": {"code": "512800", "name": "银行ETF"},
    "保险": {"code": "512800", "name": "银行ETF"},
    # 白酒/消费
    "白酒": {"code": "512690", "name": "白酒ETF"},
    "酿酒": {"code": "512690", "name": "白酒ETF"},
    "饮料制造": {"code": "512690", "name": "白酒ETF"},
    "啤酒概念": {"code": "512690", "name": "白酒ETF"},
    "食品": {"code": "510150", "name": "消费ETF"},
    "乳业": {"code": "510150", "name": "消费ETF"},
    "猪肉概念": {"code": "510150", "name": "消费ETF"},
    "鸡肉概念": {"code": "510150", "name": "消费ETF"},
    "预制菜": {"code": "510150", "name": "消费ETF"},
    "免税概念": {"code": "510150", "name": "消费ETF"},
    "旅游酒店": {"code": "510150", "name": "消费ETF"},
    "旅游概念": {"code": "510150", "name": "消费ETF"},
    "餐饮": {"code": "510150", "name": "消费ETF"},
    "农业": {"code": "510150", "name": "消费ETF"},
    "农牧饲渔": {"code": "510150", "name": "消费ETF"},
    "大消费": {"code": "510150", "name": "消费ETF"},
    "家电": {"code": "510150", "name": "消费ETF"},
    "零售": {"code": "510150", "name": "消费ETF"},
    "电商": {"code": "512980", "name": "传媒ETF"},
    "网红经济": {"code": "512980", "name": "传媒ETF"},
    # 房地产/基建（宽基兜底）
    "房地产": {"code": "510300", "name": "沪深300ETF"},
    "工程建设": {"code": "510300", "name": "沪深300ETF"},
    "水泥建材": {"code": "510300", "name": "沪深300ETF"},
    "建筑材料": {"code": "510300", "name": "沪深300ETF"},
    "基建": {"code": "510300", "name": "沪深300ETF"},
    "中字头": {"code": "510300", "name": "沪深300ETF"},
    "国企改革": {"code": "510300", "name": "沪深300ETF"},
    "石油行业": {"code": "510300", "name": "沪深300ETF"},
    "油气开采": {"code": "510300", "name": "沪深300ETF"},
    "化工": {"code": "510300", "name": "沪深300ETF"},
    "钢铁": {"code": "510300", "name": "沪深300ETF"},
    "航运概念": {"code": "510300", "name": "沪深300ETF"},
    "港口航运": {"code": "510300", "name": "沪深300ETF"},
    "物流": {"code": "510300", "name": "沪深300ETF"},
    "一带一路": {"code": "510300", "name": "沪深300ETF"},
    # 电力/公用
    "电力": {"code": "561380", "name": "电网设备ETF"},
    "公用事业": {"code": "561380", "name": "电网设备ETF"},
    "燃气": {"code": "561380", "name": "电网设备ETF"},
    "水务": {"code": "561380", "name": "电网设备ETF"},
    "绿色电力": {"code": "516160", "name": "新能源ETF"},
}

pro: Optional[ts.pro_api] = None


def set_api(session) -> None:
    """由外部注入已创建好的 ts.pro_api() 会话"""
    global pro
    pro = session


def fetch_moneyflow_cnt_ths(start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取同花顺概念板块资金流向（批量查询）
    接口：moneyflow_cnt_ths
    积分要求：6000
    单次最大可调取5000条数据（每天约390+概念，一周约5天=2000条以内，安全）
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            df = pro.moneyflow_cnt_ths(
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
            logger.error(f"获取 {start_date}~{end_date} 概念资金流向失败: {e}")
            raise

    if df is None or df.empty:
        logger.debug(f"{start_date}~{end_date} 无数据")
        return pd.DataFrame()

    # 数据清洗
    df = df.rename(columns={
        "trade_date": "date",
        "name": "industry_name",
        "pct_change": "pct_change",
        "net_amount": "net_inflow",  # 净额（亿元）
    })

    # 添加 ETF 映射
    df["etf_code"] = df["industry_name"].map(
        lambda x: CONCEPT_TO_ETF.get(x, {}).get("code", "")
    )
    df["etf_name"] = df["industry_name"].map(
        lambda x: CONCEPT_TO_ETF.get(x, {}).get("name", "")
    )

    # 过滤出有 ETF 映射的概念
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
        logger.debug(f"已保存 {date} 概念资金流向数据: {len(group)} 个概念")


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
        description="拉取同花顺概念板块资金流向数据 (需要 Tushare 6000 积分)"
    )
    parser.add_argument("--date", help="指定日期 YYYYMMDD")
    parser.add_argument("--start", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--out",
        default=Path(__file__).resolve().parent.parent / "public" / "data" / "moneyflow_cnt_ths",
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
        # 按周拉取缺失日期所在区间
        missing_set = set(missing)
        week_ranges = get_week_ranges(start_date, end_date)
        total_fixed = 0

        for week_start, week_end in tqdm(week_ranges, desc="补全进度", unit="周"):
            week_dates = get_all_dates_between(week_start, week_end)
            if not any(d in missing_set for d in week_dates):
                continue
            try:
                df = fetch_moneyflow_cnt_ths(week_start, week_end)
                if not df.empty:
                    # 只保存缺失的日期
                    existing = set((out_dir / f"{d}.csv").exists() for d in week_dates)
                    _ = existing
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
            df = fetch_moneyflow_cnt_ths(start, end)
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
                df = fetch_moneyflow_cnt_ths(start, end)
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
