# 后端规范化重构说明（Flask 工厂模式 + 蓝图 + 四层架构）

> 本文档记录 `app/backend/` 从单体 Flask 脚本到规范化分层架构的完整重构：
> 目标结构、关键对比、迁移注意事项。

## 一、目标目录结构

```text
app/backend/
├── __init__.py              # 包元信息（分层说明）
├── app.py                   # ★ 应用工厂 create_app()：配置装配、扩展、中间件、错误处理、蓝图、数据库迁移
├── server.py                # 进程入口（CLI 参数、日志、UDS/TCP 启动）——签名与旧版一致，cmd/main 无需改动
├── config.py                # ★ 环境隔离配置（Base/Development/Production/Testing）+ 路径解析 + override()
├── extensions.py            # ★ 扩展单例：db = SQLAlchemy() / migrate = Migrate()（杜绝循环引用）
├── requirements.txt         # ★ 运行时依赖清单
├── core/                    # 领域逻辑与公共基础设施
│   ├── domain.py            # 纯领域逻辑（周期推进、状态派生、校验）——未改动
│   ├── exceptions.py        # ★ ApiError 异常体系（Validation/NotFound/Conflict/Forbidden/...）
│   ├── response.py          # ★ 统一响应 {code, message, data}
│   └── middleware.py        # ★ 身份解析、管理员校验、默认分类补种、网关前缀剥离（WSGI 中间件）
├── models/                  # ★ ORM 数据实体（Flask-SQLAlchemy）
│   ├── subscription.py      #   订阅（列与旧 schema 一一对应）
│   ├── category.py          #   分类（含 NOCASE 唯一索引）
│   ├── app_settings.py      #   全局设置（单行约束）
│   ├── notification_log.py  #   通知日志（幂等唯一索引）
│   ├── email_log.py         #   邮件日志
│   └── seeded_user.py       #   默认分类补种标记
├── schemas/                 # ★ 参数校验与序列化（手写轻量 Schema，复用 core/domain 校验）
│   ├── base.py
│   ├── subscription.py      #   创建/更新/导入三种场景
│   ├── category.py          #   名称归一化（NFC/全角/非法字符）
│   └── settings.py          #   密钥占位符过滤、类型转换、{field}_clear
├── storage/                 # 数据持久化
│   ├── repositories.py      # ★ SQLAlchemy 仓储（查询/写入/幂等领取/备份副本）
│   └── bootstrap.py         # ★ 存量旧库就地升级引导（v1→v11 幂等）+ 默认设置补种
├── services/                # 业务层
│   ├── subscriptions.py     # ★ 订阅业务（Schema 校验 → 周期推导 → 仓储编排）
│   ├── categories.py        # ★ 分类业务（去重/上限校验、默认分类补种）
│   ├── settings.py          # ★ 设置业务（密钥脱敏）
│   ├── statistics.py        # 统计与日历（算法未动，仅改数据源）
│   ├── notifications.py     # 通知业务（幂等领取改为仓储原子 UPSERT）
│   ├── backup.py            # 备份导入导出（事务改为 SQLAlchemy 会话）
│   └── scheduler.py         # 定时任务（绑定 app 实例 + 每轮 app_context）
├── api/                     # ★ 路由层（Blueprint，仅做请求解析与响应封装）
│   ├── subscriptions.py     #   /api/subscriptions ...
│   ├── categories.py        #   /api/categories ...
│   ├── settings.py          #   /api/settings ...
│   ├── statistics.py        #   /api/statistics + /api/calendar
│   ├── backup.py            #   /api/backup + 导入导出 + 文件管理
│   ├── notifications.py     #   /api/notifications/... + 渠道测试
│   ├── logs.py              #   /api/logs/tail
│   └── web.py               #   静态文件 + SPA fallback
├── utils/                   # 基础设施工具
│   ├── file_utils.py        # 未改动
│   └── channels/            # email.py 已去除存储层依赖（参数全量传入）
└── migrations/              # ★ Flask-Migrate / Alembic
    ├── alembic.ini
    ├── env.py               #   注意 disable_existing_loggers=False（见迁移注意事项 #5）
    ├── script.py.mako
    └── versions/
        └── 0001_baseline.py # 基线迁移（幂等 DDL，与旧 v11 schema 完全一致）
```

## 二、关键重构点对比

| 维度 | 重构前 | 重构后 |
| --- | --- | --- |
| 应用装配 | `server.py` 860 行单体（路由/中间件/错误处理/工厂全在一个函数里） | `app.py` 工厂 + `api/` 9 个蓝图 + `core/middleware.py` 中间件 + 全局错误处理器 |
| 循环引用 | 模块级 `app`、`db._conn` 全局连接 | 扩展单例 `extensions.py`，工厂内 `init_app`，无全局实例 |
| 数据层 | 裸 sqlite3 + 单连接线程锁 + 手写迁移（`db_version` v1→v11） | Flask-SQLAlchemy ORM（`models/`）+ 仓储（`storage/repositories.py`）+ Flask-Migrate（`migrations/`） |
| 会话生命周期 | 全局 `_conn` + RLock，手动 `_commit()` | 绑定应用/请求上下文，路由请求自动管理；定时线程每轮 `with app.app_context()` |
| 校验与业务 | 全部混在 `storage/db.py`（1300+ 行） | 参数校验 → `schemas/`（复用 `core/domain.py` 严格校验）；业务编排 → `services/`；持久化 → `storage/repositories.py` |
| 响应结构 | 裸 JSON + `{"error": msg}` 错误体 | 统一 `{code, message, data}`（code==0 成功）；前端 `api.js` 统一解包 |
| 错误处理 | 分散在路由 try/except + 若干 errorhandler | `core/exceptions.py` 异常体系 + 全局 Error Handler 统一转译 |
| 配置 | 模块级函数 + env 直读 | 环境隔离配置类（Development/Production/Testing），敏感项走环境变量；路径辅助函数保留 |
| 通知幂等 | 手写 BEGIN IMMEDIATE + UPSERT + 进程内存兜底 | 仓储单语句原子 UPSERT（语义等价：sent 终态 / pending TTL / failed 可重领） |
| 网关前缀 | before_request 里改 `request.environ`（对路由不生效，前缀路径 404） | WSGI 中间件在 Flask 创建 Request 前改写 PATH_INFO/SCRIPT_NAME（修复） |

## 三、迁移注意事项

1. **依赖安装（设备端必须补齐）**：新增 `Flask-SQLAlchemy` 与 `Flask-Migrate`（见 `app/backend/requirements.txt` / `pyproject.toml`）。
   已在 `cmd/install_callback` 中增加幂等安装步骤：
   `python3 -m pip install "Flask-SQLAlchemy>=3.1,<4.0" "Flask-Migrate>=4.0,<5.0"`
   （flask 随 fnOS `install_dep_apps=python312` 运行时提供，不重复安装；pip 失败会使安装流程报错退出，
   避免装上无法启动的应用）。

2. **存量数据库零风险升级**：启动时自动执行「旧库就地升级（`storage/bootstrap.py`，v1→v11 幂等、含自修复）→
   Alembic 基线（幂等 DDL）→ 补种默认设置」。已验证：v11 旧库升级后数据完整、`alembic_version` 正确 stamp。
   全新库直接走 Alembic。**不要删除 `db_version` 表**——它是旧库检测标记（见 `bootstrap.has_legacy_marker`）。

3. **开发期生成新迁移**：`cd app/backend && flask db migrate -m "描述"`（FLASK_APP 指向 `backend.app:create_app`），
   然后 `flask db upgrade`；生产启动时工厂自动 `upgrade()`，无需手动执行。

4. **接口响应结构变更**：所有 JSON 接口从裸数据改为 `{code, message, data}` 信封。
   `frontend/src/services/api.js` 已同步解包（code==0 返回 data，否则抛 message），视图组件零改动。
   下载类端点（导出 JSON/CSV、备份文件）保持原始文件响应，不走信封。

5. **日志注意**：`migrations/env.py` 的 `fileConfig(..., disable_existing_loggers=False)` 是刻意为之——
   Alembic 日志配置默认会禁用未在 ini 中声明的日志器，导致 `server.py` 的 app.log 静默失效。

6. **顺带修复的问题**：
   - 网关前缀剥离改为 WSGI 中间件（此前 before_request 改 environ 对路由无效，前缀路径 404）；
   - 全量备份的 SQLite 副本 fsync 在 Windows 上对只读句柄失败（`scheduler._atomic_copy_database` 改为 r+b 打开）；
   - 本地 TCP 模式的 `allow_headerless_local_identity` 显式参数现在优先于配置类。

7. **测试**：`tests/` 已适配新架构（`tests/helpers.py` 提供按类隔离的临时库 + 应用上下文）。
   运行方式不变：`python3 -m unittest discover -s tests -v`。

8. **启动方式不变**：`cmd/main`、`dev.sh`、`cmd/install_callback` 仍调用 `python3 server.py ...`，
   CLI 参数（--uds/--http/--db/--www/--share/--init-db/--reminder-days）与旧版完全一致。

9. **路径一律使用绝对路径**：`--db ./data/...`、`--www app/www` 这类相对路径会引发隐蔽故障——
   Flask 的 `send_file` 按 `app.root_path`（backend 包目录）拼接相对路径（静态资源 500/404），
   而 `mkdir` 按进程 CWD 解析（看似正常）。`config.py` 的路径辅助函数已统一
   `.resolve()` 绝对化；Flask-SQLAlchemy 3.x 也会把相对 sqlite 路径拼接到
   `app.instance_path`，工厂内已强制绝对 URI 并先行创建父目录。
