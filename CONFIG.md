# 配置总览（CONFIG.md）

本项目整套配置的集中说明。所有内容均基于代码原文整理，改动后请同步更新本文档。

---

## 一、总体架构

```
浏览器 ──5173────▶ Vite (frontend) ──proxy /api──▶ Python 后端 (Flask, 3001) ─▶ SQLite
        (dev 前端)                   └─ 生产/真机: 走网关前缀 /app/subscription ─▶ 后端
```

- 前端 dev（Vite）默认 **5173**
- **后端端口分两套**：dev 走一键脚本（`dev.sh` / `dev.ps1`）默认 **3001**（见第五节）；
  生产入口 `server.py --http` 默认 **8000**（见第三节），UDS 模式下不占端口
- 生产/真机：页面走网关前缀 `/app/subscription`，由后端直接服务

---

## 二、后端配置（`app/backend/config.py`）

### 2.1 环境隔离（Flask 配置类）

| 环境 | 类 | 关键差异 |
|---|---|---|
| `development` | `DevelopmentConfig` | `DEBUG=True`、`ALLOW_HEADERLESS_LOCAL=True`（允许无身份头，回退 local 管理员） |
| `production` | `ProductionConfig` | 同 `BaseConfig`，不开放调试 |
| `testing` | `TestingConfig` | `TESTING=True`、DB 用 `sqlite:///:memory:` |

环境选择顺序：`SUBSCRIPTION_ENV` → 否则若存在 `TRIM_APPDEST` 判为 `production` → 否则 `development`。

### 2.2 安全与请求边界

| 配置 | 值 |
|---|---|
| `SECRET_KEY` | 环境变量 `SECRET_KEY` 注入，缺省 `subscription-dev-insecure-key` |
| `MAX_CONTENT_LENGTH` | 5 MB |
| `SQLALCHEMY_TRACK_MODIFICATIONS` | False |
| `SQLALCHEMY_ENGINE_OPTIONS` | `check_same_thread=False, timeout=5`（SQLite 多线程 WAL） |

### 2.3 路径解析

优先级：`override()`（`--db` 等 CLI 参数、`server.py` 注入） > 环境变量 > 默认值。

| 路径 | 环境变量 | 默认 |
|---|---|---|
| 应用根 | `TRIM_APPDEST` | 仓库根 `.../zephyr-fn` |
| 前端静态 | `WWW_DIR` | `<app_root>/www` |
| 数据目录 | `TRIM_PKGVAR` | `app/backend/../../data`（即 `zephyr-fn/data`） |
| 数据库 | `DB_PATH` | `<data_dir>/subscription.db` |
| 日志 | — | `<data_dir>/logs` |
| 网关前缀 | `GATEWAY_PREFIX` | `/app/subscription` |

其他：`TRIM_APPVER`（版本）、`TRIM_SYS_ARCH`（架构）、`wizard_reminder_days`（安装向导提醒天数）。

---

## 三、后端入口 CLI（`app/backend/server.py`）

| 参数 | 说明 |
|---|---|
| `--http PORT` | TCP 监听端口，缺省 `8000` |
| `--uds PATH` | Unix socket（网关模式，优先级高于 http） |
| `--db PATH` | 覆盖数据库路径 |
| `--www DIR` | 前端目录 |
| `--init-db` | 仅初始化数据库后退出 |
| `--reminder-days N` | 安装向导提醒天数（配合 `--init-db`） |

启动时自动完成（幂等）：`bootstrap_legacy_database()` → Alembic `upgrade()` → `seed_default_settings()`。

---

## 四、前端配置（`frontend/vite.config.mjs`）

配置以 `defineConfig(({ command }) => ...)` 按 `command`（`serve` / `build`）分支。

| 项 | dev（`serve`） | build | 说明 |
|---|---|---|---|
| `base` | `/` | `/app/subscription/` | dev 不能带前缀：Vite 6 下带前缀的 base 会被 proxy 吞掉，Vite 自身的模块请求会被转发给后端 |
| `server.port` | `5173` | — | 可被 `vite --port` 覆盖（`dev.sh` / `dev.ps1` 即以此传参） |
| `server.strictPort` | `true` | — | 端口被占直接报错，不静默跳到 5174 |
| `build.outDir` | — | `dist`（`emptyOutDir: true`） | |

proxy 只代理 `/api`：

```js
proxy: {
  "/api": {
    target: `http://127.0.0.1:${process.env.BACKEND_PORT || 5000}`,
    changeOrigin: true,
  },
}
```

`BACKEND_PORT` 在前端进程启动时读取，由 `dev.sh` / `dev.ps1` 注入（见第五节）。
**未注入时回退 5000**，与两个脚本默认的 3001 对不上，表现为前端满屏
`ECONNREFUSED 127.0.0.1:5000` —— 单独跑 `npm run dev` 时必须自己带上：

```
bash      : BACKEND_PORT=3001 npm run dev
PowerShell: $env:BACKEND_PORT=3001; npm run dev
```

`GATEWAY_PREFIX`（脚本常量）为 `/app/subscription`，须与后端
`paths.gateway_prefix()` 及 `GATEWAY_PREFIX` 环境变量一致。

前端 API 基准（`src/services/api.js:11`）：

```js
API_BASE = import.meta.env.DEV ? "/api" : "/app/subscription/api"
```

- dev：页面在根路径，`/api` 走 Vite proxy → 后端（`BACKEND_PORT`，脚本默认 3001）
- prod：页面在 `/app/subscription/`，`/api` 走网关前缀，由后端中间件剥离前缀
  （`app/backend/http/middleware.py`）

---

## 五、一键开发脚本（`dev.sh` / `dev.ps1`）

两个脚本提供等价的一键启动：`dev.sh`（bash，Linux/macOS）、`dev.ps1`（PowerShell，Windows）。
都是「先起后端 → 探活通过 → 再起前端」，差异见下方「启动流程」第 3 点与「进程模型与清理」。

| dev.sh | dev.ps1 | 默认 | 说明 |
|---|---|---|---|
| `-b, --backend-port` | `-BackendPort` | `3001` | 后端 API 端口 |
| `-f, --frontend-port` | `-FrontendPort` | `5173` | Vite 端口 |
| `-d, --database` | `-Database` | `./data/subscription.db` | SQLite 文件路径 |
| `-h, --help` | — | — | 用法说明 |

启动流程（两端一致）：

1. **依赖自检**：缺 `flask` / `flask_sqlalchemy` / `flask_migrate` 或 `frontend/node_modules` 时自动安装（幂等）
2. **注入环境变量**：`DB_PATH`（绝对路径）、`FLASK_APP=app.backend:create_app()`、`FLASK_DEBUG=1`、`FLASK_RUN_PORT`、`BACKEND_PORT`
3. **数据库迁移**：`dev.sh` 每次都跑 `flask db upgrade` 预检，失败即中止（不启动前端）；`dev.ps1` 仅在库文件缺失时跑一次，其余交给应用工厂启动时的自动迁移
4. **端口占用预检**：后端 / 前端端口被占即中止，并给出占用进程信息（`dev.ps1` 直接给出 PID 与释放命令）
5. **启动后端**：`flask run --host=0.0.0.0 --port <后端端口>`
6. **探活**：轮询 `http://127.0.0.1:<后端端口>/api/settings`（40 次 × 0.3s），后端进程提前退出立即中止；**探活失败不启动前端**，打印后端日志尾部后 `exit 1`
7. **启动前端**：`vite --port <前端端口>`，同时把 `BACKEND_PORT` 传给 Vite 供 proxy 使用（见第四节）

进程模型与清理：

| | dev.sh | dev.ps1 |
|---|---|---|
| 后端 | 后台进程 `> >(tee "$log") 2>&1 &` | `Start-Process`（stdout/stderr 落盘） |
| 前端 | 后台进程 + `wait` | 前台 `npx vite` |
| 日志 | `data/logs/dev-backend.log`、`data/logs/dev-migrate.log` | `data/logs/dev-backend.log`、`data/logs/dev-backend.err.log` |
| 清理 | `trap EXIT`：先 `pkill -P` 收子进程，再 `kill` 父进程 | `finally`：`taskkill /PID <pid> /T /F` 整棵树 |

`FLASK_DEBUG=1` 下 werkzeug reloader 会派生真正监听端口的子进程，两个脚本都按
**进程树**清理，避免孤儿进程继续占住后端端口。

---

## 六、常见排查

- **前端跑到 5174**：`strictPort` 已改为 `true`，此后 Vite 不会静默换端口；若仍出现说明有多份 vite 进程占 5173。
- **`/api` 请求失败（ECONNREFUSED）**：先核对端口——dev 走脚本应为 **3001**，生产 `server.py` 默认 **8000**；再确认后端确实在该端口监听（`netstat -ano | findstr 3001`）。
- **数据库迁移报 `duplicate column`**：`alembic_version` 与表结构脱节，属半迁移中间态；全新环境不受影响。