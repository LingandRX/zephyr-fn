#!/usr/bin/env bash
# 一键打包流程：构建前端 -> 干净暂存（可选升版本）-> fnpack -> 校验
#
# 流程：
#   1. ./build.sh                 # 前端构建 & 资源同步 & 清理缓存
#   2. tools/vendor_deps.py       # 预置 Linux cp312 轮子到 app/backend/vendor
#   3. tools/fpk_stage.py prepare # 排除 .venv/.idea 等；默认只在暂存目录自增 version
#   4. fnpack build -d <stage>    # 只打包干净目录
#   5. tools/fpk_stage.py finalize# 校验通过后才把新版本写回仓库 manifest
#
# 环境变量：
#   NO_BUMP=1       跳过版本自增
#   SKIP_VERIFY=1   跳过 fpk 校验（不推荐）
#
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

# 自动检测 Python 命令 (Windows 通常是 python, Linux/macOS 通常是 python3)
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "错误：未找到 Python，请先安装 Python。" >&2
  exit 1
fi

# 1. 前端构建
echo "==> [1/5] 执行前端构建 (build.sh)..."
bash ./build.sh

# 2. 预置飞牛可用的 Linux 依赖（不要在 NAS 上 pip install 系统 Python）
echo "==> [2/5] 预置 Linux vendor 依赖..."
$PYTHON_CMD tools/vendor_deps.py

# 3. 生成干净暂存目录（版本号只改暂存副本，失败不会污染仓库 manifest）
echo "==> [3/5] 准备干净打包目录..."
PREPARE_ARGS=(prepare)
if [ "${NO_BUMP:-0}" != "1" ]; then
  PREPARE_ARGS+=(--bump)
else
  echo "    跳过版本自增 (NO_BUMP=1)"
fi
STAGE="$($PYTHON_CMD tools/fpk_stage.py "${PREPARE_ARGS[@]}")"

# 4. fnpack 打包
echo "==> [4/5] 执行 fnpack 打包..."

# 检测平台与架构
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m | tr '[:upper:]' '[:lower:]')"

case "$OS" in
  darwin)
    OS_NAME="darwin"
    ;;
  linux)
    OS_NAME="linux"
    ;;
  cygwin*|mingw*|msys*|windows*)
    OS_NAME="windows"
    ;;
  *)
    OS_NAME="$OS"
    ;;
esac

case "$ARCH" in
  x86_64|amd64|x64)
    ARCH_NAME="amd64"
    ;;
  arm64|aarch64)
    ARCH_NAME="arm64"
    ;;
  *)
    ARCH_NAME="$ARCH"
    ;;
esac

# 查找 tools/package 下匹配当前平台与架构的二进制
FNPACK_BIN=""
for candidate in tools/package/fnpack*-"${OS_NAME}-${ARCH_NAME}"*; do
  if [ -f "$candidate" ]; then
    FNPACK_BIN="$candidate"
    break
  fi
done

if [ -n "$FNPACK_BIN" ]; then
  echo "    检测到平台: ${OS_NAME}-${ARCH_NAME}，使用预置打包工具: $FNPACK_BIN"
  chmod +x "$FNPACK_BIN" 2>/dev/null || true
  "./$FNPACK_BIN" build --directory "$STAGE"
elif command -v fnpack >/dev/null 2>&1; then
  echo "    未在 tools/package 找到对应平台的预置文件（${OS_NAME}-${ARCH_NAME}），使用系统 fnpack"
  fnpack build --directory "$STAGE"
else
  echo "错误：未在 tools/package 找到适用于 ${OS_NAME}-${ARCH_NAME} 的打包工具，系统 PATH 中也未找到 'fnpack' 命令。" >&2
  exit 1
fi

echo "==> [5/5] 规范化权限并校验 app.tgz..."
FPK_PATH="$($PYTHON_CMD tools/fpk_stage.py finalize --stage "$STAGE")"

echo "==> 打包成功完成: $FPK_PATH"
