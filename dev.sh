#!/usr/bin/env bash
# ================================================================
#  一键本地开发脚本（Flask 后端 + Vite 前端，支持热更新）
#
#  用法：
#    ./dev.sh                 # 启动开发环境（后端 :5000，前端 :5173）
#    ./dev.sh -b 5001         # 自定义后端端口
#    ./dev.sh -f 3000         # 自定义前端端口
#    ./dev.sh -d /tmp/t.db    # 自定义数据库路径
#
#  环境要求：Python 3.10+、Node.js 18+
# ================================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---- 默认配置 ----
BACKEND_PORT=5000
FRONTEND_PORT=5173
DB="./data/subscription.db"

# ---- 解析命令行参数 ----
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--backend-port)  BACKEND_PORT="$2";  shift 2 ;;
        -f|--frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
        -d|--database)      DB="$2";            shift 2 ;;
        -h|--help)
            sed -n '3,12p' "$0"; exit 0 ;;
        *)  echo "未知参数: $1（-h 查看帮助）"; exit 1 ;;
    esac
done

# ---- Python 环境 ----
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
    echo "📦 使用虚拟环境: .venv"
fi
command -v "$PYTHON_BIN" >/dev/null || { echo "❌ 需要 python3 / 项目虚拟环境" >&2; exit 1; }

# ---- 安装后端依赖（幂等） ----
if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import flask, flask_sqlalchemy, flask_migrate
PY
then
    echo "📦 安装后端 Python 依赖..."
    "$PYTHON_BIN" -m pip install -r app/backend/requirements.txt -q
fi

# ---- 安装前端依赖（幂等） ----
command -v node >/dev/null || { echo "❌ 需要 node/npm" >&2; exit 1; }
if [ ! -d frontend/node_modules ]; then
    echo "📦 安装前端依赖 (npm install)..."
    (cd frontend && npm install --silent)
fi

# ---- 初始化数据库（幂等） ----
DB_ABS="$(cd "$(dirname "$DB")" && pwd)/$(basename "$DB")"
export DATABASE_URL="sqlite:///$DB_ABS"
DB_DIR="$(dirname "$DB")"
[ -d "$DB_DIR" ] || mkdir -p "$DB_DIR"

if [ ! -f "$DB" ]; then
    echo "🗄️  初始化数据库: $DB"
    "$PYTHON_BIN" -m flask db upgrade
fi

# ---- Flask 环境变量 ----
export FLASK_APP="app.backend:create_app()"
export FLASK_DEBUG=1
export FLASK_RUN_PORT="$BACKEND_PORT"

# ---- 启动后端（后台） ----
echo ""
echo "🐍 启动后端 Flask 开发服务器 (端口 $BACKEND_PORT)..."
"$PYTHON_BIN" -m flask run --host=0.0.0.0 --port="$BACKEND_PORT" &
BACKEND_PID=$!

# ---- 退出清理 ----
cleanup() {
    echo ""
    echo "🛑 正在关闭服务..."
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    echo "👋 已退出"
}
trap cleanup EXIT INT TERM

# ---- 等待后端就绪 ----
for i in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/api/settings" >/dev/null 2>&1; then
        break
    fi
    sleep 0.3
done

# ---- 启动前端（前台） ----
echo "⚡ 启动 Vite 前端开发服务器 (端口 $FRONTEND_PORT)..."
echo ""
echo "  ┌──────────────────────────────────────────┐"
echo "  │  🌐 前端页面  http://localhost:$FRONTEND_PORT        │"
echo "  │  🔗 后端 API  http://localhost:$BACKEND_PORT/api     │"
echo "  │  🛑 Ctrl+C 停止所有服务                   │"
echo "  └──────────────────────────────────────────┘"
echo ""

(cd frontend && BACKEND_PORT="$BACKEND_PORT" npx vite --port "$FRONTEND_PORT")
