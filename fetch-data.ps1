# Stock Analyse 统一拉取数据脚本 (PowerShell)
# 运行 run_all_fetch.py 拉取行情、资金流向和活跃市值研究数据（耗时较久，请耐心等待）。

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = $ScriptDir
$Py        = "$env:USERPROFILE\miniconda3\python.exe"
$Script    = Join-Path $Root 'fetch_data\run_all_fetch.py'

if (-not (Test-Path -LiteralPath $Py)) {
    Write-Host "[错误] 未找到 Python: $Py" -ForegroundColor Red
    Write-Host "       请检查 miniconda 安装路径，或修改本脚本顶部变量。"
    exit 1
}
if (-not (Test-Path -LiteralPath $Script)) {
    Write-Host "[错误] 未找到脚本: $Script" -ForegroundColor Red
    exit 1
}

Write-Host '========================================'
Write-Host '  Stock Analyse 统一数据拉取'
Write-Host '  (ETF / 指数 / 资金流向 / 活跃市值研究)'
Write-Host '========================================'
Write-Host ''
Write-Host "使用 Python: $Py"
Write-Host "执行脚本: $Script"
Write-Host ''

& $Py $Script
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host '数据拉取成功。' -ForegroundColor Green
} else {
    Write-Host "数据拉取失败，退出码: $code" -ForegroundColor Red
}
Write-Host ''
Write-Host '按回车键退出...'
Read-Host | Out-Null
