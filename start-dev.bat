@echo off
REM ===========================================
REM   Stock Analyse 一键开发环境启动（入口）
REM   双击此文件即可，逻辑在 start-dev.ps1
REM   注意：不要 chcp 65001，会与 PowerShell 子进程的字符串解析冲突
REM ===========================================
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1"
