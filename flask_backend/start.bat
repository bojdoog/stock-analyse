@echo off
chcp 65001 >nul
echo ========================================
echo   Flask 后端启动脚本
echo   Stock Analyse API Server
echo ========================================
echo.

REM 检查 Python 是否安装
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 检查虚拟环境
if not exist "venv" (
    echo [信息] 创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装依赖
echo [信息] 安装依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM 设置环境变量
set FLASK_DEBUG=true
set FLASK_HOST=0.0.0.0
set FLASK_PORT=5000

echo.
echo [启动] Flask 服务器启动中...
echo [访问] http://localhost:5000
echo.

REM 启动 Flask
python app.py
pause
