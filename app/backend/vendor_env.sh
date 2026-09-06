# 由 cmd 脚本 source：为飞牛 python312 设置 PYTHON_BIN / PYTHONPATH（vendor 内 Linux 轮子）
# 用法: . "${TRIM_APPDEST}/backend/vendor_env.sh"

: "${TRIM_APPDEST:?TRIM_APPDEST 为空}"

# 优先探测飞牛 python312 应用，其次系统已安装的 python3
_find_python() {
  if [ -n "${PYTHON_BIN:-}" ] && [ -x "$PYTHON_BIN" ]; then
    echo "$PYTHON_BIN"
    return
  fi
  for candidate in \
    "/var/apps/python312/target/bin/python3" \
    "/var/apps/python312/bin/python3" \
    "/usr/local/bin/python3" \
    "/usr/bin/python3"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return
    fi
  done
  command -v python3 2>/dev/null || echo "/var/apps/python312/target/bin/python3"
}

PYTHON_BIN="$(_find_python)"
_machine="${TRIM_SYS_ARCH:-$(uname -m 2>/dev/null || echo x86_64)}"
case "${_machine}" in
  x86_64|amd64|x64|x86)
    _vendor_tag="manylinux2014_x86_64"
    ;;
  aarch64|arm64|arm)
    _vendor_tag="manylinux2014_aarch64"
    ;;
  *)
    _vendor_tag="manylinux2014_x86_64"
    ;;
esac

_vendor="${TRIM_APPDEST}/backend/vendor/${_vendor_tag}"
if [ ! -d "${_vendor}/flask" ]; then
  echo "错误: 预置依赖不存在: ${_vendor} (arch=${_machine})"
  echo "请使用仓库 package.sh / package.ps1 重新打包（会执行 tools/vendor_deps.py）"
  ls -la "${TRIM_APPDEST}/backend/vendor" 2>/dev/null || true
  exit 1
fi

export PYTHON_BIN
export PYTHONPATH="${_vendor}${PYTHONPATH:+:${PYTHONPATH}}"
echo "PYTHON_BIN=${PYTHON_BIN}"
echo "PYTHONPATH=${PYTHONPATH}"
