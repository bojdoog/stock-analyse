@echo off
REM Stock Analyse unified data fetch entry point.
REM Implementation: fetch-data.ps1
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch-data.ps1"
