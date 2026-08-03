#!/usr/bin/env python3
"""
统一执行所有 fetch 脚本（除 fetch_kline.py 外）

资金流向脚本默认拉取全量数据：
  - 东财板块: 2023-09-12 ~ 今天
  - 同花顺概念: 2024-09-10 ~ 今天
  - 同花顺行业: 2024-09-10 ~ 今天
"""
import datetime as dt
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent

# 资金流向脚本的起始日期
MONEYFLOW_START = {
    "fetch_moneyflow_ind_dc.py": "20230912",
    "fetch_moneyflow_cnt_ths.py": "20240910",
    "fetch_moneyflow_ind_ths.py": "20240910",
}

today = dt.date.today().strftime("%Y%m%d")

SCRIPTS: list[tuple[str, list[str]]] = [
    ("fetch_etf.py", []),
    ("fetch_index.py", []),
    ("fetch_moneyflow_cnt_ths.py", ["--start", MONEYFLOW_START["fetch_moneyflow_cnt_ths.py"], "--end", today]),
    ("fetch_moneyflow_ind_dc.py", ["--start", MONEYFLOW_START["fetch_moneyflow_ind_dc.py"], "--end", today]),
    ("fetch_moneyflow_ind_ths.py", ["--start", MONEYFLOW_START["fetch_moneyflow_ind_ths.py"], "--end", today]),
]


def run_script(name: str, args: list[str]) -> bool:
    path = TOOLS_DIR / name
    cmd = [sys.executable, str(path)] + args

    print(f"\n{'=' * 60}")
    print(f"开始执行: {name} {' '.join(args)}")
    print(f"{'=' * 60}")

    result = subprocess.run(cmd, capture_output=False)

    ok = result.returncode == 0
    status = "✓ 完成" if ok else f"✗ 失败 (exit code {result.returncode})"
    print(f"{'=' * 60}")
    print(f"{name}: {status}")
    print(f"{'=' * 60}")
    print()
    return ok


def main():
    print("=== 统一执行数据拉取脚本 ===")
    print(f"共 {len(SCRIPTS)} 个脚本")
    print()

    success = 0
    fail = 0

    for script_name, script_args in SCRIPTS:
        if run_script(script_name, script_args):
            success += 1
        else:
            fail += 1

    print(f"\n全部完成: {success} 成功, {fail} 失败")

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()