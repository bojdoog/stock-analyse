@echo off
REM ===========================================
REM   Stock Analyse 统一数据拉取（入口）
REM   双击此文件即可，逻辑在 fetch-data.ps1
REM ===========================================
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch-data.ps1"