#!/usr/bin/env bash
# 一键本地预览
#
#   ./dev.sh                  # Vue 版（构建 dist 后由后端服务，与线上行为一致）
#   FRONTEND=vanilla ./dev.sh # 原生版（app/www，零构建秒开）
#   PORT=9000 ./dev.sh        # 自定义端口
#   DB=/tmp/t.db ./dev.sh     # 自定义数据库（不污染仓库 data/）
set -euo pipefail
cd "$(dirname "$0")"

FRONTEND="${FRONTEND:-vue}"
PORT="${PORT:-8000}"
DB="${DB:-./data/subscription.db}"
SHARE="${SHARE:-./data/backups}"

command -v python3 >/dev/null || { echo "错误：需要 python3" >&2; exit 1; }

# 初始化数据库（幂等，--init-db 已内置建表迁移）
if [ ! -f "$DB" ]; then
  echo "==> 初始化数据库: $DB"
  python3 app/backend/server.py --init-db --db "$DB" --share "$SHARE"
fi

WWW="app/www"
if [ "$FRONTEND" = "vue" ]; then
  command -v node >/dev/null || { echo "错误：Vue 版需要 node/npm" >&2; exit 1; }
  if [ ! -d frontend/node_modules ]; then
    echo "==> 安装前端依赖 (npm install)"
    (cd frontend && npm install)
  fi
  echo "==> 构建 Vue 前端 (frontend/dist)"
  (cd frontend && npm run build >/dev/null)
  WWW="frontend/dist"
fi

echo "==> 启动服务: http://127.0.0.1:${PORT}/app/subscription/"
echo "    (FRONTEND=vanilla ./dev.sh 可预览原生版；Ctrl+C 退出)"
exec python3 app/backend/server.py --http "$PORT" --db "$DB" --www "$WWW" --share "$SHARE"