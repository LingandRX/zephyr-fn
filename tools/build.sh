#!/usr/bin/env bash
# 打包前构建：将 Vue 前端产物同步到 app/www（fnOS 打包器直接收录 app/www）
#
#   ./tools/build.sh          # 完整流程：npm install(如缺) → vite build → 同步 app/www
#   之后运行 fnpack build 即可产出 fpk。
#
# 注意：本脚本会覆盖 app/www（vanilla 原生版保留在 git 历史中，
# 如需恢复执行：git checkout -- app/www）。
set -euo pipefail
cd "$(dirname "$0")/.."

command -v node >/dev/null || { echo "错误：打包前端需要 node/npm" >&2; exit 1; }
if [ ! -d frontend/node_modules ]; then
  echo "==> 安装前端依赖 (npm install)"
  (cd frontend && npm install)
fi

echo "==> 构建 Vue 前端 (frontend/dist)"
(cd frontend && npx vite build)

echo "==> 同步 dist → app/www"
rm -rf app/www
mkdir -p app/www
cp -R frontend/dist/. app/www/
echo "    app/www 内容:"
ls app/www

# 清理 Python 缓存，避免 fnpack 把 __pycache__/*.pyc 打进包
echo "==> 清理 Python 缓存 (__pycache__)"
find app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo
echo "==> 完成。下一步运行: fnpack build"
echo "    (本地预览: ./dev.sh；打包 CLI 见 https://developer.fnnas.com/docs/cli/fnpack/)"