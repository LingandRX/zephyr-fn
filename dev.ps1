<#
.SYNOPSIS
    一键本地开发脚本（Flask 后端 + Vite 前端，支持热更新）
.DESCRIPTION
    同时启动后端 Flask 开发服务器和前端 Vite 开发服务器。
    前端修改即时热更新（HMR），后端修改需手动重启。
.PARAMETER BackendPort
    后端端口（默认 3001）
.PARAMETER FrontendPort
    前端端口（默认 5173）
.PARAMETER Database
    数据库文件路径（默认 .\data\subscription.db）
.EXAMPLE
    .\dev.ps1
    .\dev.ps1 -BackendPort 3001
    .\dev.ps1 -FrontendPort 3000 -Database C:\tmp\test.db
#>

param(
    [int]$BackendPort = 3001,
    [int]$FrontendPort = 5173,
    [string]$Database = ".\data\subscription.db"
)

$ErrorActionPreference = "Stop"

# ---- 进入项目根目录 ----
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir
 
# ---- 自动激活项目 Git Hook 门禁 ----
if ((Test-Path ".githooks") -and (Get-Command git -ErrorAction SilentlyContinue)) {
    try { & git config core.hooksPath .githooks 2>$null | Out-Null } catch {}
}

$BackendProc = $null

# 终止后端进程树。
# FLASK_DEBUG=1 下 werkzeug reloader 会派生一个真正监听端口的子进程，
# 只杀父进程会留下孤儿继续占用端口，导致下次启动撞端口 → 必须 /T 整棵树终止。
function Stop-Backend {
    if ($null -ne $BackendProc -and -not $BackendProc.HasExited) {
        & taskkill /PID $BackendProc.Id /T /F 2>$null | Out-Null
    }
}

# 返回监听指定端口的进程 PID，无监听则返回 $null。
# 优先用 Get-NetTCPConnection（不受系统语言影响），不可用时回退 netstat。
function Get-PortListenerPid([int]$Port) {
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conn) { return ($conn | Select-Object -First 1).OwningProcess }
        return $null
    }
    $line = netstat -ano | Select-String -Pattern "[:.]$Port\s+\S+\s+LISTENING" | Select-Object -First 1
    if ($line) { return [int](($line.ToString().Trim() -split '\s+')[-1]) }
    return $null
}

# ---- Python 环境 ----
$PythonBin = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    # 绝对路径：Start-Process 对相对 FilePath 的解析基准与 -WorkingDirectory 不一致
    $PythonBin = Join-Path $RootDir ".venv\Scripts\python.exe"
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
# 后端只认 DB_PATH（见 app/backend/paths.py:db_path()），且要的是文件路径而非
# SQLAlchemy URI；原先导出 DATABASE_URL 不被任何代码读取，-Database 属于空转。
$env:DB_PATH = "$DatabaseAbs"

if (-not (Test-Path $Database)) {
    Write-Host "🗄️  初始化数据库: $Database" -ForegroundColor Yellow
    $env:FLASK_APP = "app.backend:create_app()"
    & $PythonBin -m flask db upgrade
}

# ---- Flask 环境变量 ----
$env:FLASK_APP = "app.backend:create_app()"
$env:FLASK_DEBUG = "1"
$env:FLASK_RUN_PORT = $BackendPort
# Vite 用同名变量决定 /api 的代理目标（见 frontend/vite.config.mjs）。
# 不导出时会回退到 5000，导致前端满屏 ECONNREFUSED 127.0.0.1:5000。
$env:BACKEND_PORT = $BackendPort

# ---- 后端日志 ----
$LogDir = Join-Path $RootDir "data\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$BackendLog = Join-Path $LogDir "dev-backend.log"
$BackendErrLog = Join-Path $LogDir "dev-backend.err.log"

# ---- 端口占用预检 ----
# 上次异常退出残留的进程（reloader 子进程尤其容易）会占着端口，
# 这里提前拦截并给出确切 PID，避免 Flask/Vite 报难懂的 bind 错误。
foreach ($svc in @(@{ Name = "后端"; Port = $BackendPort }, @{ Name = "前端"; Port = $FrontendPort })) {
    $owner = Get-PortListenerPid $svc.Port
    if ($owner) {
        Write-Host "❌ $($svc.Name)端口 $($svc.Port) 已被 PID $owner 占用" -ForegroundColor Red
        Write-Host "   释放: taskkill /PID $owner /T /F" -ForegroundColor Red
        exit 1
    }
}

# ---- 启动后端（后台进程，输出落盘） ----
Write-Host ""
Write-Host "🐍 启动后端 Flask 开发服务器 (端口 $BackendPort)..." -ForegroundColor Green
# 用 Start-Process 而非 Start-Job，原因有二：
#   1) 拿到真实 PID，才能连同 reloader 子进程一起终止（Stop-Job 会漏杀，留下孤儿占端口）
#   2) 输出重定向到日志文件，否则 Job 的输出流不会显示，后端报错完全不可见
# 注意：-RedirectStandardOutput 与 -RedirectStandardError 不能指向同一个文件
$BackendProc = Start-Process -FilePath $PythonBin `
    -ArgumentList @("-m", "flask", "run", "--host=0.0.0.0", "--port=$BackendPort") `
    -WorkingDirectory $RootDir -NoNewWindow -PassThru `
    -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErrLog

# ---- 等待后端就绪（后端崩溃立即中止，不再空等） ----
$Ready = $false
for ($i = 0; $i -lt 40; $i++) {
    if ($BackendProc.HasExited) { break }   # 后端进程已退出，继续等没有意义
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/settings" `
            -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        $Ready = $true
        break
    } catch {
        Start-Sleep -Milliseconds 300
    }
}

if (-not $Ready) {
    Write-Host ""
    Write-Host "❌ 后端未能在 http://127.0.0.1:$BackendPort 就绪，已中止（不启动前端）" -ForegroundColor Red
    Write-Host "后端日志末尾：" -ForegroundColor Red
    Write-Host ("-" * 60) -ForegroundColor Red
    foreach ($f in @($BackendLog, $BackendErrLog)) {
        if (Test-Path $f) { Get-Content $f -Tail 30 }
    }
    Write-Host ("-" * 60) -ForegroundColor Red
    Write-Host "完整日志: $BackendLog    $BackendErrLog" -ForegroundColor Red
    Stop-Backend
    exit 1
}

# ---- 启动前端（前台） ----
Write-Host "⚡ 启动 Vite 前端开发服务器 (端口 $FrontendPort)..." -ForegroundColor Green
Write-Host ""
Write-Host "  ┌──────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "  │  🌐 前端页面  http://localhost:$FrontendPort        │" -ForegroundColor Cyan
Write-Host "  │  🔗 后端 API  http://localhost:$BackendPort/api     │" -ForegroundColor Cyan
Write-Host "  │  🛑 Ctrl+C 停止所有服务                   │" -ForegroundColor Cyan
Write-Host "  └──────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host "  📄 后端日志  $BackendLog" -ForegroundColor Cyan
Write-Host "  📄 后端错误  $BackendErrLog" -ForegroundColor Cyan
Write-Host ""

try {
    Push-Location ".\frontend"
    & npx vite --port $FrontendPort
} finally {
    Pop-Location
    # 清理后端进程（含 reloader 子进程）
    Write-Host ""
    Write-Host "🛑 正在关闭后端服务..." -ForegroundColor Red
    Stop-Backend
    Write-Host "👋 已退出" -ForegroundColor Yellow
}