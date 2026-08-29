#!/usr/bin/env bash
# 一键本地开发 / 预览
#
#   ./dev.sh                  # Vue 热更新开发模式（Vite dev :5173 + 后端 API :5001，支持 HMR）
#   BUILD=1 ./dev.sh          # Vue 静态构建预览（构建 dist 后由后端 :8000 服务，与线上行为一致）
#   FRONTEND=vanilla ./dev.sh # 原生版（app/www，零构建秒开，后端 :8000）
#   PORT=9000 ./dev.sh        # 自定义端口（静态预览模式）
#   DB=/tmp/t.db ./dev.sh     # 自定义数据库（不污染仓库 data/）
set -euo pipefail
cd "$(dirname "$0")"

FRONTEND="${FRONTEND:-vue}"
BUILD="${BUILD:-0}"
PORT="${PORT:-8000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
DB="${DB:-./data/subscription.db}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x "$PWD/.venv/bin/python" ]; then
  PYTHON_BIN="$PWD/.venv/bin/python"
fi

command -v "$PYTHON_BIN" >/dev/null || { echo "错误：需要 python3 / 项目虚拟环境" >&2; exit 1; }

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import flask, flask_sqlalchemy, flask_migrate
print('ok')
PY
then
  echo "==> 安装后端 Python 依赖..."
  "$PYTHON_BIN" -m pip install -r app/backend/requirements.txt
fi

# 初始化数据库（幂等，--init-db 已内置建表迁移）
if [ ! -f "$DB" ]; then
  echo "==> 初始化数据库: $DB"
  "$PYTHON_BIN" app/backend/server.py --init-db --db "$DB"
fi

if [ "$FRONTEND" = "vanilla" ]; then
  echo "==> 启动原生版服务: http://127.0.0.1:${PORT}/app/subscription/"
  echo "    (Ctrl+C 退出)"
  exec "$PYTHON_BIN" app/backend/server.py --http "$PORT" --db "$DB" --www "app/www"
fi

command -v node >/dev/null || { echo "错误：Vue 版需要 node/npm" >&2; exit 1; }
if [ ! -d frontend/node_modules ]; then
  echo "==> 安装前端依赖 (npm install)"
  (cd frontend && npm install)
fi

# 生产构建预览模式
if [ "$BUILD" = "1" ] || [ "$FRONTEND" = "build" ]; then
  echo "==> 构建 Vue 前端 (frontend/dist)"
  (cd frontend && npm run build)
  echo "==> 启动生产预览服务: http://127.0.0.1:${PORT}/app/subscription/"
  echo "    (Ctrl+C 退出)"
  exec "$PYTHON_BIN" app/backend/server.py --http "$PORT" --db "$DB" --www "frontend/dist"
fi

# 默认：Vue 热更新开发模式（Vite dev + 后端 API）
echo "==> 启动后端 API 服务 (端口 $BACKEND_PORT)..."
"$PYTHON_BIN" app/backend/server.py --http "$BACKEND_PORT" --db "$DB" --www "app/www" &
BACKEND_PID=$!

cleanup() {
  echo ""
  echo "==> 正在关闭后端服务 (PID: $BACKEND_PID)..."
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> 启动 Vite 前端开发服务器 (支持 HMR 热更新)..."
echo "    前端页面: http://localhost:5173/"
echo "    后端 API: http://127.0.0.1:${BACKEND_PORT}/api"
echo "    (BUILD=1 ./dev.sh 可进行打包预览；FRONTEND=vanilla ./dev.sh 可预览原生版；Ctrl+C 退出)"

(cd frontend && BACKEND_PORT="$BACKEND_PORT" npm run dev)