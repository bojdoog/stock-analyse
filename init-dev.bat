@echo off
REM Stock Analyse 环境初始化入口：双击运行，具体逻辑在 init-dev.ps1
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0init-dev.ps1"
pause
