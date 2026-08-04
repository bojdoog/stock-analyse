#!/bin/bash
set -e

echo "========================================"
echo "  Flask 后端启动脚本"
echo "  Stock Analyse API Server"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.8+"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[信息] 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "[信息] 安装依赖..."
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 安装数据拉取脚本的依赖（如需）
if [ -f "utils/fetch_data/requirements.txt" ]; then
    pip install -r utils/fetch_data/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
fi

# 设置环境变量
export FLASK_DEBUG=true
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000

echo ""
echo "[启动] Flask 服务器启动中..."
echo "[访问] http://localhost:5000"
echo ""

# 启动 Flask
python app.py