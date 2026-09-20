#!/usr/bin/env bash
# Stock Analyse 一键开发环境启动（Linux/macOS）
# 后端/前端在当前终端后台运行，Ctrl+C 一起停
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

echo "========================================"
echo "  Stock Analyse 一键开发环境启动"
echo "========================================"

# 启动 Flask 后端 (后台，日志落 logs/backend.log)
echo "[1/2] 启动 Flask 后端 ..."
(
  cd "$ROOT/flask_backend"
  FLASK_DEBUG=true FLASK_HOST=127.0.0.1 FLASK_PORT=5000 \
    ./venv/bin/python app.py >>"$LOG_DIR/backend.log" 2>&1
) &

# 启动前端 dev (后台，日志落 logs/frontend.log)
echo "[2/2] 启动前端开发服务器 ..."
(
  cd "$ROOT/stock-line"
  npm run dev >>"$LOG_DIR/frontend.log" 2>&1
) &

echo
echo "已后台启动："
echo "  后端: http://127.0.0.1:5000   日志: logs/backend.log"
echo "  前端: 按 dev 输出端口 (默认 8000)  日志: logs/frontend.log"
echo

# 等待前端就绪后自动打开浏览器
echo "[3/3] 等待前端就绪后自动打开浏览器 ..."
URL=""
for i in $(seq 1 60); do
  if [ -f "$LOG_DIR/frontend.log" ]; then
    URL=$(grep -oE 'Local:[[:space:]]+http://localhost:[0-9]+' "$LOG_DIR/frontend.log" | tail -n 1 | awk '{print $2}')
    if [ -n "$URL" ]; then break; fi
  fi
  sleep 1
done
URL=${URL:-http://localhost:8000}
echo "[3/3] 打开浏览器: $URL"
( command -v xdg-open >/dev/null && xdg-open "$URL" ) \
  || ( command -v open >/dev/null && open "$URL" ) \
  || true
echo

echo "实时查看日志："
echo "  tail -f logs/backend.log"
echo "  tail -f logs/frontend.log"
echo
echo "停止：Ctrl+C 即可结束两个服务。"
echo

wait
