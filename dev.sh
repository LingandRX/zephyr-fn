#!/usr/bin/env bash
# ================================================================
#  一键本地开发脚本（Flask 后端 + Vite 前端，支持热更新）
#
#  用法：
#    ./dev.sh                 # 启动开发环境（后端 :3001，前端 :5173）
#    ./dev.sh -b 5001         # 自定义后端端口
#    ./dev.sh -f 3000         # 自定义前端端口
#    ./dev.sh -d /tmp/t.db    # 自定义数据库路径
#
#  环境要求：Python 3.10+、Node.js 18+
# ================================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---- 默认配置 ----
BACKEND_PORT=3001
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

# ---- 自动激活项目 Git Hook 门禁 ----
if [ -d ".githooks" ] && command -v git >/dev/null 2>&1; then
    git config core.hooksPath .githooks 2>/dev/null || true
fi

# ---- 退出清理（提前安装，保证任何退出路径都统一收尾）----
# 注意：只在确实启动过服务时才打印提示，避免 -h / 迁移预检失败时出现无关噪音。
BACKEND_PID=""
FRONTEND_PID=""
CLEANED=0
cleanup() {
    [ "$CLEANED" = 1 ] && return 0
    CLEANED=1
    # 什么都没启动（-h / 预检失败等）：不打印无关提示，也不改变退出码
    [ -n "$BACKEND_PID" ] || [ -n "$FRONTEND_PID" ] || return 0
    echo ""
    echo "🛑 正在关闭服务..."
    if [ -n "$BACKEND_PID" ]; then
        # debug 模式下 Flask 会 fork 出 reloader 子进程，先收子再收父
        pkill -P "$BACKEND_PID" 2>/dev/null || true
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        # Ctrl+C 会通过进程组同时终止前端；这里兜住 kill/SIGTERM 的场景，
        # 避免 Vite 变成孤儿进程继续占着端口。
        pkill -P "$FRONTEND_PID" 2>/dev/null || true
        kill "$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo "👋 已退出"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

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

# ---- 数据库路径与日志目录 ----
# 目录必须先创建：否则 dirname 不存在时 `cd` 求绝对路径会直接失败（set -e 会终止脚本）。
DB_DIR="$(dirname "$DB")"
[ -d "$DB_DIR" ] || mkdir -p "$DB_DIR"
DB_ABS="$(cd "$DB_DIR" && pwd)/$(basename "$DB")"
# 后端只认 DB_PATH（见 app/backend/paths.py:db_path()），且要的是文件路径而非
# SQLAlchemy URI；原先导出 DATABASE_URL 不被任何代码读取，-d 属于空转。
export DB_PATH="$DB_ABS"

LOG_DIR="data/logs"
[ -d "$LOG_DIR" ] || mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/dev-backend.log"
MIGRATE_LOG="$LOG_DIR/dev-migrate.log"

# ---- Flask 环境变量 ----
export FLASK_APP="app.backend:create_app()"
export FLASK_DEBUG=1
export FLASK_RUN_PORT="$BACKEND_PORT"

# ---- 数据库迁移预检（失败即止）----
# 后端在 create_app() 里就会自动跑 Alembic 迁移，这里提前跑一次，
# 目的是让迁移错误在启动前端之前干净地暴露出来，
# 而不是等 Vite 起来后满屏 ECONNREFUSED 127.0.0.1:3001。
echo ""
echo "🗄️  检查数据库迁移: $DB"
if ! "$PYTHON_BIN" -m flask db upgrade >"$MIGRATE_LOG" 2>&1; then
    echo ""
    echo "❌ 数据库迁移失败，已中止启动（不启动前端）。日志末尾：" >&2
    echo "------------------------------------------------------------" >&2
    tail -n 30 "$MIGRATE_LOG" >&2 || true
    echo "------------------------------------------------------------" >&2
    echo "完整日志: $MIGRATE_LOG" >&2
    echo "提示: 迁移脚本与旧库引导（bootstrap v13）内容重叠时，" >&2
    echo "      必须逐列 PRAGMA 守卫，否则会报 duplicate column name。" >&2
    exit 1
fi

# ---- 端口占用预检 ----
port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
if port_in_use "$BACKEND_PORT"; then
    echo "❌ 后端端口 $BACKEND_PORT 已被占用: lsof -nP -iTCP:$BACKEND_PORT -sTCP:LISTEN" >&2
    exit 1
fi
if port_in_use "$FRONTEND_PORT"; then
    echo "❌ 前端端口 $FRONTEND_PORT 已被占用: lsof -nP -iTCP:$FRONTEND_PORT -sTCP:LISTEN" >&2
    exit 1
fi

# ---- 启动后端（后台，输出同时打印与落盘）----
echo ""
echo "🐍 启动后端 Flask 开发服务器 (端口 $BACKEND_PORT)..."
# 用进程替换而非管道：管道会让 $! 变成 tee 的 PID，导致无法正确 kill 后端。
"$PYTHON_BIN" -m flask run --host=0.0.0.0 --port="$BACKEND_PORT" > >(tee "$BACKEND_LOG") 2>&1 &
BACKEND_PID=$!

# ---- 等待后端就绪（进程死亡立即退出，不再空等）----
READY=0
for _ in $(seq 1 40); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        break   # 后端进程已退出，无需再等
    fi
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/api/settings" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 0.3
done

if [ "$READY" != 1 ]; then
    echo "" >&2
    echo "❌ 后端未能在 http://127.0.0.1:$BACKEND_PORT 就绪，已中止（不启动前端）" >&2
    echo "后端日志末尾：" >&2
    echo "------------------------------------------------------------" >&2
    tail -n 30 "$BACKEND_LOG" >&2 || true
    echo "------------------------------------------------------------" >&2
    echo "完整日志: $BACKEND_LOG" >&2
    exit 1
fi

# ---- 启动前端（前台）----
echo ""
echo "⚡ 启动 Vite 前端开发服务器 (端口 $FRONTEND_PORT)..."
echo ""
echo "  🌐 前端页面  http://localhost:$FRONTEND_PORT"
echo "  🔗 后端 API  http://localhost:$BACKEND_PORT/api"
echo "  📄 后端日志  $BACKEND_LOG"
echo "  🛑 Ctrl+C 停止所有服务"
echo ""

if [ -x "frontend/node_modules/.bin/vite" ]; then
    (cd frontend && BACKEND_PORT="$BACKEND_PORT" exec ./node_modules/.bin/vite --port "$FRONTEND_PORT") &
else
    (cd frontend && BACKEND_PORT="$BACKEND_PORT" exec npx vite --port "$FRONTEND_PORT") &
fi
FRONTEND_PID=$!
wait "$FRONTEND_PID"
