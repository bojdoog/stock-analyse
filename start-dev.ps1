# Stock Analyse 一键开发环境启动 (PowerShell)
# 后端/前端在当前终端后台运行，Ctrl+C 一起停；前端就绪后自动打开浏览器。

$ErrorActionPreference = 'Stop'

# 项目根目录：本脚本所在目录的父目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = $ScriptDir
$LogDir    = Join-Path $Root 'logs'
$BackendLog     = Join-Path $LogDir 'backend.log'
$BackendErrLog  = Join-Path $LogDir 'backend.err.log'
$FrontendLog    = Join-Path $LogDir 'frontend.log'
$FrontendErrLog = Join-Path $LogDir 'frontend.err.log'
$PyExe       = Join-Path $Root 'flask_backend\venv\Scripts\python.exe'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# 清空旧日志（如果上一个进程仍持有句柄则忽略错误，不影响本次启动）
try { '' | Set-Content -LiteralPath $BackendLog     -Encoding UTF8 } catch {}
try { '' | Set-Content -LiteralPath $BackendErrLog  -Encoding UTF8 } catch {}
try { '' | Set-Content -LiteralPath $FrontendLog    -Encoding UTF8 } catch {}
try { '' | Set-Content -LiteralPath $FrontendErrLog -Encoding UTF8 } catch {}

Write-Host '========================================'
Write-Host '  Stock Analyse 一键开发环境启动'
Write-Host '  后端/前端在原终端后台运行；Ctrl+C 一起停'
Write-Host '========================================'
Write-Host ''

# ---------- 1. 启动 Flask 后端 ----------
Write-Host '[1/3] 启动 Flask 后端 ...'
$env:FLASK_DEBUG = 'true'
$env:FLASK_HOST  = '127.0.0.1'
$env:FLASK_PORT  = '5000'

$backend = Start-Process -FilePath $PyExe `
    -ArgumentList 'app.py' `
    -WorkingDirectory (Join-Path $Root 'flask_backend') `
    -RedirectStandardOutput $BackendLog `
    -RedirectStandardError  $BackendErrLog `
    -WindowStyle Hidden `
    -PassThru
Write-Host "       PID=$($backend.Id)  日志: $BackendLog"

# ---------- 2. 启动前端 dev ----------
Write-Host '[2/3] 启动前端开发服务器 ...'
$npmExe = (Get-Command npm.exe -ErrorAction SilentlyContinue).Source
if (-not $npmExe) { $npmExe = 'npm.cmd' }

$frontend = Start-Process -FilePath $npmExe `
    -ArgumentList 'run','dev' `
    -WorkingDirectory (Join-Path $Root 'stock-line') `
    -RedirectStandardOutput $FrontendLog `
    -RedirectStandardError  $FrontendErrLog `
    -WindowStyle Hidden `
    -PassThru
Write-Host "       PID=$($frontend.Id)  日志: $FrontendLog"

# ---------- 3. 等待前端就绪后自动打开浏览器 ----------
Write-Host '[3/3] 等待前端就绪后自动打开浏览器 ...'

$url = $null
for ($i = 0; $i -lt 60; $i++) {
    if (Test-Path -LiteralPath $FrontendLog) {
        try {
            $content = Get-Content -LiteralPath $FrontendLog -Raw -ErrorAction SilentlyContinue
            if ($content) {
                $m = [regex]::Match($content, 'Local:\s+(http://localhost:\d+)')
                if ($m.Success) { $url = $m.Groups[1].Value; break }
            }
        } catch {}
    }
    Start-Sleep -Seconds 1
}
if (-not $url) { $url = 'http://localhost:8000' }

Write-Host "[3/3] 打开浏览器: $url"
Start-Process $url | Out-Null

Write-Host ''
Write-Host '已后台启动:'
Write-Host "  后端: http://127.0.0.1:5000   日志: logs\backend.log"
Write-Host "  前端: $url  日志: logs\frontend.log"
Write-Host ''
Write-Host '实时查看日志:'
Write-Host '  Get-Content -Path .\logs\backend.log  -Wait'
Write-Host '  Get-Content -Path .\logs\frontend.log -Wait'
Write-Host ''
Write-Host '停止: 直接关闭此终端 / Ctrl+C 即可结束两个服务。'
Write-Host ''

# 保持脚本不退出，让 Ctrl+C 终止所有子进程后由本进程一并退出
try {
    while ($true) {
        if ($backend.HasExited -and $frontend.HasExited) { break }
        Start-Sleep -Seconds 1
    }
} finally {
    if (-not $backend.HasExited)  { Stop-Process -Id $backend.Id  -Force -ErrorAction SilentlyContinue }
    if (-not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue }
}
