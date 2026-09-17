# 订阅管理 (zephyr-fn) 架构设计文档

本文档详细阐述了飞牛 fnOS 订阅管理应用（`zephyr-fn`）的前端与后端架构设计、通信机制、组件结构、数据流转与核心时序。

---

## 1. 系统总体拓扑与网络接入架构

应用作为飞牛 fnOS 容器生态内的第三方原生应用，依托飞牛统一网关实现鉴权与反向代理。

### 1.1 系统网络与进程拓扑图

```mermaid
flowchart TD
    subgraph ClientLayer["客户端 / 浏览器"]
        Browser["fnOS Web 桌面 / 移动端浏览器"]
    end

    subgraph GatewayLayer["fnOS 统一网关 (Reverse Proxy)"]
        Gateway["fnOS Gateway (5666 端口)"]
        AuthModule["网关注入身份头:<br/>X-Trim-Userid / X-Trim-Isadmin / X-Trim-Username"]
    end

    subgraph AppContainer["应用运行环境 (TRIM_APPDEST / TRIM_PKGVAR)"]
        subgraph StaticWWW["前端静态资源 (app/www)"]
            SPA["SPA 静态文件 (index.html, JS, CSS, Assets)"]
        end

        subgraph BackendProcess["Python Flask 后端服务 (server.py)"]
            SocketServer["UnixWSGIServer (app.sock) / TCP (:3001/:8000)"]
            WSGI["GatewayPrefixMiddleware (前缀自适应剥离)"]
            FlaskCore["Flask Core (API / Services / Domain)"]
            SchedulerThread["后台调度线程 (Daily Notification Scheduler)"]
        end

        subgraph StorageLayer["持久化与本地数据"]
            SQLite[("SQLite 数据库 (WAL 模式)<br/>subscription.db")]
            LogFiles["轮转运行日志<br/>logs/app.log"]
        end
    end

    subgraph ExternalChannels["外部推送服务"]
        SMTP["SMTP 邮件服务器"]
        PushPlus["PushPlus 微信推送 API"]
    end

    Browser -->|"HTTP / HTTPS 访问 /app/subscription/"| Gateway
    Gateway --> AuthModule
    AuthModule -->|"UDS 套接字转发 + 身份头注入"| SocketServer
    SPA -.->|"构建产物直出"| FlaskCore
    SocketServer --> WSGI --> FlaskCore
    FlaskCore --> SQLite
    FlaskCore --> LogFiles
    SchedulerThread --> SQLite
    SchedulerThread -->|"到期提醒触发"| SMTP
    SchedulerThread -->|"到期提醒触发"| PushPlus
```

### 1.2 接入与环境特性
- **双模监听支持**：生产环境通过 `--uds $TRIM_APPDEST/app.sock` 接收网关转发；本地开发通过 `--http 8000` 接收 TCP 直连请求。
- **租户隔离机制**：统一网关校验登录态后注入 `X-Trim-Userid`，后端服务全程依赖此 Header 实现多用户数据隔离。

---

## 2. 前端架构设计 (Vue 3 + Vite)

前端采用 **BaseLayout（公共页面壳）+ Sub Pages（子页面视图）** 体系，未使用重型路由库与中心化状态库，保证轻量、低内存占用与高响应性。

### 2.1 前端分层与组件架构图

```mermaid
flowchart TD
    subgraph EntryPoint["入口与应用引导"]
        MainJS["main.js (createApp)"]
        AppVue["App.vue (根容器)"]
    end

    subgraph LayoutLayer["布局与页面壳 (BaseLayout)"]
        BaseLayout["BaseLayout.vue (公共页面壳)"]
        Sidebar["Sidebar.vue (侧边栏导航/新增/折叠)"]
        TopBar["TopBar (顶栏/主题切换/汉堡菜单)"]
        NoticeBanner["到期浮动提醒横幅 (可折叠/关闭)"]
        ToastHost["HeadlessToast (全局消息提示)"]
        PageHost["滚动宿主容器 (.page-host)"]
    end

    subgraph ViewsLayer["子页面层 (Sub Pages / Keep-Alive)"]
        SubView["SubscriptionsView.vue<br/>(订阅列表/筛选/批量/增删改/续费)"]
        CalendarView["CalendarView.vue<br/>(月度日历/到期与续费事件)"]
        StatView["StatisticsView.vue<br/>(名义与实际支出/多货币/趋势图)"]
        SettingsView["SettingsView.vue<br/>(汇率/通知渠道配置/CSV导入导出/日志)"]
    end

    subgraph ComponentsLayer["通用与业务组件库"]
        SubModal["SubscriptionModal.vue (订阅编辑/新增弹窗)"]
        TplSelector["TemplateSelector.vue (内置订阅模板选择器)"]
        HeadlessBtn["HeadlessButton"]
        HeadlessDate["HeadlessDatePicker"]
        HeadlessBox["HeadlessListbox"]
        HeadlessSwitch["HeadlessSwitch"]
        HeadlessTime["HeadlessTimePicker"]
    end

    subgraph StateLogic["状态与逻辑层 (State & Utilities)"]
        UIState["ui.js (reactive)<br/>- view 切换<br/>- theme 主题状态<br/>- sidebar 展开收起<br/>- toast 队列与两阶段动画"]
        FormatUtil["format.js<br/>- 金额分转元<br/>- 货币汇率折算<br/>- 相对日期格式化"]
        TplData["subscriptionTemplates.js (预设模板库)"]
    end

    subgraph ServiceLayer["前端通信层 (API Client)"]
        ApiClient["services/api.js<br/>- 统一前缀适配 (dev 走 /api，prod 走网关前缀)<br/>- 统一解包 {code, message, data}<br/>- CSV 导出与下载端点"]
    end

    subgraph StyleTokens["样式与设计令牌"]
        TokensCSS["tokens.css (色彩/间距/字号/圆角/阴影/z-index)"]
        MainCSS["main.css (基底样式与 WebView 兼容规则)"]
    end

    MainJS --> AppVue --> BaseLayout
    BaseLayout --> Sidebar
    BaseLayout --> TopBar
    BaseLayout --> NoticeBanner
    BaseLayout --> ToastHost
    BaseLayout --> PageHost

    PageHost -->|"动态挂载 component :is"| SubView
    PageHost --> CalendarView
    PageHost --> StatView
    PageHost --> SettingsView

    SubView --> SubModal
    SubView --> HeadlessBtn
    SubView --> HeadlessBox
    SubModal --> TplSelector
    SubModal --> HeadlessDate
    SettingsView --> HeadlessSwitch
    SettingsView --> HeadlessTime

    ViewsLayer -.->|"读取/修改状态"| UIState
    ViewsLayer -.->|"数据格式化"| FormatUtil
    TplSelector -.->|"选取模板"| TplData
    ViewsLayer -->|"调用 HTTP 接口"| ApiClient

    StyleTokens -.-> LayoutLayer
    StyleTokens -.-> ViewsLayer
```

### 2.2 前端核心机制
1. **视口隔离与滚动托管**：外层壳固定视口高度（`height: 100vh`），所有视图内容在 `.page-host` 内滚动，且滚动条自适应隐藏，彻底杜绝外层抖动与双滚动条。
2. **Keep-Alive 状态保活**：各子页面通过 `<component :is="...">` + `<keep-alive>` 保持状态，在日历切换月份或列表进行筛选时，切走再切回仍保留上下文。
3. **设计令牌化 (Design Tokens)**：颜色、间距、圆角与层级统一在 `tokens.css` 中声明 CSS 变量，支持浅色、深色及跟随系统自动切换。

---

## 3. 后端分层架构设计 (Python + Flask)

后端严格遵循经典的分层架构：WSGI 中间件层 $\to$ 路由层 $\to$ 服务层 $\to$ 领域层 $\to$ 仓储持久化层。

### 3.1 后端详细分层图

```mermaid
flowchart TD
    subgraph TransportLayer["1. 接入与网络传输层 (Server Layer)"]
        ServerEntry["server.py (命令行入口与主进程)"]
        UDS["UnixWSGIServer (标准库多线程 AF_UNIX)"]
        TCP["Flask 本地调试服务器 (TCP Socket)"]
        AppFactory["create_app() (应用工厂)"]
    end

    subgraph WSGIMiddlewareLayer["2. WSGI 与请求边界中间件层 (Web / Middleware)"]
        PrefixMW["GatewayPrefixMiddleware<br/>- 剥离网关前缀 (/app/subscription 或 /app)<br/>- 改写 PATH_INFO / SCRIPT_NAME<br/>- 静态文件/SPA Fallback 探测"]
        IdentityMW["parse_identity()<br/>- 解析 X-Trim-Userid / X-Trim-Isadmin<br/>- 封装 RequestIdentity 注入 g.identity"]
        AdminMW["check_admin_only()<br/>- 保护设置、备份、导出、测试推送等敏感接口"]
        CategoryMW["ensure_default_categories()<br/>- 新用户首访幂等补种系统默认分类"]
        ErrorHandler["全局异常捕获与响应封装 (response.py)<br/>- ApiError / ValidationError / 404 / 500<br/>- 统一格式: {code, message, data}"]
    end

    subgraph ApiControllerLayer["3. 路由与控制器层 (API Blueprints)"]
        BP_Sub["subscriptions.py (增删改查/分页/续费/恢复)"]
        BP_Cat["categories.py (分类增删改查)"]
        BP_Pay["payments.py (支付流水查询)"]
        BP_Stat["statistics.py (名义/实际支出与多维统计)"]
        BP_Cal["calendar.py (月度日历事件聚合)"]
        BP_Set["settings.py (全局设置读写)"]
        BP_Bak["backup.py (CSV导入/导出/模板)"]
        BP_Not["notifications.py (到期提醒/测试推送)"]
        BP_Log["logs.py (运行日志尾部回显)"]
        BP_Web["web.py (SPA 静态资源与兜底响应)"]
    end

    subgraph ServiceLayer["4. 应用业务服务层 (Services)"]
        Svc_Sub["services/subscriptions.py (订阅业务与支付关联)"]
        Svc_Cat["services/categories.py (分类业务与默认值)"]
        Svc_Stat["services/statistics.py (聚合计算与汇率折算)"]
        Svc_Bak["services/backup.py (CSV 解析校验与幂等合并)"]
        Svc_Set["services/settings.py (偏好与渠道凭证持久化)"]
        Svc_Not["services/notifications.py (到期扫描与频控去重)"]
        Svc_Sch["services/scheduler.py (守护线程: 每日定时巡检与唤醒补偿)"]
    end

    subgraph DomainLayer["5. 核心领域模型与规则层 (Domain)"]
        DomainCore["domain/domain.py<br/>- add_one_period() (周期精确推进)<br/>- derive_status() (状态机派生: 活跃/即将到期/待支付/宽限期/过期)<br/>- 续费策略评估 (auto / manual / stop / stop_on_expiry)<br/>- 日历事件生成与可见性判断"]
        DomainExceptions["domain/exceptions.py (领域异常定义)"]
    end

    subgraph PersistenceLayer["6. 数据仓储与持久化层 (Repositories & Models)"]
        subgraph Repositories["仓储访问层 (Repositories)"]
            Repo_Sub["subscription_repo.py"]
            Repo_Cat["category_repo.py"]
            Repo_Pay["payment_repo.py"]
            Repo_Set["settings_repo.py"]
            Repo_Not["notification_repo.py"]
            Repo_Boot["bootstrap.py (旧库迁移与系统配置补种)"]
        end

        subgraph ORMModels["SQLAlchemy ORM 模型 (Models)"]
            M_Sub["Subscription (订阅实体)"]
            M_Cat["Category (分类实体)"]
            M_Pay["Payment (支付流水实体)"]
            M_Set["AppSettings (单例全局设置)"]
            M_Not["NotificationLog (提醒流水与防重放索引)"]
        end

        subgraph DBEngine["底层数据库与迁移"]
            Alembic["Alembic 迁移脚本 (migrations/versions)"]
            SQLiteDB[("SQLite 数据库 (WAL 模式, 外键开启)")]
        end
    end

    subgraph InfraLayer["7. 基础设施与外部渠道 (Utils / Channels)"]
        Ch_Email["channels/email.py (SMTP/SSL/STARTTLS 邮件投递)"]
        Ch_Push["channels/pushplus.py (PushPlus 微信模板通知)"]
        VendorDeps["vendor/ (预置 Linux cp312 轮子: x86_64 / aarch64)"]
    end

    ServerEntry --> AppFactory
    ServerEntry --> UDS
    ServerEntry --> TCP
    AppFactory --> WSGIMiddlewareLayer
    PrefixMW --> IdentityMW --> AdminMW --> CategoryMW --> ApiControllerLayer
    ApiControllerLayer --> ServiceLayer
    ServiceLayer --> DomainLayer
    ServiceLayer --> Repositories
    Repositories --> ORMModels --> DBEngine
    Alembic -.->|"启动时自动升级 schema"| SQLiteDB
    Repo_Boot -.->|"就地升级与数据填充"| SQLiteDB

    Svc_Sch -.-> Svc_Not
    Svc_Not --> Ch_Email
    Svc_Not --> Ch_Push
    ErrorHandler -.-> ApiControllerLayer
```

### 3.2 领域层关键规则
- **单一事实来源 (SSOT)**：以 `renewal_policy`（`auto` / `manual` / `stop` / `stop_on_expiry`）为唯一策略源，对外兼容只读派生字段 `auto_renew`。
- **状态派生机**：不持久化存储易变的状态（如即将到期），统一由 `derive_status(now, period_end, renewal_policy, billing_status)` 动态推导。
- **周期精确推进**：`add_one_period` 考虑月末锚定（如 1 月 31 日加 1 个月为 2 月 28/29 日，下月自动恢复 31 日）与闰年闰月计算。

---

## 4. 核心业务交互时序图

### 4.1 典型业务时序：订阅续费与流水落盘

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户 (Browser)
    participant UI as 前端 SubscriptionsView
    participant Api as 前端 api.js
    participant GW as fnOS 网关
    participant MW as 后端 WSGI & 中间件
    participant Ctrl as subscriptions 蓝图
    participant Svc as subscriptions 服务
    participant Domain as domain 领域引擎
    participant Repo as 仓储层 (Sub & Pay Repo)
    participant DB as SQLite 数据库

    User->>UI: 点击「续费」按钮
    UI->>Api: renewSubscription(id)
    Api->>GW: POST /app/subscription/api/subscriptions/{id}/renew
    Note over GW: 网关完成鉴权，注入 Header:<br/>X-Trim-Userid: 1000<br/>X-Trim-Isadmin: true
    GW->>MW: 转发到 Unix Domain Socket
    MW->>MW: GatewayPrefixMiddleware 剥离前缀<br/>PATH_INFO 改为 /api/subscriptions/{id}/renew
    MW->>MW: parse_identity 解析租户身份并存入 g.identity
    MW->>Ctrl: 调用路由控制器
    Ctrl->>Svc: renew_subscription(user_id, id)
    Svc->>Repo: 获取当前订阅实体
    Repo->>DB: SELECT * FROM subscriptions WHERE id=? AND user_id=?
    DB-->>Repo: 返回 Subscription
    Svc->>Domain: add_one_period(current_period_end, period_type, ...)
    Domain-->>Svc: 计算出下一期周期与到期日 (next_period_start, next_period_end)
    Svc->>Domain: derive_status(...) 派生新生命周期
    Svc->>Repo: 1. 更新 Subscription 周期与支付锚点
    Svc->>Repo: 2. 自动生成 Payment 流水记录 (payment_type='renewal')
    Repo->>DB: 事务提交 (COMMIT: subscriptions 更新 + payments 插入)
    DB-->>Repo: 成功
    Svc-->>Ctrl: 返回最新订阅明细
    Ctrl-->>MW: ok(data) 打包成 {code: 0, message: "ok", data: ...}
    MW-->>GW: HTTP 200 JSON
    GW-->>Api: 响应数据
    Api->>Api: 解包 code === 0，返回 data
    Api-->>UI: 响应完成
    UI->>User: Toast 提示「续费成功」，表格原位更新
```

### 4.2 后台巡检时序：到期检查与多渠道防重推送

```mermaid
sequenceDiagram
    autonumber
    participant Sch as Scheduler 后台线程
    participant Svc as notifications 服务
    participant Repo as 仓储层
    participant DB as SQLite 数据库
    participant Mail as SMTP 邮件渠道
    participant Push as PushPlus 微信渠道

    loop 每分钟巡检一次 (daemon thread)
        Sch->>Repo: 读取系统配置 AppSettings (id=1)
        Repo->>DB: SELECT notification_time, quiet_hours, channels...
        DB-->>Repo: 配置参数
        alt 当前时间匹配 notification_time 且未处于免打扰区间
            Sch->>Svc: check_and_send_due_notifications()
            Svc->>Repo: 查询所有用户即将到期或超期的订阅
            Repo->>DB: 检索符合条件的活跃订阅
            DB-->>Repo: 返回订阅列表
            loop 遍历每个待通知订阅
                Svc->>Repo: 检查 NotificationLog (今日、该订阅、该渠道是否已推送)
                Repo->>DB: SELECT COUNT(*) FROM notification_logs WHERE ...
                DB-->>Repo: 0 (未发送)
                alt 启用了邮件且配置完整
                    Svc->>Mail: send_email(subject, content)
                    Mail-->>Svc: 发送成功
                    Svc->>Repo: 记录 NotificationLog(channel='email', status='sent')
                    Repo->>DB: INSERT INTO notification_logs
                end
                alt 启用了 PushPlus 且配置 Token
                    Svc->>Push: send_pushplus(token, content)
                    Push-->>Svc: 发送成功
                    Svc->>Repo: 记录 NotificationLog(channel='pushplus', status='sent')
                    Repo->>DB: INSERT INTO notification_logs
                end
            end
        end
    end
```

---

## 5. 实体关系模型 (ER Diagram)

后端基于 SQLite WAL 模式运行，核心实体与外键关系如下：

```mermaid
erDiagram
    Subscription ||--o{ Payment : "生成/关联流水"
    Category ||--o{ Subscription : "归属分类"
    Subscription ||--o{ NotificationLog : "记录推送流水"

    Subscription {
        string id PK "订阅唯一ID (UUID32)"
        string user_id "所属用户ID (逻辑隔离)"
        string name "订阅服务名称"
        int amount "金额 (存储单位: 分)"
        string currency "货币代码 (CNY/USD/HKD)"
        string category_id FK "分类外键"
        string period_type "周期类型 (month/quarter/year/once/custom)"
        string renewal_policy "续费策略 (auto/manual/stop/stop_on_expiry)"
        string lifecycle "生命周期 (active/grace_period/canceled/ended/expired)"
        string current_period_start "当前周期起始日"
        string current_period_end "当前周期截止日"
        string next_due_date "下一扣费日"
        string deleted_at "软删除时间戳"
    }

    Payment {
        string id PK "流水ID"
        string subscription_id FK "关联订阅"
        string user_id "所属用户ID"
        int amount "扣费金额 (分)"
        string currency "货币代码"
        float exchange_rate "结算汇率"
        int amount_cny "折算人民币金额 (分)"
        string paid_at "支付日期"
        string period_start "计费周期起"
        string period_end "计费周期止"
        string payment_type "类型 (first/renewal/refund/adjustment)"
    }

    Category {
        string id PK "分类ID"
        string user_id "所属用户ID"
        string name "分类名称 (NOCASE 唯一)"
        string icon "Emoji 图标"
        int sort_order "排序权重"
    }

    NotificationLog {
        string id PK "记录ID"
        string subscription_id FK "关联订阅"
        string notification_date "通知日期 (YYYY-MM-DD)"
        string channel "渠道 (email/pushplus)"
        string status "状态 (sent/failed)"
    }

    AppSettings {
        int id PK "主键单例 (恒为1)"
        string default_currency "默认货币"
        float exchange_rate_usd "USD对CNY汇率"
        float exchange_rate_hkd "HKD对CNY汇率"
        int notification_days "提前提醒天数"
        string notification_time "每日提醒时间 (HH:MM)"
        int email_enabled "是否启用邮件"
        int pushplus_enabled "是否启用PushPlus"
    }
```

---

## 6. 核心工程决策与亮点总结

| 维度 | 设计方案 | 解决的核心问题 |
| :--- | :--- | :--- |
| **网关路径自适应** | WSGI 层 `GatewayPrefixMiddleware` | 统一网关转发时原样保留 `/app/subscription` 前缀，中间件在 Flask 处理前自动重写 `PATH_INFO` 与 `SCRIPT_NAME`，同时兼容直接挂在 `/app` 下与本地 `/` 开发环境。 |
| **多租户安全隔离** | 基于网关头的全局用户会话 `g.identity` | 飞牛 NAS 为多用户系统，所有 CRUD 查询强制绑定 `user_id`，杜绝垂直与水平越权漏洞。 |
| **金额整数存储** | 数据库与后端全链路采用「分」作为整数类型 | 彻底消除浮点数在金额计算、汇率折算与账目累加过程中的精度丢失风险。 |
| **幂等补迁机制** | `bootstrap` 就地升级 + `Flask-Migrate` (Alembic) | 保证新装、旧版升级（从早期 SQLite 到带有 payments/deleted_at 的新表）平滑过渡，重启服务无缝兼容。 |
| **纯离线依赖打包** | `vendor/` 预置 cp312 manylinux 平台轮子 | 飞牛真机安装包不进行联网 `pip install`，避免设备无法连接 PyPI 导致的部署失败。 |
