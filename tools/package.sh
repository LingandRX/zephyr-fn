#!/usr/bin/env bash
# 一键打包流程：构建前端 -> 生成图标 -> 执行 fnpack 打包
#
# 流程：
#   1. ./tools/build.sh          # 前端构建 & 资源同步 & 清理缓存
#   2. python3 tools/gen_icons.py # 图标生成
#   3. fnpack build              # 最终打包
#
set -euo pipefail
cd "$(dirname "$0")/.."

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
echo "==> [1/3] 执行前端构建 (tools/build.sh)..."
bash tools/build.sh

# 2. 图标生成
echo "==> [2/3] 执行图标生成 (tools/gen_icons.py)..."
$PYTHON_CMD tools/gen_icons.py

# 3. fnpack 打包
echo "==> [3/3] 执行 fnpack 打包..."
if command -v fnpack >/dev/null 2>&1; then
  fnpack build
else
  echo "错误：未找到 'fnpack' 命令。请确保已安装飞牛 fnOS 开发工具。" >&2
  exit 1
fi

echo "==> 打包成功完成！"
