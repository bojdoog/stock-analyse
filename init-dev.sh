#!/usr/bin/env bash
# Stock Analyse 环境初始化（Linux / macOS）
# 作用：创建后端 venv、安装前后端依赖、初始化数据库结构。可重复执行。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/flask_backend"
FRONTEND="$ROOT/stock-line"
VENV="$BACKEND/venv"
PY="$VENV/bin/python"

step() { printf '\n== %s ==\n' "$1"; }
fail() { printf '[错误] %s\n' "$1" >&2; exit 1; }

printf '========================================\n'
printf '  Stock Analyse 环境初始化\n'
printf '========================================\n'

step '1/4 检查 Python 并准备虚拟环境'
command -v python3 >/dev/null 2>&1 || fail '未找到 python3，请先安装 Python 3.9+。'
if [ ! -x "$PY" ]; then
  printf '创建虚拟环境 flask_backend/venv ...\n'
  python3 -m venv "$VENV"
fi
[ -x "$PY" ] || fail '虚拟环境创建失败，请检查 python3-venv 是否已安装。'
printf '使用 Python: %s\n' "$("$PY" --version)"

step '2/4 安装后端依赖'
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$BACKEND/requirements.txt"

step '3/4 安装前端依赖'
command -v npm >/dev/null 2>&1 || fail '未找到 npm，请先安装 Node.js 18+。'
printf '使用 Node: %s\n' "$(node --version)"
if [ ! -d "$FRONTEND/node_modules" ]; then
  ( cd "$FRONTEND" && npm install )
else
  printf 'stock-line/node_modules 已存在，跳过 npm install。\n'
fi

step '4/4 初始化数据库'
( cd "$BACKEND" && "$PY" -c "from market_store import initialize; initialize(); print('数据库结构已就绪')" )
printf 'SQLite: flask_backend/instance/stock_analyse.sqlite3（设置 DATABASE_PATH=mysql 时优先使用 MySQL）\n'

printf '\n初始化完成。\n'
printf '  启动: bash start-dev.sh\n'
printf '  数据: 启动后可在页面控制台抓取；或先按 fetch_data/requirements.txt 装好 pandas/tushare 再运行 fetch_data/run_all_fetch.py\n'
printf '  说明: 首次初始化只有表结构与默认指标，行情数据为空。\n'
