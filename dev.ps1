<#
.SYNOPSIS
    一键本地开发脚本（Flask 后端 + Vite 前端，支持热更新）
.DESCRIPTION
    同时启动后端 Flask 开发服务器和前端 Vite 开发服务器。
    前端修改即时热更新（HMR），后端修改需手动重启。
.PARAMETER BackendPort
    后端端口（默认 5000）
.PARAMETER FrontendPort
    前端端口（默认 5173）
.PARAMETER Database
    数据库文件路径（默认 .\data\subscription.db）
.EXAMPLE
    .\dev.ps1
    .\dev.ps1 -BackendPort 5001
    .\dev.ps1 -FrontendPort 3000 -Database C:\tmp\test.db
#>

param(
    [int]$BackendPort = 5000,
    [int]$FrontendPort = 5173,
    [string]$Database = ".\data\subscription.db"
)

$ErrorActionPreference = "Stop"

# ---- 进入项目根目录 ----
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

# ---- Python 环境 ----
$PythonBin = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $PythonBin = ".\.venv\Scripts\python.exe"
    Write-Host "📦 使用虚拟环境: .venv" -ForegroundColor Yellow
}

# ---- 安装后端依赖（幂等） ----
try {
    & $PythonBin -c "import flask, flask_sqlalchemy, flask_migrate" 2>$null
} catch {
    Write-Host "📦 安装后端 Python 依赖..." -ForegroundColor Yellow
    & $PythonBin -m pip install -r ".\app\backend\requirements.txt" -q
}

# ---- 安装前端依赖（幂等） ----
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 需要 Node.js，请先安装 https://nodejs.org/" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path ".\frontend\node_modules")) {
    Write-Host "📦 安装前端依赖 (npm install)..." -ForegroundColor Yellow
    Push-Location ".\frontend"
    npm install --silent
    Pop-Location
}

# ---- 初始化数据库（幂等） ----
$DatabaseAbs = (Resolve-Path $Database -ErrorAction SilentlyContinue)
if (-not $DatabaseAbs) {
    $DataDir = Split-Path -Parent $Database
    if ($DataDir -and -not (Test-Path $DataDir)) {
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    }
    $DatabaseAbs = Join-Path $RootDir $Database
}
$env:DATABASE_URL = "sqlite:///$($DatabaseAbs -replace '\\','/')"

if (-not (Test-Path $Database)) {
    Write-Host "🗄️  初始化数据库: $Database" -ForegroundColor Yellow
    $env:FLASK_APP = "app.backend:create_app()"
    & $PythonBin -m flask db upgrade
}

# ---- Flask 环境变量 ----
$env:FLASK_APP = "app.backend:create_app()"
$env:FLASK_DEBUG = "1"
$env:FLASK_RUN_PORT = $BackendPort

# ---- 启动后端（后台 Job） ----
Write-Host ""
Write-Host "🐍 启动后端 Flask 开发服务器 (端口 $BackendPort)..." -ForegroundColor Green
$BackendJob = Start-Job -ScriptBlock {
    param($PythonBin, $BackendPort)
    Set-Location $using:RootDir
    & $PythonBin -m flask run --host=0.0.0.0 --port=$BackendPort
} -ArgumentList $PythonBin, $BackendPort

# ---- 等待后端就绪 ----
for ($i = 0; $i -lt 30; $i++) {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/settings" -TimeoutSec 2 -ErrorAction Stop
        break
    } catch {
        Start-Sleep -Milliseconds 300
    }
}

# ---- 启动前端（前台） ----
Write-Host "⚡ 启动 Vite 前端开发服务器 (端口 $FrontendPort)..." -ForegroundColor Green
Write-Host ""
Write-Host "  ┌──────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "  │  🌐 前端页面  http://localhost:$FrontendPort        │" -ForegroundColor Cyan
Write-Host "  │  🔗 后端 API  http://localhost:$BackendPort/api     │" -ForegroundColor Cyan
Write-Host "  │  🛑 Ctrl+C 停止所有服务                   │" -ForegroundColor Cyan
Write-Host "  └──────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host ""

try {
    Push-Location ".\frontend"
    & npx vite --port $FrontendPort
} finally {
    Pop-Location
    # 清理后端进程
    Write-Host ""
    Write-Host "🛑 正在关闭后端服务..." -ForegroundColor Red
    Stop-Job -Job $BackendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $BackendJob -Force -ErrorAction SilentlyContinue
    Write-Host "👋 已退出" -ForegroundColor Yellow
}