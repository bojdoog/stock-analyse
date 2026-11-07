# Stock Analyse 环境初始化（Windows）
# 作用：创建后端 venv、安装前后端依赖、初始化数据库结构。可重复执行。

$ErrorActionPreference = 'Stop'
$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend  = Join-Path $Root 'flask_backend'
$Frontend = Join-Path $Root 'stock-line'
$Venv     = Join-Path $Backend 'venv'
$Py       = Join-Path $Venv 'Scripts\python.exe'

function Step($text) { Write-Host "`n== $text ==" -ForegroundColor Cyan }
function Fail($text) { Write-Host "[错误] $text" -ForegroundColor Red; exit 1 }

Write-Host '========================================'
Write-Host '  Stock Analyse 环境初始化'
Write-Host '========================================'

# ---------- 1. Python 与虚拟环境 ----------
Step '1/4 检查 Python 并准备虚拟环境'
$Launcher     = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
$SystemPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $Launcher -and -not $SystemPython) { Fail '未找到 Python，请先安装 Python 3.9+，并在安装时勾选 "Add python.exe to PATH"。' }

if (-not (Test-Path -LiteralPath $Py)) {
    Write-Host '创建虚拟环境 flask_backend\venv ...'
    if ($Launcher) { & $Launcher -3 -m venv $Venv } else { & $SystemPython -m venv $Venv }
}
if (-not (Test-Path -LiteralPath $Py)) { Fail '虚拟环境创建失败，请检查 Python 安装是否完整。' }
Write-Host ('使用 Python: ' + (& $Py --version))

# ---------- 2. 后端依赖 ----------
Step '2/4 安装后端依赖'
& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $Backend 'requirements.txt')

# ---------- 3. 前端依赖 ----------
Step '3/4 安装前端依赖'
$Npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $Npm) { $Npm = (Get-Command npm -ErrorAction SilentlyContinue).Source }
if (-not $Npm) { Fail '未找到 npm，请先安装 Node.js 18+。' }
$Node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
if ($Node) { Write-Host ('使用 Node: ' + (& $Node --version)) }
if (-not (Test-Path -LiteralPath (Join-Path $Frontend 'node_modules'))) {
    Push-Location $Frontend
    try { & $Npm install } finally { Pop-Location }
} else {
    Write-Host 'stock-line\node_modules 已存在，跳过 npm install。'
}

# ---------- 4. 数据库 ----------
Step '4/4 初始化数据库'
Push-Location $Backend
try {
    & $Py -c "from market_store import initialize; initialize(); print('数据库结构已就绪')"
} finally { Pop-Location }
Write-Host 'SQLite: flask_backend\instance\stock_analyse.sqlite3（设置 DATABASE_PATH=mysql 时优先使用 MySQL）'

Write-Host ''
Write-Host '初始化完成。' -ForegroundColor Green
Write-Host '  启动: 双击 start-dev.bat（或 powershell -ExecutionPolicy Bypass -File .\start-dev.ps1）'
Write-Host '  数据: 启动后可在页面控制台抓取；或先按 fetch_data\requirements.txt 装好 pandas/tushare 再运行 fetch-data.bat'
Write-Host '  说明: 首次初始化只有表结构与默认指标，行情数据为空。'
