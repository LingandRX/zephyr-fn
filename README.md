# 订阅管理 (subscription)

飞牛 fnOS 订阅管理应用：记录订阅服务、费用与到期时间，支持多货币统计、日历视图、到期提醒与自动备份。

后端参考 [zephyr-tarui](https://github.com/LingandRX/zephyr-tarui)（Tauri + Rust 版订阅管理）的数据模型与业务逻辑，用 **Python 标准库** 重写（零第三方依赖），并针对飞牛 fnOS 平台做了适配：统一网关接入、NAS 多用户数据隔离、data-share 共享目录备份。

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
- 到期提醒：系统日志 + 邮件 (SMTP) + PushPlus 微信推送（每个订阅每天每渠道一次）
- 备份：每日自动导出 JSON + SQLite 副本到共享目录 `subscription/backups`（保留 5 份），支持手动备份、JSON/CSV 导入导出

## 技术栈

- 后端：Python 3（标准库：http.server / sqlite3 / smtplib / urllib，无第三方依赖）
- 前端：Vue 3 + Vite（默认，`frontend/`）；另保留原生 HTML/CSS/JS 零构建版（`app/www/`）作对照
- 数据库：SQLite（WAL 模式，版本化迁移）
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
│   └── install_callback      # 初始化数据库（幂等）
├── wizard/install            # 安装向导（到期提醒提前天数）
├── app/
│   ├── backend/              # Python 后端
│   │   ├── server.py         # HTTP 服务 + API 路由（网关 Socket / TCP 双模式）
│   │   ├── db.py             # SQLite 连接 / 迁移 / CRUD
│   │   ├── domain.py         # 周期推进 / 续费策略 / 状态派生 / 日历逻辑
│   │   ├── services.py       # 统计与日历服务
│   │   ├── backup.py         # JSON / CSV 导入导出、DB 合并
│   │   ├── notifications.py  # 到期筛选 / 免打扰 / 文案
│   │   ├── email_sender.py   # SMTP 邮件
│   │   ├── pushplus.py       # PushPlus 推送
│   │   └── scheduler.py      # 每小时提醒 + 每日备份
│   ├── www/                  # 前端产物目录（git 基线为 vanilla 原生版；打包前由 tools/build.sh 覆盖为 Vue 产物）
│   └── ui/
│       ├── config            # 统一网关入口（/app/subscription）
│       └── images/           # 入口图标
├── frontend/                 # Vue 3 + Vite 前端（默认前端，架构与开发详见 frontend/README.md）
├── dev.sh                    # 一键本地预览（Vue 或 vanilla）
├── tools/
│   ├── gen_icons.py          # 图标生成脚本（纯 Python）
│   └── build.sh              # 打包前构建：Vite build → 同步 app/www → 清理 __pycache__
└── tests/test_backend.py     # 单元测试（17 个）
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
- 状态类由 `src/ui.js` 轻量 store 管理（未引入 vue-router / 状态库，保持轻依赖）；
- 新增 Sub Page 三步：`views/` 新建组件 → `layouts/BaseLayout.vue` 的 `NAV`/`PAGES` 注册 → 跑 `npm run check:views` 回归。

## 本地开发

前端有两套实现，默认使用 **Vue 3 版**（`frontend/`），原生零构建版（`app/www/`）保留作对照：

```bash
# 一键预览（自动：初始化数据库 -> 构建 Vue 前端 -> 启动服务）
./dev.sh
# 默认地址 http://127.0.0.1:8000/app/subscription/
# FRONTEND=vanilla ./dev.sh  可预览原生版；PORT=9000 / DB=/tmp/t.db 可自定义

# 开发 Vue 前端（HMR，代理 /api 到后端 5001）
python3 app/backend/server.py --http 5001 --db ./data/subscription.db --www app/www --share ./data/backups
cd frontend && npm install && npm run dev   # http://localhost:5173/

# 前端回归检查（BaseLayout/Sub Page 隔离、折叠按钮、滚动容器断言）
cd frontend && npm run check:views

# 手动启动后端（TCP 模式）
python3 app/backend/server.py --http 8000 --db ./data/subscription.db --www app/www --share ./data/backups
# 网关模式（Unix Socket）
python3 app/backend/server.py --uds /tmp/app.sock --db ./data/subscription.db --www app/www --share ./data/backups

# 运行单元测试
python3 -m unittest discover -s tests -v
```

多用户测试：请求头带 `X-Trim-Userid: 1000` 即可模拟不同 NAS 用户。

## 打包与安装（飞牛 fnOS）

```bash
# 1. 前置：构建 Vue 前端并同步到 app/www（同时清理 __pycache__）
./tools/build.sh

# 2. 生成图标（如未生成）
python3 tools/gen_icons.py

# 3. 打包（需安装 fnpack，见 https://developer.fnnas.com/docs/cli/fnpack/）
fnpack build
# 产出 subscription.fpk；注意：打包前务必先运行 ./tools/build.sh，
# 否则 app/www 不是 Vue 产物（git 中的 baseline 是 vanilla 原生版）

# 4. 在飞牛 fnOS 设备上安装
appcenter-cli install-fpk subscription-0.1.0.fpk
# 或应用中心 -> 手动安装
```

安装后在桌面打开「订阅管理」即可（统一网关 `/app/subscription`）。数据存放在 `$TRIM_PKGVAR`，备份导出到共享目录 `subscription/backups`（可在文件管理器中看到，便于纳入 fnOS 系统备份）。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `TRIM_APPDEST` | 应用安装目录（含 www / backend） |
| `TRIM_PKGVAR` | 运行数据目录（数据库、日志） |
| `TRIM_DATA_SHARE_PATHS` | data-share 共享目录（备份落点） |
| `TRIM_SYS_ARCH` | 设备架构 |
| `wizard_reminder_days` | 安装向导设置的提醒提前天数 |
| `GATEWAY_PREFIX` | 统一网关前缀（默认 `/app/subscription`，须与 `app/ui/config` 的 `gatewayPrefix` 一致） |

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/subscriptions` | 列表 / 新增 |
| GET/PUT/DELETE | `/api/subscriptions/{id}` | 详情 / 更新 / 删除 |
| POST | `/api/subscriptions/{id}/renew` | 续费（推进到下一期） |
| GET/POST | `/api/categories` | 分类列表 / 新增 |
| PUT/DELETE | `/api/categories/{id}` | 更新 / 删除分类 |
| GET/PUT | `/api/settings` | 读取 / 更新设置 |
| GET | `/api/statistics?mode=nominal\|actual` | 统计 |
| GET | `/api/calendar?year=&month=` | 日历事件 |
| POST | `/api/backup` | 立即备份 |
| GET | `/api/backup/export-json` / `/api/export/csv` | 导出 |
| POST | `/api/backup/import-json` / `import-csv` | 导入（按名称+金额+周期去重） |
| GET | `/api/notifications/upcoming` | 即将到期提醒 |

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

## 数据与备份说明

- 数据库：`$TRIM_PKGVAR/subscription.db`（WAL 模式，金额以「分」整数存储）
- 日志：`$TRIM_PKGVAR/logs/app.log`
- 自动备份：每天一次，JSON + SQLite 副本写入共享目录，保留最近 5 份
- 升级：`upgrade_callback` 自动补迁数据库 schema（版本化迁移）

## 与 zephyr-tarui 的对应关系

| zephyr-tarui (Rust) | 本仓库 (Python) |
| --- | --- |
| `db/migrations.rs` | `db.py`（迁移 + CRUD） |
| `domain/renewal.rs` `domain/dates.rs` `domain/calendar.rs` | `domain.py` |
| `services.rs` | `services.py` |
| `backup.rs` | `backup.py` |
| `notification.rs` `email.rs` `pushplus.rs` `scheduler.rs` | `notifications.py` `email_sender.py` `pushplus.py` `scheduler.py` |
| Tauri IPC command | `server.py` HTTP API |

## 已知限制 / TODO

- 汇率需手动配置（NAS 无外网时也可用）；如需自动更新可扩展 `exchange_rate` 模块
- 免打扰 / 邮件 / PushPlus 配置在「设置」页
- 桌面系统通知渠道暂以应用内横幅 + 日志呈现
