# Agent Guide

飞牛 fnOS 订阅管理应用 (`zephyr-fn`)：记录订阅服务、费用与到期时间，支持多货币换算、日历视图、到期推送提醒。

## 技术栈与架构

- **后端 (`app/backend/`)**: Python 3.12 + Flask 分层架构
  - `api/`: 蓝图路由，只处理请求解析与统一响应封装
  - `services/`: 业务编排与事务收敛（`commit` 控制在 service 层）
  - `repositories/`: 数据库持久化 CRUD
  - `models/`: SQLAlchemy ORM 模型
  - `domain/`: 纯领域逻辑（周期推进、状态派生、日历计算）
  - `schemas/`: 请求参数校验与清洗
  - `migrations/`: Alembic 数据库版本化迁移
- **前端 (`frontend/`)**: Vue 3 + Vite
  - 架构：`BaseLayout.vue`（公共外壳）+ `views/`（Sub Page 子页面）
  - 路由状态：轻量 Hash 路由 + `src/utils/ui.js` 单例（无 vue-router 依赖）
  - 样式规范：`src/styles/tokens.css` 统一设计令牌
- **打包集成**:
  - `cmd/`: fnOS 生命周期脚本 (`main`, `install_callback`, `upgrade_callback`)
  - `manifest`: 应用元数据与权限
  - `app/ui/config`: 统一网关入口配置 (`/app/subscription/`)

## 常用命令

```bash
# 本地热开发（后端 :3001 + 前端 :5173）
./dev.sh

# 一键本地代码质量门禁（推流前运行，完全对齐 CI）
./check.sh
# 快速检查（仅检查格式与 Lint，跳过耗时测试）
./check.sh --fast

# 激活本地 Git Hook（提交时自动 format 与 check，启动 ./dev.sh 时也会自动激活）
git config core.hooksPath .githooks

# 后端测试
pytest tests/ -v
# 或指定虚拟环境
./.venv/bin/pytest tests/ -v

# 代码检查与格式化
ruff check app/ tests/ tools/
ruff format --check app/ tests/ tools/

# 前端检查（视图规范与 Hash 路由双向绑定校验）
npm run --prefix frontend check

# 前端构建（输出至 app/www）
npm run --prefix frontend build

# 一键安全打包（严禁直接在根目录使用 fnpack build）
./package.sh
```

## 核心开发规范与约束

1. **统一 API 格式**:
   - 响应格式固定为 `{code: 0, message: "ok", data: ...}`，`code == 0` 表示成功。
2. **多用户与网关**:
   - 依赖 `X-Trim-Userid` 请求头隔离用户数据；
   - 统一网关前缀为 `/app/subscription/`，入口与重定向必须带结尾斜杠。
3. **数据库与事务**:
   - SQLite WAL 模式，金额统一以整数「分」存储；
   - 数据库事务提交权收敛在 service 层，禁止在 repository 层随意 commit；
   - 数据库表结构变更必须编写 Alembic 迁移脚本。
4. **前端开发规范**:
   - 遵循 `BaseLayout` + `Sub Page` 模式，子页面不重复写外壳与滚动容器；
   - 禁止硬编码颜色、尺寸、圆角等魔法数字，严格使用 tokens；
   - 修改页面或路由后需运行 `npm run --prefix frontend check` 校验通过。
5. **打包约束**:
   - `fnpack` 不识别 `.gitignore`，切勿在项目根目录直接打包；
   - 始终通过 `./package.sh`（执行安全暂存、排除 `.venv` 与无用文件、自动自增与校验）。
