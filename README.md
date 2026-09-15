# 订阅管理 (subscription)

飞牛 fnOS 订阅管理应用：记录订阅服务、费用与到期时间，支持多货币统计、日历视图与到期提醒。

## 官方开发文档

<https://github.com/ckcoding/fnnas-docs>

## 功能

- 订阅管理：新增 / 编辑 / 删除 / 续费（推进到下一期）
- 分类管理：自定义分类（名称 + emoji 图标）
- 多货币：CNY / USD / HKD，自定义汇率换算（默认 7.2 / 0.92）
- 周期：月付 / 季付 / 年付 / 一次性 / 自定义（天 / 周 / 月 / 年）
- 续费策略：自动续费 / 手动续费 / 到期停止 / 到期停止并结束
- 状态派生：活跃 / 即将到期（7 天内）/ 待支付 / 宽限期 / 已取消 / 已过期
- 统计：本月支出、本月实际到期、年支出、未来 30 天、分类统计、近 12 个月趋势
- 日历视图：按月查看扣费 / 服务到期事件
- 到期提醒：系统日志 + 邮件 (SMTP) + PushPlus 微信推送（每个订阅每天每渠道一次；默认每天 09:00 固定时刻推送，可在「设置 → 提醒偏好」调整）
- 数据迁移：支持 CSV 导入导出

## 技术栈

- 后端：Python 3 + Flask（`Flask-SQLAlchemy` / `Flask-Migrate` / `SQLAlchemy`，见 `app/backend/requirements.txt`）；通知渠道使用标准库 `smtplib` / `urllib`
- 前端：Vue 3 + Vite（`frontend/`），构建产物输出到 `app/www/`
- 数据库：SQLite（WAL 模式，Alembic 版本化迁移）
- 接入方式：飞牛统一网关（Unix Socket + 登录态校验，`X-Trim-Userid` 隔离用户数据）

## 目录结构

```text
.
├── manifest                  # fnOS 应用元数据
├── ICON.PNG / ICON_256.PNG   # 应用包图标
├── config/
│   ├── privilege             # 运行身份（run-as=package）
│   └── resource              # data-share 共享备份目录
├── cmd/                      # 生命周期脚本
│   ├── main                  # start / stop / status
│   ├── install_callback      # 初始化数据库（幂等）
│   └── upgrade_callback      # 升级回调（补迁数据库 schema）
├── wizard/install            # 安装向导（到期提醒提前天数）
├── app/
│   ├── backend/              # Python 后端（分层架构）
│   │   ├── server.py         # 进程入口（参数解析 / 日志 / UDS·TCP 监听）
│   │   ├── app.py            # 应用工厂 create_app（装配配置/扩展/中间件/蓝图/迁移）
│   │   ├── config.py         # Flask 配置类（按环境隔离）
│   │   ├── paths.py          # 路径与环境变量解析
│   │   ├── extensions.py     # Flask 扩展单例（db / migrate）
│   │   ├── api/              # 路由层：每个资源一个蓝图
│   │   ├── http/             # WSGI 网关前缀剥离中间件、统一响应封装
│   │   ├── domain/           # 领域层（领域模型、周期推进、状态派生、异常）
│   │   ├── services/         # 业务应用服务层（统计/通知/备份/订阅/分类/设置/调度）
│   │   ├── repositories/     # 持久化访问层（各资源 CRUD、启动引导）
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── schemas/          # 请求/响应数据校验
│   │   ├── migrations/       # Alembic 迁移脚本（versions/ 按序编号）
│   │   ├── utils/            # 基础设施层
│   │   │   ├── channels/     # 通知渠道（email.py、pushplus.py）
│   │   │   └── file_utils.py # 文件写入与落盘工具
│   │   └── vendor/           # 打包预置的 Linux cp312 轮子（x86_64 / aarch64）
│   ├── www/                  # 前端构建产物（后端静态服务根目录）
│   └── ui/
│       ├── config            # 统一网关入口（/app/subscription）
│       └── images/           # 入口图标
├── frontend/                 # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── layouts/          # 页面布局壳
│   │   ├── views/            # 页面视图组件
│   │   ├── components/       # 通用 UI 组件
│   │   ├── services/         # 前端 API 业务服务
│   │   ├── styles/           # 设计令牌与全局样式
│   │   └── utils/            # 格式化、UI状态与交互工具
├── dev.sh / dev.ps1          # 一键本地预览（Flask 后端 + Vite 前端）
├── package.sh / package.ps1  # 一键打包（fnpack）
├── tools/
│   ├── seed_demo_data.py     # 演示数据生成与灌库脚本
│   ├── vendor_deps.py        # 预置 Linux cp312 轮子到 backend/vendor
│   ├── fpk_stage.py          # 打包暂存目录准备与校验
│   └── package/              # 内置 fnpack 二进制
└── tests/                    # 测试套件（单元测试、安全测试、回归测试）

```

## 前端架构

Vue 前端采用 **BaseLayout（公共页面壳）+ Sub Page（子页面）** 结构：

```text
frontend/src/
├── layouts/BaseLayout.vue    # 公共壳：侧边栏（导航/新增/折叠按钮）+ 顶栏 + 浮动到期提醒（可收起/关闭）+ Toast
│                              #   主区为滚动容器 .page-host，<component :is> + keep-alive 切换 Sub Page
└── views/                    # Sub Pages，各自只管内容，不重复写壳
    ├── SubscriptionsView.vue   # 订阅列表（统计卡/筛选/表格/增删改续费/弹窗）
    ├── CalendarView.vue        # 日历
    ├── StatisticsView.vue      # 统计
    └── SettingsView.vue        # 设置
```

- 切换导航 = 切换 BaseLayout 下的 Sub Page（keep-alive 保留各页状态，如日历月份、列表数据）；
- 外壳锁死视口（`height:100vh`），**Sub Page 在主窗口内滚动**（`.page-host` 内部 `overflow-y:auto`），
  顶栏/侧边栏折叠按钮始终可见；滚动条已隐藏（Chromium WebView 与 Firefox 双兼容）；
- 设计令牌集中管理（`src/styles/tokens.css`）：色板/间距/字号/圆角/阴影/z-index，页面样式禁止魔法数字；
- 状态类由 `src/utils/ui.js` 轻量 store 管理（未引入 vue-router / 状态库，保持轻依赖）；
- 新增 Sub Page 三步：`views/` 新建组件 → `layouts/BaseLayout.vue` 的 `NAV`/`PAGES` 注册 → 跑 `npm run check:views` 回归。

## 本地开发

```bash
# 一键热更新开发（自动拉起 Flask 后端 :3001 + Vite dev :5173，支持 HMR 热更新）
./dev.sh
# 访问地址 http://localhost:5173/
# PowerShell 等价脚本：.\dev.ps1
# 可调参数：-b 后端端口（默认 3001）、-f 前端端口（默认 5173）、-d SQLite 路径（默认 ./data/subscription.db）

# 前端回归检查（BaseLayout/Sub Page 隔离、折叠按钮、滚动容器断言）
cd frontend && npm run check:views

# 手动启动后端（TCP 模式）
python3 app/backend/server.py --http 8000 --db ./data/subscription.db --www app/www
# 网关模式（Unix Socket）
python3 app/backend/server.py --uds /tmp/app.sock --db ./data/subscription.db --www app/www

# 运行单元测试
python3 -m unittest discover -s tests -v
```

多用户测试：请求头带 `X-Trim-Userid: 1000` 即可模拟不同 NAS 用户。

## 打包与安装（飞牛 fnOS）

请用仓库脚本一键打包，不要在项目根目录直接 `fnpack build`。
`fnpack` 会把 `app/` 下几乎所有文件打进 `app.tgz`，**不读 `.gitignore`**。
Windows 开发机上的 `app/backend/.venv`（含指向 `C:\...` 的符号链接）一旦打进去，飞牛安装时就会报「解压 app.tgz 失败」。

```bash
# Linux / macOS / Git Bash
./package.sh
# 跳过版本自增：NO_BUMP=1 ./package.sh

# Windows PowerShell
.\package.ps1
# 跳过版本自增：.\package.ps1 -NoBump
```

脚本流程：`build.sh`/`build.ps1` 构建前端并同步到 `app/www` →
`tools/vendor_deps.py` 预置 Linux cp312 轮子到 `app/backend/vendor/`（x86_64 + aarch64）→
拷到干净暂存目录（排除 `.venv` / `.idea` / `__pycache__`，`cmd/` 转为 LF；
默认只在暂存目录自增 version，**打包失败不会改仓库 manifest**）→
`fnpack build --directory <stage>` → 把 `cmd/*` 执行位置为 `0755` 并校验 `app.tgz`，
校验通过后才把新版本写回 `manifest`。
产出仓库根目录的 `subscription.fpk`。

安装回调不再在设备上 `pip install`。若安装失败，SSH 查看
`$TRIM_PKGVAR/logs/install.log`（通常在 `/var/apps/subscription/var/logs/install.log` 附近，以设备为准）。

校验失败（体积过大、含 `.venv`、含 Windows 符号链接、缺少 `www/index.html`）会让打包以非 0 退出。
应急跳过校验：`SKIP_VERIFY=1`（不推荐）。

```bash
# 仅在飞牛设备上安装已产出的包
appcenter-cli install-fpk subscription.fpk
# 或应用中心 -> 手动安装
```

安装后在桌面打开「订阅管理」即可（统一网关 `/app/subscription`）。数据存放在 `$TRIM_PKGVAR`。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `TRIM_APPDEST` | 应用安装目录（含 www / backend） |
| `TRIM_PKGVAR` | 运行数据目录（数据库、日志） |
| `TRIM_SYS_ARCH` | 设备架构 |
| `wizard_reminder_days` | 安装向导设置的提醒提前天数 |
| `SUBSCRIPTION_DEBUG` | 置为 `1` 时运行日志输出 DEBUG 级别（默认 INFO） |
| `GATEWAY_PREFIX` | 统一网关前缀（默认 `/app/subscription`，须与 `app/ui/config` 的 `gatewayPrefix` 一致） |

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查（返回 `status` 与 `version`） |
| GET/POST | `/api/subscriptions` | 列表 / 新增（新增成功返回 201）。列表默认全量；带 `?page` 时分页返回，支持 `per_page`(1-100，默认 20) / `lifecycle` / `category_id` 筛选 |
| GET/PUT/DELETE | `/api/subscriptions/{id}` | 详情 / 更新 / 删除（软删除） |
| POST | `/api/subscriptions/{id}/restore` | 恢复已软删除的订阅 |
| POST | `/api/subscriptions/{id}/renew` | 续费（推进到下一期） |
| GET/POST | `/api/categories` | 分类列表 / 新增 |
| PUT/DELETE | `/api/categories/{id}` | 更新 / 删除分类 |
| GET | `/api/payments` | 支付流水：按 `?subscription_id=` 查询，或 `?start_date=&end_date=`（均必填，`YYYY-MM-DD`）按区间查询；都不传则返回全部 |
| GET/PUT | `/api/settings` | 读取 / 更新设置 |
| GET | `/api/statistics?mode=nominal\|actual` | 统计（`mode` 默认 `nominal`） |
| GET | `/api/calendar?year=&month=` | 日历事件（默认当前年月） |
| GET | `/api/export/csv` | 导出 CSV |
| GET | `/api/backup/import-template` | 下载 CSV 导入模板 |
| POST | `/api/backup/import-csv` | 导入 CSV（按名称+金额+周期去重） |
| GET | `/api/notifications/upcoming` | 即将到期提醒 |
| POST | `/api/notifications/test-email` | 测试邮件通知（设置页调用） |
| POST | `/api/notifications/test-pushplus` | 测试 PushPlus 推送（设置页调用） |
| GET | `/api/logs/tail?lines=200` | 运行日志尾部读取（`lines` 上限 1000） |

统一响应为 `{code, message, data}`（`code == 0` 表示成功），CSV 导出端点直接返回文件流。非 API 路径由后端兜底服务前端静态资源：`/` 返回 `index.html`，命中静态文件则直出，否则回退 `index.html`（SPA fallback）。

## 常见问题

### 打开应用后 app.js / style.css 404

原因：统一网关会把 `gatewayPrefix` **原样转发**给应用（文档见
`developer.fnnas.com/docs/core-concepts/gateway-registration/`），应用需自行处理前缀。
`gatewayPrefix` 规范为 `/app/{appname}`（即 `/app/subscription`），不能写成 `/app`。
若真机注册的前缀与配置不一致（例如配成了 `/app`），浏览器请求 `/app/app.js`，
后端无法剥离前缀导致静态资源 404。

处理：后端已做自适应——优先按 `GATEWAY_PREFIX`（默认 `/app/subscription`）剥离；
不一致时自动识别 `/app/...` 挂载并校验为 API 或静态文件后使用，两种前缀均可访问。
同时请把 `app/ui/config` 中的 `gatewayPrefix` 保持为 `/app/subscription`（文档要求），
重新打包安装即可。

### 打开应用后资源 404，且 URL 是 /app/style.css（没有 /app/subscription 前缀）

原因：页面入口 URL **不带结尾斜杠**（如 `/app/subscription`）时，浏览器会把相对路径
`style.css` 解析到上一层目录 `/app/style.css`，该路径不在网关注册前缀下，网关直接 404，
请求到不了应用。

处理：后端已对「挂载路径不带斜杠」返回 302 跳转到带斜杠版本（如
`/app/subscription` → `/app/subscription/`），入口 `url` 也已改为带斜杠；
请用**最新代码**重新打包（版本号已升至 0.1.1，确保真机覆盖安装），
并直接访问 `http://<nas>:5666/app/subscription/`。

### 如何确认新版是否装上

- 版本号应为 0.1.1（`manifest` 中的 `version`），若应用中心仍显示旧版本，先卸载再安装。
- 在浏览器访问 `http://<nas>:5666/app/subscription/`（**带结尾斜杠**），页面能打开即正常；
  再访问 `http://<nas>:5666/app/subscription/app.js` 应返回 200。

## 数据说明

- 数据库：`$TRIM_PKGVAR/subscription.db`（WAL 模式，金额以「分」整数存储）
- 日志：`$TRIM_PKGVAR/logs/app.log`（按大小轮转：单文件 2MB、保留 5 份；启动时清理超过 30 天的轮转日志）
- 调试日志：`SUBSCRIPTION_DEBUG=1` 时输出 DEBUG 级别；本地 TCP 模式日志同时回显终端，网关模式只写文件
- 升级：`upgrade_callback` 自动补迁数据库 schema（版本化迁移）

## 与 zephyr-tarui 的对应关系

| zephyr-tarui (Rust) | 本仓库 (Python) |
| --- | --- |
| `db/migrations.rs` | `migrations/`（Alembic）+ `repositories/`（CRUD） |
| `domain/renewal.rs` `domain/dates.rs` `domain/calendar.rs` | `domain/domain.py` |
| `services.rs` | `services/` |
| `backup.rs` | `services/backup.py` |
| `notification.rs` `email.rs` `pushplus.rs` `scheduler.rs` | `services/notifications.py` `utils/channels/email.py` `utils/channels/pushplus.py` `services/scheduler.py` |
| Tauri IPC command | `server.py` 进程入口 + `api/` HTTP 路由 |

## 已知限制 / TODO

- 汇率需手动配置（NAS 无外网时也可用）；如需自动更新可扩展 `exchange_rate` 模块
- 免打扰 / 邮件 / PushPlus 配置在「设置」页
- 桌面系统通知渠道暂以应用内横幅 + 日志呈现
