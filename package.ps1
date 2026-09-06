# 一键打包流程：构建前端 -> 生成图标 -> 干净暂存（可选升版本）-> fnpack -> 校验
#
# 流程：
#   1. .\build.ps1                # 前端构建 & 资源同步 & 清理缓存
#   2. python tools/gen_icons.py  # 图标生成
#   3. tools/vendor_deps.py       # 预置 Linux cp312 轮子到 app/backend/vendor
#   4. tools/fpk_stage.py prepare # 排除 .venv/.idea 等；默认只在暂存目录自增 version
#   5. fnpack build -d <stage>    # 只打包干净目录
#   6. tools/fpk_stage.py finalize# 校验通过后才把新版本写回仓库 manifest
#
# 用法：
#   .\package.ps1
#   $env:NO_BUMP = "1"; .\package.ps1
#   .\package.ps1 -NoBump
#   $env:SKIP_VERIFY = "1"; .\package.ps1   # 跳过 fpk 校验（不推荐）
#
param(
    [switch]$NoBump
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot
if (-not $env:PYTHONIOENCODING) {
    $env:PYTHONIOENCODING = "utf-8"
}

function Assert-ExitCode {
    param([string]$Name)
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("错误：$Name 失败（退出码 $LASTEXITCODE）")
        exit $LASTEXITCODE
    }
}

function ConvertTo-FnpackExe {
    param([Parameter(Mandatory = $true)][string]$Source)
    if ($Source -like '*.exe') {
        return $Source
    }
    # PowerShell 的 & 无法启动无 .exe 后缀的 Win32 程序（Git Bash 可以），
    # 这里复制一份带后缀的可执行文件再调用。
    $destDir = Join-Path $PSScriptRoot ".tmp"
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $dest = Join-Path $destDir "fnpack.exe"
    Copy-Item -LiteralPath $Source -Destination $dest -Force
    return $dest
}

function Invoke-FnpackBuild {
    param(
        [Parameter(Mandatory = $true)][string]$Bin,
        [Parameter(Mandatory = $true)][string]$Stage
    )
    $exe = ConvertTo-FnpackExe -Source $Bin
    Write-Host "    实际执行: $exe build --directory $Stage"
    & $exe build --directory $Stage
    if ($null -eq $LASTEXITCODE) {
        [Console]::Error.WriteLine("错误：fnpack 未能启动（PowerShell LASTEXITCODE 为空）")
        exit 1
    }
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("错误：fnpack 失败（退出码 $LASTEXITCODE）")
        exit $LASTEXITCODE
    }
}

function Resolve-PythonCmd {
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $cmd) {
            return $cmd.Source
        }
    }
    [Console]::Error.WriteLine("错误：未找到 Python，请先安装 Python。")
    exit 1
}

$PythonCmd = Resolve-PythonCmd

$skipBump = $NoBump -or ($env:NO_BUMP -eq "1")

# 1. 前端构建（子进程调用，等价于 bash ./build.sh）
Write-Host "==> [1/6] 执行前端构建 (build.ps1)..."
if ($PSVersionTable.PSEdition -eq "Core") {
    $hostExe = Join-Path $PSHOME "pwsh.exe"
} else {
    $hostExe = Join-Path $PSHOME "powershell.exe"
}
& $hostExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build.ps1")
Assert-ExitCode "build.ps1"

# 2. 图标生成
Write-Host "==> [2/6] 执行图标生成 (tools/gen_icons.py)..."
& $PythonCmd (Join-Path $PSScriptRoot "tools\gen_icons.py")
Assert-ExitCode "tools/gen_icons.py"

# 3. 预置飞牛可用的 Linux 依赖（不要在 NAS 上 pip install 系统 Python）
Write-Host "==> [3/6] 预置 Linux vendor 依赖..."
& $PythonCmd (Join-Path $PSScriptRoot "tools\vendor_deps.py")
Assert-ExitCode "tools/vendor_deps.py"

# 4. 生成干净暂存目录（版本号只改暂存副本，失败不会污染仓库 manifest）
Write-Host "==> [4/6] 准备干净打包目录..."
$prepareArgs = @((Join-Path $PSScriptRoot "tools\fpk_stage.py"), "prepare")
if (-not $skipBump) {
    $prepareArgs += "--bump"
} else {
    Write-Host "    跳过版本自增 (NO_BUMP=1)"
}
$STAGE = (& $PythonCmd @prepareArgs | Select-Object -Last 1)
Assert-ExitCode "fpk_stage.py prepare"
if ([string]::IsNullOrWhiteSpace($STAGE)) {
    [Console]::Error.WriteLine("错误：未能得到打包暂存目录")
    exit 1
}
$STAGE = $STAGE.Trim()

# 5. fnpack 打包
Write-Host "==> [5/6] 执行 fnpack 打包..."

if ($env:OS -match "Windows") {
    $OS_NAME = "windows"
} else {
    $OS_NAME = [System.Environment]::OSVersion.Platform.ToString().ToLowerInvariant()
    if ($OS_NAME -match "unix|linux") { $OS_NAME = "linux" }
    elseif ($OS_NAME -match "macos|darwin") { $OS_NAME = "darwin" }
}

$arch = $env:PROCESSOR_ARCHITECTURE
if ([string]::IsNullOrEmpty($arch) -and -not [string]::IsNullOrEmpty($env:PROCESSOR_ARCHITEW6432)) {
    $arch = $env:PROCESSOR_ARCHITEW6432
}
switch -Regex ($arch) {
    "^(AMD64|x86_64|x64)$" { $ARCH_NAME = "amd64" }
    "^(ARM64|aarch64)$" { $ARCH_NAME = "arm64" }
    default {
        if ($arch -eq "x86" -and $env:PROCESSOR_ARCHITEW6432 -match "AMD64|x86_64|x64") {
            $ARCH_NAME = "amd64"
        } else {
            $ARCH_NAME = "$arch".ToLowerInvariant()
        }
    }
}

$packageDir = Join-Path $PSScriptRoot "tools\package"
$glob = "fnpack*-$OS_NAME-$ARCH_NAME*"
$FNPACK_BIN = $null
if (Test-Path $packageDir) {
    $FNPACK_BIN = Get-ChildItem -Path $packageDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like $glob } |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not [string]::IsNullOrEmpty($FNPACK_BIN)) {
    Write-Host "    检测到平台: ${OS_NAME}-${ARCH_NAME}，使用预置打包工具: $FNPACK_BIN"
    Invoke-FnpackBuild -Bin $FNPACK_BIN -Stage $STAGE
} elseif (Get-Command fnpack -ErrorAction SilentlyContinue) {
    Write-Host "    未在 tools/package 找到对应平台的预置文件（${OS_NAME}-${ARCH_NAME}），使用系统 fnpack"
    $fnpackCmd = (Get-Command fnpack).Source
    Invoke-FnpackBuild -Bin $fnpackCmd -Stage $STAGE
} else {
    [Console]::Error.WriteLine("错误：未在 tools/package 找到适用于 ${OS_NAME}-${ARCH_NAME} 的打包工具，系统 PATH 中也未找到 'fnpack' 命令。")
    exit 1
}

Write-Host "==> [6/6] 规范化权限并校验 app.tgz..."
$finalizeArgs = @((Join-Path $PSScriptRoot "tools\fpk_stage.py"), "finalize", "--stage", $STAGE)
$FPK_PATH = (& $PythonCmd @finalizeArgs | Select-Object -Last 1)
Assert-ExitCode "fpk_stage.py finalize"

Write-Host "==> 打包成功完成: $FPK_PATH"
