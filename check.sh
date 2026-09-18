#!/usr/bin/env bash
# ================================================================
#  全量本地代码质量门禁脚本 (Local CI Gate)
#  一键运行与 GitHub Actions 相同的全部检查，确保推流 100% 绿标。
#
#  用法：
#    ./check.sh          # 运行全量检查（后端 Lint/Format/Test + 前端 Check/Lint/Build）
#    ./check.sh --fast   # 仅运行代码格式与 Lint（跳过耗时较长的 Test 和 Build）
# ================================================================
set -euo pipefail
cd "$(dirname "$0")"

FAST_MODE=0
if [[ "${1:-}" == "--fast" ]]; then
    FAST_MODE=1
fi

echo "================================================================"
echo "🚀 开始执行本地代码质量门禁检查 (Local CI)"
echo "================================================================"

# ---- Python & Ruff 环境探测 ----
RUFF_CMD=""
if command -v ruff >/dev/null 2>&1; then
    RUFF_CMD="ruff"
elif [ -x ".venv/bin/ruff" ]; then
    RUFF_CMD=".venv/bin/ruff"
elif command -v uvx >/dev/null 2>&1; then
    RUFF_CMD="uvx ruff"
elif command -v uv >/dev/null 2>&1; then
    RUFF_CMD="uv run ruff"
elif python3 -m ruff --version >/dev/null 2>&1; then
    RUFF_CMD="python3 -m ruff"
else
    echo "❌ 未找到 ruff，请先安装或激活虚拟环境 (.venv)。" >&2
    exit 1
fi

# ---- 1. 后端代码规范检查 (Ruff check) ----
echo ""
echo "🔍 [1/5] 后端代码规范检查 (ruff check)..."
$RUFF_CMD check app/ tests/ tools/
echo "✅ 后端代码规范检查通过！"

# ---- 2. 后端代码格式检查 (Ruff format) ----
echo ""
echo "🎨 [2/5] 后端代码格式检查 (ruff format --check)..."
$RUFF_CMD format --check app/ tests/ tools/
echo "✅ 后端代码格式检查通过！"

# ---- 3. 后端单元与冒烟测试 (Pytest) ----
if [ "$FAST_MODE" -eq 0 ]; then
    echo ""
    echo "🧪 [3/5] 后端测试套件 (pytest)..."
    PYTEST_CMD=""
    if [ -x ".venv/bin/pytest" ]; then
        PYTEST_CMD=".venv/bin/pytest"
    elif command -v uv >/dev/null 2>&1; then
        PYTEST_CMD="uv run --extra dev pytest"
    elif command -v pytest >/dev/null 2>&1; then
        PYTEST_CMD="pytest"
    elif python3 -m pytest --version >/dev/null 2>&1; then
        PYTEST_CMD="python3 -m pytest"
    fi

    if [ -n "$PYTEST_CMD" ]; then
        $PYTEST_CMD tests/ -v
        echo "✅ 后端测试套件全部通过！"
    else
        echo "⚠️  未检测到 pytest，跳过后端单元测试。"
    fi
else
    echo ""
    echo "⏩ [3/5] 跳过后端单元测试 (--fast)"
fi

# ---- 4. 前端规范与双向绑定检查 ----
echo ""
echo "🌐 [4/5] 前端规范与路由双向绑定校验..."
if command -v npm >/dev/null 2>&1; then
    if [ ! -d "frontend/node_modules" ]; then
        echo "📦 安装前端依赖..."
        (cd frontend && npm install --silent)
    fi
    npm run --prefix frontend check
    echo "✅ 前端规范检查通过！"

    echo ""
    echo "🧹 [5/5] 前端 ESLint 检查..."
    npm run --prefix frontend lint
    echo "✅ 前端 ESLint 检查通过！"

    if [ "$FAST_MODE" -eq 0 ]; then
        echo ""
        echo "🏗️  [可选] 前端构建测试 (vite build)..."
        npm run --prefix frontend build
        echo "✅ 前端构建测试通过！"
    fi
else
    echo "⚠️  未找到 node/npm，跳过前端检查。"
fi

echo ""
echo "================================================================"
echo "🎉 恭喜！全部门禁检查通过，代码符合规范，可放心推流 (git push)！"
echo "================================================================"
