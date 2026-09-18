<#
.SYNOPSIS
    全量本地代码质量门禁脚本 (Local CI Gate for Windows)
.DESCRIPTION
    一键运行与 GitHub Actions 相同的全部检查，确保推流 100% 绿标。
.EXAMPLE
    .\check.ps1
    .\check.ps1 -Fast
#>
param(
    [switch]$Fast
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "🚀 开始执行本地代码质量门禁检查 (Local CI)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# ---- 寻找 ruff ----
$RuffCmd = $null
if (Get-Command ruff -ErrorAction SilentlyContinue) {
    $RuffCmd = "ruff"
} elseif (Test-Path ".venv\Scripts\ruff.exe") {
    $RuffCmd = ".venv\Scripts\ruff.exe"
} elseif (Get-Command uvx -ErrorAction SilentlyContinue) {
    $RuffCmd = "uvx ruff"
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    $RuffCmd = "uv run ruff"
} else {
    Write-Error "❌ 未找到 ruff，请先安装或激活虚拟环境。"
}

# 1. 后端规范检查
Write-Host "`n🔍 [1/5] 后端代码规范检查 (ruff check)..." -ForegroundColor Yellow
Invoke-Expression "$RuffCmd check app/ tests/ tools/"
Write-Host "✅ 后端代码规范检查通过！" -ForegroundColor Green

# 2. 后端格式检查
Write-Host "`n🎨 [2/5] 后端代码格式检查 (ruff format --check)..." -ForegroundColor Yellow
Invoke-Expression "$RuffCmd format --check app/ tests/ tools/"
Write-Host "✅ 后端代码格式检查通过！" -ForegroundColor Green

# 3. 后端单元测试
if (-not $Fast) {
    Write-Host "`n🧪 [3/5] 后端测试套件 (pytest)..." -ForegroundColor Yellow
    if (Test-Path ".venv\Scripts\pytest.exe") {
        & .venv\Scripts\pytest.exe tests/ -v
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run --extra dev pytest tests/ -v
    } elseif (Get-Command pytest -ErrorAction SilentlyContinue) {
        & pytest tests/ -v
    } else {
        Write-Warning "⚠️ 未找到 pytest，跳过测试。"
    }
    Write-Host "✅ 后端测试套件全部通过！" -ForegroundColor Green
} else {
    Write-Host "`n⏩ [3/5] 跳过后端单元测试 (-Fast)" -ForegroundColor DarkGray
}

# 4. 前端检查
Write-Host "`n🌐 [4/5] 前端规范与路由双向绑定校验..." -ForegroundColor Yellow
if (Get-Command npm -ErrorAction SilentlyContinue) {
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "📦 安装前端依赖..." -ForegroundColor DarkGray
        npm --prefix frontend install --silent
    }
    npm run --prefix frontend check
    Write-Host "✅ 前端规范检查通过！" -ForegroundColor Green

    Write-Host "`n🧹 [5/5] 前端 ESLint 检查..." -ForegroundColor Yellow
    npm run --prefix frontend lint
    Write-Host "✅ 前端 ESLint 检查通过！" -ForegroundColor Green

    if (-not $Fast) {
        Write-Host "`n🏗️ [可选] 前端构建测试 (vite build)..." -ForegroundColor Yellow
        npm run --prefix frontend build
        Write-Host "✅ 前端构建测试通过！" -ForegroundColor Green
    }
} else {
    Write-Warning "⚠️ 未找到 npm，跳过前端检查。"
}

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "🎉 恭喜！全部门禁检查通过，代码符合规范，可放心推流 (git push)！" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
