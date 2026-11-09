#!/usr/bin/env python3
"""
从数据库（stock_daily_basic）读取股票池并用 Tushare 抓取日线K线（固定 qfq，全量覆盖）
- 保存到 ../public/data/stock/{code}.csv

用法：
  python fetch_data/fetch_kline.py
  python fetch_data/fetch_kline.py --start 20250101 --end today
  python fetch_data/fetch_kline.py --workers 8
"""
from __future__ import annotations

import argparse
import builtins
import datetime as dt
import logging
import random
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from .storage_sqlite import save_dataframe, refresh_index, list_files, initialize, read_frame, has_file, save_csvs_batch
except ImportError:
    from storage_sqlite import save_dataframe, refresh_index, list_files, initialize, read_frame, has_file, save_csvs_batch

try:
    from .trading_date import default_end_date
except ImportError:
    from trading_date import default_end_date
from typing import List, Optional
import os

import pandas as pd
import tushare as ts
from tqdm import tqdm

warnings.filterwarnings("ignore")

# --------------------------- 全局日志配置 --------------------------- #
LOG_FILE = Path(__file__).resolve().parent / "fetch.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fetch_from_stocklist")

# --------------------------- 限流/封禁处理配置 --------------------------- #
COOLDOWN_SECS = 60  # Tushare 按分钟计额度，命中上限后统一等到额度恢复
BAN_PATTERNS = (
    "访问频繁", "请稍后", "超过频率", "频繁访问", "频率超限",
    "too many requests", "429",
    "forbidden", "403",
    "max retries exceeded"
)


def _looks_like_ip_ban(exc: Exception) -> bool:
    msg = (str(exc) or "").lower()
    return any(pat in msg for pat in BAN_PATTERNS)


class RateLimitError(RuntimeError):
    """表示命中限流/封禁，需要长时间冷却后重试。"""
    pass


_cooldown_lock = threading.Lock()
_cooldown_until = 0.0
_cooldown_reporting = False


def _cooldown_left() -> float:
    with _cooldown_lock:
        return max(0.0, _cooldown_until - time.monotonic())


def _wait_for_cooldown() -> None:
    """命中限流后所有线程一起等，避免每个线程各睡一遍。"""
    while True:
        left = _cooldown_left()
        if left <= 0:
            return
        time.sleep(min(1.0, left))


def _start_cooldown(seconds: int = COOLDOWN_SECS) -> None:
    """开启全局冷却；由首个命中的线程打印倒计时，供控制台显示限流进度条。"""
    global _cooldown_until, _cooldown_reporting
    wait_s = max(1, int(seconds * random.uniform(0.95, 1.05)))
    with _cooldown_lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + wait_s)
        if _cooldown_reporting:
            return
        _cooldown_reporting = True

    def report():
        global _cooldown_reporting
        while True:
            left = int(_cooldown_left())
            if left <= 0:
                break
            print(f"RATE_WAIT {left} {wait_s}", flush=True)
            time.sleep(1)
        print("RATE_WAIT 0 0", flush=True)
        with _cooldown_lock:
            _cooldown_reporting = False

    threading.Thread(target=report, daemon=True).start()


# tushare 的 pro_bar 内部会把限流信息用 print 输出、再抛一个无意义的 IOError('ERROR.')，
# 这里拦截 print：命中限流关键词时立刻开启全局冷却，让控制台显示「等待tushare额度恢复」。
_hit_local = threading.local()
_original_print = builtins.print


def _print_watch(*args, **kwargs):
    try:
        message = " ".join(str(arg) for arg in args).lower()
        if any(pattern in message for pattern in BAN_PATTERNS):
            _hit_local.rate_limited = True
            _start_cooldown()
    except Exception:  # noqa: BLE001
        pass
    return _original_print(*args, **kwargs)


builtins.print = _print_watch


# --------------------------- 历史K线（Tushare 日线，固定qfq） --------------------------- #
pro: Optional[ts.pro_api] = None  # 模块级会话


def set_api(session) -> None:
    """由外部(比如GUI)注入已创建好的 ts.pro_api() 会话"""
    global pro
    pro = session


def _to_ts_code(code: str) -> str:
    """把6位code映射到标准 ts_code 后缀。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"{code}.SH"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def _get_kline_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    ts_code = _to_ts_code(code)
    _wait_for_cooldown()
    _hit_local.rate_limited = False
    try:
        df = ts.pro_bar(
            ts_code=ts_code,
            adj="qfq",
            start_date=start,
            end_date=end,
            freq="D",
            api=pro
        )
    except Exception as e:
        if getattr(_hit_local, 'rate_limited', False) or _looks_like_ip_ban(e):
            _start_cooldown()
            raise RateLimitError(str(e)) from e
        raise

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"trade_date": "date", "vol": "volume"})[
        ["date", "open", "close", "high", "low", "volume", "amount"]
    ].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "close", "high", "low", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    if df["date"].isna().any():
        raise ValueError("存在缺失日期！")
    if (df["date"] > pd.Timestamp.today()).any():
        raise ValueError("数据包含未来日期，可能抓取错误！")
    return df


# --------------------------- 读取数据库股票池 & 过滤板块 ---------------------------

def _filter_by_boards(df: pd.DataFrame, exclude_boards: set[str]) -> pd.DataFrame:
    """
    exclude_boards 子集：{'gem','star','bj'}
    - gem  : 创业板 300/301（.SZ）
    - star : 科创板 688（.SH）
    - bj   : 北交所（.BJ 或 4/8 开头）
    """
    code = df["symbol"].astype(str)
    ts_code = df["ts_code"].astype(str).str.upper()
    mask = pd.Series(True, index=df.index)

    if "gem" in exclude_boards:
        mask &= ~code.str.startswith(("300", "301"))
    if "star" in exclude_boards:
        mask &= ~code.str.startswith(("688",))
    if "bj" in exclude_boards:
        mask &= ~(ts_code.str.endswith(".BJ") | code.str.startswith(("4", "8")))

    return df[mask].copy()


def load_codes_from_database(exclude_boards: set[str]) -> List[str]:
    """股票池取自数据库 stock_daily_basic（近 120 天出现过的个股），不再依赖本地 stocklist.csv。"""
    from market_store import connect
    from stock_basic_daily import pool
    with connect() as db:
        rows = pool(db)
    if not rows:
        return []
    symbols, ts_codes = [], []
    for row in rows:
        code = str(row["code"]).zfill(6)
        suffix = "SH" if code.startswith("6") else "SZ" if code[0] in "03" else "BJ"
        symbols.append(code)
        ts_codes.append(f"{code}.{suffix}")
    df = _filter_by_boards(pd.DataFrame({"symbol": symbols, "ts_code": ts_codes}), exclude_boards)
    codes = list(dict.fromkeys(df["symbol"].tolist()))
    logger.info("从数据库读取到 %d 只股票（排除板块：%s）",
                len(codes), ",".join(sorted(exclude_boards)) or "无")
    return codes


# --------------------------- 单只抓取（全量覆盖保存） --------------------------- #
def fetch_one(
    code: str,
    start: str,
    end: str,
    out_dir: Path,
    defer_db: bool = False,
):
    csv_path = out_dir / f"{code}.csv"

    failures = 0
    while failures < 9:
        try:
            new_df = _get_kline_tushare(code, start, end)
            if new_df.empty:
                logger.debug("%s 无数据，生成空表。", code)
                new_df = pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume", "amount"])
            new_df = validate(new_df)
            if defer_db:
                # 先落 CSV，全部下载结束后再统一入库，避免每只股票都建连接、重写历史。
                new_df.to_csv(csv_path, index=False)
            else:
                save_dataframe(new_df, csv_path, category='stock')  # 直接覆盖保存
            break
        except Exception as e:
            if isinstance(e, RateLimitError) or _looks_like_ip_ban(e):
                # 频率上限按分钟计，整批线程一起等额度恢复；限流不计入失败次数。
                if not isinstance(e, RateLimitError):
                    _start_cooldown()
                _wait_for_cooldown()
            else:
                failures += 1
                time.sleep(15 * failures)
    else:
        raise RuntimeError(f"{code} 九次抓取均失败")


# --------------------------- 主入口 --------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="从数据库 stock_daily_basic 读取股票池并用 Tushare 抓取日线K线（固定qfq，全量覆盖）"
    )
    default_start = '20240101'
    parser.add_argument("--start", default=default_start, help="起始日期 YYYYMMDD 或 'today'")
    parser.add_argument("--end", default="today", help="结束日期 YYYYMMDD 或 'today'（today=15点前取前一交易日，15点后取当天）")
    parser.add_argument(
        "--exclude-boards",
        nargs="*",
        default=["gem", "star", "bj"],
        help="排除板块，可多选：gem(创业板300/301) star(科创板688) bj(北交所.BJ/4/8)",
    )
    parser.add_argument(
        "--out",
        default=Path(__file__).resolve().parents[1] / "data" / "stock",
        help="输出目录",
    )
    parser.add_argument("--workers", type=int, default=6, help="并发线程数")
    parser.add_argument(
        "--defer-db",
        action="store_true",
        help="下载阶段只写 CSV，全部结束后批量入库（批量写库比逐只写快很多）",
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

    # ---------- 日期解析 ---------- #
    start = dt.date.today().strftime("%Y%m%d") if str(args.start).lower() == "today" else args.start
    end = default_end_date() if str(args.end).lower() == "today" else args.end

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 从数据库读取股票池 ---------- #
    exclude_boards = set(args.exclude_boards or [])
    codes = load_codes_from_database(exclude_boards)

    if not codes:
        logger.error("数据库中暂无股票池，请先运行 fetch_data/fetch_daily_basic.py 初始化。")
        sys.exit(1)

    logger.info(
        "开始抓取 %d 支股票 | 数据源:Tushare(日线,qfq) | 日期:%s → %s | 排除:%s",
        len(codes), start, end, ",".join(sorted(exclude_boards)) or "无",
    )

    # ---------- 多线程抓取（全量覆盖） ---------- #
    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(fetch_one, code, start, end, out_dir, args.defer_db)
            for code in codes
        ]
        for future in tqdm(as_completed(futures), total=len(futures), desc="下载进度"):
            try:
                future.result()
            except Exception as exc:
                failures += 1
                logger.error("股票下载失败: %s", exc)

    if args.defer_db:
        paths = [path for path in (out_dir / f"{code}.csv" for code in codes) if path.exists()]
        logger.info("下载结束，开始批量写入数据库（%d 个文件）...", len(paths))
        bar = tqdm(total=len(paths), desc="入库进度")
        save_csvs_batch(paths, category="stock", progress=lambda _: bar.update(1))
        bar.close()
        logger.info("批量入库完成")

    if failures:
        logger.error("%d 支股票下载失败", failures)
        sys.exit(1)

    logger.info("全部任务完成，数据已保存至 %s", out_dir.resolve())


if __name__ == "__main__":
    main()
