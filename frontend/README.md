# 前端（Vue 3 + Vite）

订阅管理的默认前端，采用 **BaseLayout（公共页面壳）+ Sub Page（子页面）** 架构。
对齐 fnOS 官方文档（`examples/native.md`）的网关接入模式，产物为纯静态文件，
由 Python 后端直接托管，真机运行时无需 Node 环境。

## 页面架构

```
BaseLayout.vue（公共壳：侧边栏 + 顶栏 + 提醒横幅 + Toast）
└── .page-host（主窗口滚动容器，滚动条已隐藏）
    └── keep-alive
        └── <component :is>   ← 切换导航即切换这里的 Sub Page
```

- **切换导航 = 切换 Sub Page**：`ui.view`（src/ui.js）决定渲染哪个页面；
  `keep-alive` 保留各页状态（日历月份、列表数据、滚动位置）。
- **Sub Page 在主窗口内滚动**：外壳 `height:100vh + overflow:hidden`，
  仅 `.page-host`（`flex:1 + min-height:0 + overflow-y:auto`）滚动，顶栏/侧边栏固定。
- 侧边栏折叠状态持久化到 `localStorage`；公共布局只在 BaseLayout 写一次。

## 目录结构

```text
frontend/
├── package.json            # vue3 + vite；scripts: dev / build / check:views
├── vite.config.mjs         # base=/app/subscription/（build） + /api 代理（dev）
├── index.html
├── scripts/
│   └── check-views.mjs     # 回归检查：Sub Page 隔离 / 折叠按钮 / 滚动容器 / 零警告
└── src/
    ├── main.js             # 入口
    ├── App.vue             # 仅挂载 BaseLayout
    ├── layouts/
    │   └── BaseLayout.vue  # 公共页面壳（NAV/PAGES 注册表 + 侧边栏 + 顶栏 + 横幅 + Toast）
    ├── views/              # Sub Pages：各自只管内容
    │   ├── SubscriptionsView.vue   # 订阅列表：统计卡/筛选/表格/增删改续费（含弹窗）
    │   ├── CalendarView.vue        # 日历：月导航/事件/今日
    │   ├── StatisticsView.vue      # 统计：大盘/趋势柱状图/分类表
    │   └── SettingsView.vue        # 设置：常规/通知渠道/分类/备份导入导出（自动保存）
    ├── api.js              # API 封装（统一前缀，不携带用户身份）
    ├── ui.js               # 轻量全局状态（视图/侧边栏/toast/跨组件事件）
    ├── format.js           # 金额/周期/日期格式化
    ├── assets/             # 图标等静态资源（经 import 由 Vite 处理 base 路径）
    └── styles/
        ├── tokens.css      # 设计令牌（色板/间距/字号/圆角/阴影/z-index + 断点约定）
        └── main.css        # 布局 + 通用组件（已按令牌重构，无魔法数字）
```

## 新增一个 Sub Page（三步）

1. `src/views/` 新建组件（单根元素，推荐根类 `class="page"`）；
2. 在 `src/layouts/BaseLayout.vue` 的 `NAV`（导航项）与 `PAGES`（组件注册表）中登记；
3. 运行 `npm run check:views` 确认回归通过（断言每个导航状态恰好渲染 1 个 Sub Page、
   折叠按钮/滚动容器存在、标题与高亮正确、零 Vue 警告）。

## 开发运行

```bash
# 1. 先启动 Python 后端（TCP 模式，端口 5001 与 vite proxy 对齐）
python3 app/backend/server.py --http 5001 --db ./data/subscription.db --www app/www --share ./data/backups

# 2. 安装依赖并启动 Vite dev server
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173/  （/api 代理 → 127.0.0.1:5001）

# 3. 回归检查（BaseLayout/Sub Page 结构断言）
npm run check:views
```

> dev 模式页面在根路径 `/`、API 走 `/api` 代理；build 产物以 `base=/app/subscription/`
> 输出，与真机网关行为一致。官方示例采用"dev 也带前缀 + 全前缀 proxy"的写法，
> 在 Vite 6 下 proxy 会吞掉 Vite 自身模块请求而失效，本工程已避开该坑（见 vite.config.mjs 注释）。

### 一键热更新开发 / 预览 / 打包（在仓库根目录）

```bash
./dev.sh                           # 一键热更新开发（Vite dev 5173 + 后端 API 5001，支持 HMR）
BUILD=1 ./dev.sh                   # 静态构建预览（构建后由后端直服，与线上一致）
./build.sh && fnpack build         # 构建产物同步到 app/www 后打包 fpk
```

## 官方约束落实情况

| 约束（官方文档） | 本前端 |
| --- | --- |
| Vite `base` 对齐 gatewayPrefix | build 时 `base: "/app/subscription/"` ✓（dev 用根路径避免 proxy 冲突） |
| 资源不写死域名、经前缀/import 加载 | 图片等经 import 由 Vite 按 base 重写 ✓ |
| API 不携带用户身份 | api.js 只发路径，身份由后端取 `X-Trim-*` Header ✓ |
| 前端不做登录页 | 依赖网关会话校验 ✓ |
| 静态 MIME 规范（css/js 带 charset） | 后端显式映射 `text/css` / `application/javascript` + charset ✓ |
| 运行时无需 node | 产物为纯静态，Python 后端托管，manifest 无需 nodejs_v22 ✓ |
| 路由保持在前缀下、无扩展名 | API 路径 `/api/...` 无点号 ✓；WebSocket 若启用固定走 `/app/subscription/ws` |
