// 页面壳 + Sub Page 回归检查：
//   BaseLayout 提供公共壳（侧边栏/顶栏/横幅/折叠按钮），切换导航 = 切换 Sub Page。
//   Sub Page 在主窗口内部滚动（overflow-y:auto 的 .page-host），不带动顶栏/侧边栏。
// 断言（每个视图状态）：
//   1. 恰好渲染 1 个 Sub Page 且位于滚动容器 .page-host 内
//   2. 侧边栏折叠按钮 sidebar-toggle 必须存在（曾因侧边栏被内容页撑高而看不见）
//   3. 导航高亮与标题对应；零 Vue 警告
// 用法: npm run check:views   （失败退出码 1）
import { createServer } from "vite";
import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true, hmr: false },
  optimizeDeps: { noDiscovery: true },
  logLevel: "error",
  appType: "custom",
});

const TITLES = {
  subscriptions: "订阅列表",
  calendar: "日历",
  statistics: "统计",
  settings: "设置",
};

let failed = false;
const warnings = [];
const originalWarn = console.error;
console.error = (...args) => warnings.push(args.join(" "));

try {
  const { default: App } = await server.ssrLoadModule("/src/App.vue");
  const { ui } = await server.ssrLoadModule("/src/ui.js");

  for (const view of ["subscriptions", "calendar", "statistics", "settings"]) {
    ui.view = view;
    const html = await renderToString(createSSRApp(App));

    const pages = (html.match(/class="page"/g) || []).length;
    const scrollHost = html.includes('class="page-host"');
    const hasToggle = html.includes('class="sidebar-toggle"');
    const hasFooter = html.includes('class="sidebar-footer"');
    const titleOk = html.includes(`>${TITLES[view]}</h1>`);
    const activeNav = html.includes(`class="active nav-item"`) &&
      html.includes(`>${TITLES[view]}</span>`);

    const pass = pages === 1 && scrollHost && hasToggle && hasFooter && titleOk && activeNav;
    failed ||= !pass;
    console.log(
      `view=${view.padEnd(13)} sub-page=${pages} 滚动容器=${scrollHost} 折叠按钮=${hasToggle} ` +
        `footer=${hasFooter} 标题=「${TITLES[view]}」高亮=${activeNav}  ${pass ? "✓" : "✗"}`
    );
  }
} finally {
  console.error = originalWarn;
  await server.close();
}

if (warnings.length) {
  failed = true;
  console.log(`\nVue 警告 ${warnings.length} 条（应为 0）：`);
  warnings.slice(0, 5).forEach((w) => console.log("  ", w.slice(0, 160)));
}
console.log(failed ? "\n=== BasePage/Sub Page 检查失败 ===" : "\n=== BasePage/Sub Page 检查通过（4 状态全部通过） ===");
process.exit(failed ? 1 : 0);