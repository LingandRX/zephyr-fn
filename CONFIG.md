# 配置总览（CONFIG.md）

本项目整套配置的集中说明。所有内容均基于代码原文整理，改动后请同步更新本文档。

---

## 一、总体架构

```
浏览器 ──5173────▶ Vite (frontend) ──proxy /api──▶ Python 后端 (Flask, 8000) ─▶ SQLite
        (dev 前端)                   └─ 生产/真机: 走网关前缀 /app/subscription ─▶ 后端
```

- 前端 dev（Vite）默认 **5173**
- 后端 API（Flask）默认 **8000**
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
| 备份 | `SHARE_DIR` > `TRIM_DATA_SHARE_PATHS` | `<data_dir>/backups` |
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
| `--share DIR` | 备份目录 |
| `--init-db` | 仅初始化数据库后退出 |
| `--reminder-days N` | 安装向导提醒天数（配合 `--init-db`） |

启动时自动完成（幂等）：`bootstrap_legacy_database()` → Alembic `upgrade()` → `seed_default_settings()`。

---

## 四、前端配置（`frontend/vite.config.mjs`）

| 项 | 值 |
|---|---|
| `server.port` | **5173** |
| `server.strictPort` | **true**（端口被占直接报错，不再静默跳到 5174） |
| proxy `/api` | → `http://127.0.0.1:${BACKEND_PORT \|\| 8000}` |
| `base` | dev=`/`；build=`/app/subscription/` |
| `GATEWAY_PREFIX` | `/app/subscription`（须与后端 `gateway_prefix()` 一致） |

前端 API 基准（`src/services/api.js`）：

```js
API_BASE = import.meta.env.DEV ? "/api" : "/app/subscription/api"
```

- dev：页面在根路径，`/api` 走 Vite proxy → 后端 8000
- prod：页面在 `/app/subscription/`，`/api` 走网关前缀，由后端剥离前缀

---

## 五、一键开发脚本（`dev.sh`）端口编排

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `FRONTEND` | `vue` | `vanilla`=原生版，`build`=打包版 |
| `BUILD` | `0` | `1`=构建 `frontend/dist` 后由后端服务 |
| `PORT` | `8000` | 生产/静态预览端口 |
| `BACKEND_PORT` | `8000` | **dev 模式下后端 API 端口**（与 `server.py` 默认一致） |
| `DB` | `./data/subscription.db` | 数据库 |
| `SHARE` | `./data/backups` | 备份目录 |

`dev.sh` 实际起两个进程：

```
后端: python server.py --http 8000 --db ... --www app/www --share ...
前端: (cd frontend && BACKEND_PORT=8000 npm run dev)   # Vite on 5173
```

---

## 六、常见排查

- **前端跑到 5174**：`strictPort` 已改为 `true`，此后 Vite 不会静默换端口；若仍出现说明有多份 vite 进程占 5173。
- **`/api` 请求失败（ECONNREFUSED）**：检查后端是否真的在 8000 监听（`netstat -ano | findstr 8000`）。
- **数据库迁移报 `duplicate column`**：`alembic_version` 与表结构脱节，属半迁移中间态；全新环境不受影响。