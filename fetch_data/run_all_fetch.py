#!/usr/bin/env python3
"""
统一拉取 ETF、指数、资金流向、指南针活跃市值缓存和推导原始数据。

资金流向脚本默认拉取全量数据：
  - 东财板块: 2023-09-12 ~ 今天
  - 同花顺概念: 2024-09-10 ~ 今天
  - 同花顺行业: 2024-09-10 ~ 今天
"""
import subprocess
import sys
from pathlib import Path

try:
    from .tushare_client import get_settings
except ImportError:
    from tushare_client import get_settings

try:
    from .trading_date import default_end_date
except ImportError:
    from trading_date import default_end_date

TOOLS_DIR = Path(__file__).resolve().parent
AMV_EMA20_SCRIPT = str(TOOLS_DIR.parent / "back_test_data" / "amv_research" / "formula.py")

SCRIPT_LABELS = {
    'fetch_compass_amv_daily.py': '指南针活跃市值日线（本地缓存增量）',
    'parse_compass_amv_cache.py': '指南针活跃市值分时（解析本地缓存）',
    'import_compass_amv_intraday.py': '指南针活跃市值分时（写库）',
    'fetch_etf.py': 'ETF 日线（Tushare 前复权）',
    'fetch_huijin_broad.py': '汇金系宽基 ETF 日线（Tushare 前复权）',
    'fetch_etf_mins.py': '汇金系宽基 ETF 分时（新浪 1 分钟线）',
    'fetch_index.py': '指数日线（Tushare）',
    'fetch_moneyflow_cnt_ths.py': '同花顺概念板块资金流（Tushare）',
    'fetch_moneyflow_ind_dc.py': '东方财富行业资金流（Tushare）',
    'fetch_moneyflow_ind_ths.py': '同花顺行业资金流（Tushare）',
    'download_amv_research.py': '活跃市值研究输入（Tushare 行业+资金流快照）',
    AMV_EMA20_SCRIPT: '活跃市值(THS反推EMA20)生成（入库+CSV）',
}

# 资金流向脚本的起始日期
MONEYFLOW_START = {
    "fetch_moneyflow_ind_dc.py": "20230912",
    "fetch_moneyflow_cnt_ths.py": "20240910",
    "fetch_moneyflow_ind_ths.py": "20240910",
}

end_date = default_end_date()

SCRIPTS: list[tuple[str, list[str]]] = [
    ("fetch_compass_amv_daily.py", []),
    ("parse_compass_amv_cache.py", ["--split-by-date", "--output", str(TOOLS_DIR.parent / "data" / "core_index" / "0AMV-intraday")]),
    ("import_compass_amv_intraday.py", []),
    ("fetch_etf.py", []),
    ("fetch_huijin_broad.py", []),
    ("fetch_etf_mins.py", []),
    ("fetch_index.py", []),
    ("fetch_moneyflow_cnt_ths.py", ["--start", MONEYFLOW_START["fetch_moneyflow_cnt_ths.py"], "--end", end_date]),
    ("fetch_moneyflow_ind_dc.py", ["--start", MONEYFLOW_START["fetch_moneyflow_ind_dc.py"], "--end", end_date]),
    ("fetch_moneyflow_ind_ths.py", ["--start", MONEYFLOW_START["fetch_moneyflow_ind_ths.py"], "--end", end_date]),
    ("download_amv_research.py", ["--start", "20240910", "--end", end_date]),
]

# 派生指标：在拉取阶段完成后执行，读取已更新的行业日线与指数量额，入库并导出 CSV
BUILD_SCRIPTS: list[tuple[str, list[str]]] = [
    (AMV_EMA20_SCRIPT, []),
]


def run_script(name: str, args: list[str], index: int, total: int) -> bool | None:
    path = Path(name)
    if not path.is_absolute():
        path = TOOLS_DIR / path
    label = SCRIPT_LABELS.get(name, Path(name).name)
    cmd = [sys.executable, str(path)] + args

    print(f"\n{'=' * 60}")
    print(f"[{index}/{total}] {label}  ({Path(name).name} {' '.join(args)})")
    print(f"{'=' * 60}")

    result = subprocess.run(cmd, capture_output=False)

    ok = None if result.returncode == 3 else result.returncode == 0
    status = "[SKIP] 存在无权限数据，已跳过" if ok is None else ("[OK] 完成" if ok else f"[FAIL] 失败 (exit code {result.returncode})")
    print(f"{'=' * 60}")
    print(f"{label}: {status}")
    print(f"{'=' * 60}")
    print()
    return ok


def main():
    print("=== 统一执行数据拉取脚本 ===")
    print(f"共 {len(SCRIPTS) + len(BUILD_SCRIPTS)} 个脚本（{len(SCRIPTS)} 拉取 + {len(BUILD_SCRIPTS)} 派生），结束日期 {end_date}")

    settings = get_settings()
    print(f"Tushare: {settings['provider']} | {settings['url']}", flush=True)

    success = []
    fail = []
    skipped = []
    results = {}

    total = len(SCRIPTS) + len(BUILD_SCRIPTS)
    for position, (script_name, script_args) in enumerate(SCRIPTS, start=1):
        if script_name == 'import_compass_amv_intraday.py' and not results.get('parse_compass_amv_cache.py'):
            print('[SKIP] 分时解析失败，跳过入库，避免把旧CSV当成本次更新。')
            results[script_name] = None
            skipped.append(script_name)
            continue
        results[script_name] = run_script(script_name, script_args, position, total)
        if results[script_name] is None:
            skipped.append(script_name)
        elif results[script_name]:
            success.append(script_name)
        else:
            fail.append(script_name)

    # 派生指标依赖当日指数与行业数据，上游未更新成功时跳过，避免用旧数据算出新日期
    for position, (script_name, script_args) in enumerate(BUILD_SCRIPTS, start=len(SCRIPTS) + 1):
        if not (results.get('fetch_index.py') and results.get('download_amv_research.py')):
            print('[SKIP] 指数或行业研究数据未成功更新，跳过派生指标生成。')
            results[script_name] = None
            skipped.append(script_name)
            continue
        results[script_name] = run_script(script_name, script_args, position, total)
        if results[script_name] is None:
            skipped.append(script_name)
        elif results[script_name]:
            success.append(script_name)
        else:
            fail.append(script_name)

    print(f"\n{'=' * 60}")
    print(f"汇总：{len(success)} 成功, {len(fail)} 失败, {len(skipped)} 跳过（结束日期 {end_date}）")
    for prefix, names in (('[OK]', success), ('[FAIL]', fail), ('[SKIP]', skipped)):
        for name in names:
            print(f"  {prefix} {SCRIPT_LABELS.get(name, Path(name).name)}  ({Path(name).name})")

    if fail:
        sys.exit(1)
    if skipped:
        sys.exit(3)


if __name__ == "__main__":
    main()
