#!/usr/bin/env bash
# 一键打包流程：自增版本号 -> 构建前端 -> 生成图标 -> 执行 fnpack 打包
#
# 流程：
#   1. 自动自增 manifest 中的 version（例如 0.1.1 -> 0.1.2，支持 NO_BUMP=1 跳过）
#   2. ./build.sh                # 前端构建 & 资源同步 & 清理缓存
#   3. python3 tools/gen_icons.py # 图标生成
#   4. fnpack build              # 最终打包
#
set -euo pipefail
cd "$(dirname "$0")"

# 自动检测 Python 命令 (Windows 通常是 python, Linux/macOS 通常是 python3)
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "错误：未找到 Python，请先安装 Python。" >&2
  exit 1
fi

# 1. 自动递增 manifest 中的版本号
if [ "${NO_BUMP:-0}" != "1" ]; then
  echo "==> [1/4] 自动自增 manifest 版本号..."
  $PYTHON_CMD -c '
import re

manifest_file = "manifest"
try:
    with open(manifest_file, "r", encoding="utf-8") as f:
        content = f.read()

    def bump(m):
        old_ver = m.group(1).strip()
        parts = old_ver.split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
        except ValueError:
            parts.append("1")
        new_ver = ".".join(parts)
        print(f"    manifest 版本号: {old_ver} -> {new_ver}")
        return f"version={new_ver}"

    new_content, count = re.subn(r"^version=(.+)$", bump, content, count=1, flags=re.MULTILINE)
    if count > 0:
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(new_content)
    else:
        print("    警告：manifest 中未找到 version= 字段，跳过自增")
except Exception as e:
    print(f"    警告：自增版本号失败 ({e})，继续打包")
'
else
  echo "==> [1/4] 跳过版本自增 (NO_BUMP=1)"
fi

# 2. 前端构建
echo "==> [2/4] 执行前端构建 (build.sh)..."
bash ./build.sh

# 3. 图标生成
echo "==> [3/4] 执行图标生成 (tools/gen_icons.py)..."
$PYTHON_CMD tools/gen_icons.py

# 4. fnpack 打包
echo "==> [4/4] 执行 fnpack 打包..."

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
  "./$FNPACK_BIN" build
elif command -v fnpack >/dev/null 2>&1; then
  echo "    未在 tools/package 找到对应平台的预置文件（${OS_NAME}-${ARCH_NAME}），使用系统 fnpack"
  fnpack build
else
  echo "错误：未在 tools/package 找到适用于 ${OS_NAME}-${ARCH_NAME} 的打包工具，系统 PATH 中也未找到 'fnpack' 命令。" >&2
  exit 1
fi

echo "==> 打包成功完成！"
