# 打包前构建：将 Vue 前端产物同步到 app/www（fnOS 打包器直接收录 app/www）
#
#   .\build.ps1               # 完整流程：npm install(如缺) → vite build → 同步 app/www
#   之后运行 fnpack build 即可产出 fpk。
#
# 注意：本脚本会覆盖 app/www（vanilla 原生版保留在 git 历史中，
# 如需恢复执行：git checkout -- app/www）。
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

function Assert-ExitCode {
    param([string]$Name)
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("错误：$Name 失败（退出码 $LASTEXITCODE）")
        exit $LASTEXITCODE
    }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine("错误：打包前端需要 node/npm")
    exit 1
}

if (-not (Test-Path (Join-Path $PSScriptRoot "frontend\node_modules"))) {
    Write-Host "==> 安装前端依赖 (npm install)"
    Push-Location (Join-Path $PSScriptRoot "frontend")
    try {
        npm install
        Assert-ExitCode "npm install"
    } finally {
        Pop-Location
    }
}

Write-Host "==> 构建 Vue 前端 (frontend/dist)"
Push-Location (Join-Path $PSScriptRoot "frontend")
try {
    npx vite build
    Assert-ExitCode "vite build"
} finally {
    Pop-Location
}

Write-Host "==> 同步 dist → app/www"
$www = Join-Path $PSScriptRoot "app\www"
$dist = Join-Path $PSScriptRoot "frontend\dist"
if (Test-Path $www) {
    Remove-Item $www -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $www | Out-Null
Copy-Item -Path (Join-Path $dist "*") -Destination $www -Recurse -Force
Write-Host "    app/www 内容:"
Get-ChildItem $www | ForEach-Object { Write-Host $_.Name }

# 清理 Python 缓存，避免 fnpack 把 __pycache__/*.pyc 打进包
Write-Host "==> 清理 Python 缓存 (__pycache__)"
$appDir = Join-Path $PSScriptRoot "app"
if (Test-Path $appDir) {
    Get-ChildItem -Path $appDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "==> 完成。下一步运行: fnpack build"
Write-Host "    (本地预览: .\dev.sh；打包 CLI 见 https://developer.fnnas.com/docs/cli/fnpack/)"
