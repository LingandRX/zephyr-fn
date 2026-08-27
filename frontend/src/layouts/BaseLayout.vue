<script setup>
// 公共页面壳（BasePage）：
//   侧边栏（导航 / 新增按钮 / 折叠按钮）+ 顶栏 + 浮动到期提醒 + 主区（Sub Page 插槽）+ Toast
//   切换导航 = 切换本壳下的 Sub Page（keep-alive 保留各页状态）
import { computed, ref, watch, onMounted } from "vue";
import { ui, toastState, toast, openNewSub, setTheme } from "../utils/ui.js";
import { getUpcomingNotifications } from "../services/api.js";
import logo from "../assets/icon_64.png";

import SubscriptionsView from "../views/SubscriptionsView.vue";
import CalendarView from "../views/CalendarView.vue";
import StatisticsView from "../views/StatisticsView.vue";
import SettingsView from "../views/SettingsView.vue";

const THEMES = ["dark", "light", "system"];
// 主题图标：Feather 风格线性 SVG 路径（与顶栏汉堡/箭头等线性图标一致）
const THEME_ICONS = {
  dark: ["M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"], // moon
  light: [
    "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z",
    "M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42",
  ], // sun
  system: [
    "M2 3h20v13H2z",
    "M8 21h8M12 17v4",
  ], // monitor
};
const THEME_LABELS = { dark: "深色模式", light: "浅色模式", system: "跟随系统" };

const NAV = [
  { key: "subscriptions", icon: "list", label: "订阅", title: "订阅" },
  { key: "calendar", icon: "calendar", label: "日历", title: "日历" },
  { key: "statistics", icon: "statistics", label: "统计", title: "统计" },
  { key: "settings", icon: "settings", label: "设置", title: "设置" },
];

// Sub Page 注册表：切换导航 = 切换这里渲染的组件
const PAGES = {
  subscriptions: SubscriptionsView,
  calendar: CalendarView,
  statistics: StatisticsView,
  settings: SettingsView,
};

const viewTitle = computed(() => NAV.find((n) => n.key === ui.view)?.title || "");
const showNewBtn = computed(() => ["subscriptions", "calendar"].includes(ui.view));
const currentPage = computed(() => PAGES[ui.view] || SubscriptionsView);

// ---------- 主题切换（循环：深色 → 浅色 → 系统 → 深色…）----------
const themeLabel = computed(() => THEME_LABELS[ui.theme] || "切换主题");

function cycleTheme() {
  const idx = THEMES.indexOf(ui.theme);
  const next = THEMES[(idx + 1) % THEMES.length];
  setTheme(next);
}

// ---------- 侧边栏折叠（持久化到 localStorage，SSR/异常环境安全降级）----------
const STORE_KEY = "sidebar-collapsed";

function readStoredCollapsed() {
  try {
    return localStorage.getItem(STORE_KEY) === "true";
  } catch {
    return false;
  }
}

function writeStoredCollapsed(v) {
  try {
    localStorage.setItem(STORE_KEY, String(v));
  } catch {
    /* SSR 或禁用存储时忽略 */
  }
}

const collapsed = ref(readStoredCollapsed());
watch(collapsed, writeStoredCollapsed);
const toggleLabel = computed(() => (collapsed.value ? "展开导航" : "收起导航"));

function switchView(key) {
  ui.view = key;
  ui.sidebarOpen = false; // 移动端选完即收起抽屉
}

// 「新增订阅」入口：弹窗位于订阅列表 Sub Page 内，先切到该页再触发
function createNew() {
  ui.view = "subscriptions";
  openNewSub();
}

// ---------- 浮动到期提醒 ----------
const notice = ref(null); // { list: [], collapsed: false, hidden: false }

async function loadNotice() {
  try {
    const result = await getUpcomingNotifications();
    const list = Array.isArray(result) ? result : [];
    if (!notice.value) {
      notice.value = { list, collapsed: false, hidden: false };
    } else {
      const hadNoNotices = notice.value.list.length === 0;
      notice.value.list = list;
      // 页面初次拿到提醒时自动展开；用户主动关闭后继续保持关闭状态。
      if (hadNoNotices && list.length) {
        notice.value.hidden = false;
        notice.value.collapsed = false;
      }
    }
  } catch (_) {
    /* 提醒加载失败静默 */
  }
}

function toggleNoticeCollapsed() {
  if (notice.value) notice.value.collapsed = !notice.value.collapsed;
}

function closeNotice() {
  if (notice.value) notice.value.hidden = true;
}

watch(() => ui.view, (v) => { if (v === "subscriptions") loadNotice(); });
onMounted(loadNotice);
</script>

<template>
  <div class="app">
    <!-- 侧边栏（固定在视口高度内，内部导航区独立滚动） -->
    <aside class="sidebar" :class="{ collapsed, open: ui.sidebarOpen }">
      <div class="brand">
        <img class="brand-logo" :src="logo" alt="订阅管理" />
        <span class="brand-name">订阅管理</span>
      </div>

      <nav class="nav">
        <button
          v-for="n in NAV"
          :key="n.key"
          class="nav-item"
          :class="{ active: ui.view === n.key }"
          :title="n.label"
          @click="switchView(n.key)"
        >
          <span class="nav-icon" aria-hidden="true">
            <svg v-if="n.key === 'subscriptions'" class="nav-item-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
              <path d="M170.666667 213.333333m-64 0a64 64 0 1 0 128 0 64 64 0 1 0-128 0Z" />
              <path d="M170.666667 512m-64 0a64 64 0 1 0 128 0 64 64 0 1 0-128 0Z" />
              <path d="M170.666667 810.666667m-64 0a64 64 0 1 0 128 0 64 64 0 1 0-128 0Z" />
              <path d="M896 778.666667H362.666667c-17.066667 0-32 14.933333 32 32s14.933333 32 32 32h533.333333c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32zM362.666667 245.333333h533.333333c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32H362.666667c-17.066667 0-32 14.933333-32 32s14.933333 32 32 32zM896 480H362.666667c-17.066667 0-32 14.933333-32 32s14.933333 32 32 32h533.333333c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32z" />
            </svg>
            <svg v-else-if="n.key === 'calendar'" class="nav-item-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
              <path d="M853.333333 149.333333h-138.666666V106.666667c0-17.066667-14.933333-32-32-32s-32 14.933333-32 32v42.666666h-277.333334V106.666667c0-17.066667-14.933333-32-32-32s-32 14.933333-32 32v42.666666H170.666667c-40.533333 0-74.666667 34.133333-74.666667 74.666667v618.666667C96 883.2 130.133333 917.333333 170.666667 917.333333h682.666666c40.533333 0 74.666667-34.133333 74.666667-74.666666v-618.666667C928 183.466667 893.866667 149.333333 853.333333 149.333333zM170.666667 213.333333h138.666666v64c0 17.066667 14.933333 32 32 32s32-14.933333 32-32v-64h277.333334v64c0 17.066667 14.933333 32 32 32s32-14.933333 32-32v-64H853.333333c6.4 0 10.666667 4.266667 10.666667 10.666667v194.133333c-4.266667-2.133333-6.4-2.133333-10.666667-2.133333H170.666667c-4.266667 0-6.4 0-10.666667 2.133333v-194.133333c0-6.4 4.266667-10.666667 10.666667-10.666667z m682.666666 640H170.666667c-6.4 0-10.666667-4.266667-10.666667-10.666666V477.866667c4.266667 2.133333 6.4 2.133333 10.666667 2.133333h682.666666c4.266667 0 6.4 0 10.666667-2.133333v364.8c0 6.4-4.266667 10.666667-10.666667 10.666666z" />
              <path d="M384 608h-85.333333c-17.066667 0-32 14.933333-32 32s14.933333 32 32 32h85.333333c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32zM725.333333 608h-192c-17.066667 0-32 14.933333-32 32s14.933333 32 32 32h192c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32z" />
            </svg>
            <svg v-else-if="n.key === 'settings'" class="nav-item-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
              <path d="M904.533333 422.4l-85.333333-14.933333-17.066667-38.4 49.066667-70.4c14.933333-21.333333 12.8-49.066667-6.4-68.266667l-53.333333-53.333333c-19.2-19.2-46.933333-21.333333-68.266667-6.4l-70.4 49.066666-38.4-17.066666-14.933333-85.333334c-2.133333-23.466667-23.466667-42.666667-49.066667-42.666666h-74.666667c-25.6 0-46.933333 19.2-53.333333 44.8l-14.933333 85.333333-38.4 17.066667L296.533333 170.666667c-21.333333-14.933333-49.066667-12.8-68.266666 6.4l-53.333334 53.333333c-19.2 19.2-21.333333 46.933333-6.4 68.266667l49.066667 70.4-17.066667 38.4-85.333333 14.933333c-21.333333 4.266667-40.533333 25.6-40.533333 51.2v74.666667c0 25.6 19.2 46.933333 44.8 53.333333l85.333333 14.933333 17.066667 38.4L170.666667 727.466667c-14.933333 21.333333-12.8 49.066667 6.4 68.266666l53.333333 53.333334c19.2 19.2 46.933333 21.333333 68.266667 6.4l70.4-49.066667 38.4 17.066667 14.933333 85.333333c4.266667 25.6 25.6 44.8 53.333333 44.8h74.666667c25.6 0 46.933333-19.2 53.333333-44.8l14.933334-85.333333 38.4-17.066667 70.4 49.066667c21.333333 14.933333 49.066667 12.8 68.266666-6.4l53.333334-53.333334c19.2-19.2 21.333333-46.933333 6.4-68.266666l-49.066667-70.4 17.066667-38.4 85.333333-14.933334c25.6-4.266667 44.8-25.6 44.8-53.333333v-74.666667c-4.266667-27.733333-23.466667-49.066667-49.066667-53.333333z m-19.2 117.333333l-93.866666 17.066667c-10.666667 2.133333-19.2 8.533333-23.466667 19.2l-29.866667 70.4c-4.266667 10.666667-2.133333 21.333333 4.266667 29.866667l53.333333 76.8-40.533333 40.533333-76.8-53.333333c-8.533333-6.4-21.333333-8.533333-29.866667-4.266667L576 768c-10.666667 4.266667-17.066667 12.8-19.2 23.466667l-17.066667 93.866666h-57.6l-17.066666-93.866666c-2.133333-10.666667-8.533333-19.2-19.2-23.466667l-70.4-29.866667c-10.666667-4.266667-21.333333-2.133333-29.866667 4.266667l-76.8 53.333333-40.533333-40.533333 53.333333-76.8c6.4-8.533333 8.533333-21.333333 4.266667-29.866667L256 576c-4.266667-10.666667-12.8-17.066667-23.466667-19.2l-93.866666-17.066667v-57.6l93.866666-17.066666c10.666667-2.133333 19.2-8.533333 23.466667-19.2l29.866667-70.4c4.266667-10.666667 2.133333-21.333333-4.266667-29.866667l-53.333333-76.8 40.533333-40.533333 76.8 53.333333c8.533333 6.4 21.333333 8.533333 29.866667 4.266667L448 256c10.666667-4.266667 17.066667-12.8 19.2-23.466667l17.066667-93.866666h57.6l17.066666 93.866666c2.133333 10.666667 8.533333 19.2 19.2 23.466667l70.4 29.866667c10.666667 4.266667 21.333333 2.133333 29.866667-4.266667l76.8-53.333333 40.533333 40.533333-53.333333 76.8c-6.4 8.533333-8.533333 21.333333-4.266667 29.866667L768 448c4.266667 10.666667 12.8 17.066667 23.466667 19.2l93.866666 17.066667v55.466666z" />
              <path d="M512 394.666667c-64 0-117.333333 53.333333-117.333333 117.333333s53.333333 117.333333 117.333333 117.333333 117.333333-53.333333 117.333333-117.333333-53.333333-117.333333-117.333333-117.333333z m0 170.666666c-29.866667 0-53.333333-23.466667-53.333333-53.333333s23.466667-53.333333 53.333333-53.333333 53.333333 23.466667 53.333333 53.333333-23.466667 53.333333-53.333333 53.333333z" />
            </svg>
            <svg v-else-if="n.key === 'statistics'" class="nav-item-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
              <path d="M874.666667 864H170.666667c-6.4 0-10.666667-4.266667-10.666667-10.666667V149.333333c0-17.066667-14.933333-32-32-32S96 132.266667 96 149.333333v704c0 40.533333 34.133333 74.666667 74.666667 74.666667h704c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32z" />
              <path d="M437.333333 469.333333v320c0 17.066667 14.933333 32 32 32s32-14.933333 32-32V469.333333c0-17.066667-14.933333-32-32-32s-32 14.933333-32 32zM298.666667 821.333333c17.066667 0 32-14.933333 32-32V533.333333c0-17.066667-14.933333-32-32-32s-32 14.933333-32 32v256c0 17.066667 14.933333 32 32 32zM640 565.333333c-17.066667 0-32 14.933333-32 32v192c0 17.066667 14.933333 32 32 32s32-14.933333 32-32v-192c0-17.066667-14.933333-32-32-32zM810.666667 352c-17.066667 0-32 14.933333-32 32v405.333333c0 17.066667 14.933333 32 32 32s32-14.933333 32-32V384c0-17.066667-14.933333-32-32-32zM322.133333 407.466667l147.2-147.2 147.2 147.2c6.4 6.4 14.933333 8.533333 23.466667 8.533333h2.133333c8.533333 0 17.066667-6.4 23.466667-12.8l170.666667-234.666667c10.666667-14.933333 6.4-34.133333-6.4-44.8-14.933333-10.666667-34.133333-6.4-44.8 6.4l-149.333334 204.8L490.666667 189.866667c-12.8-12.8-32-12.8-44.8 0l-170.666667 170.666666c-12.8 12.8-12.8 32 0 44.8 12.8 12.8 34.133333 12.8 46.933333 2.133334z" />
            </svg>
            <template v-else>{{ n.icon }}</template>
          </span>
          <span class="nav-label">{{ n.label }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button
          class="sidebar-toggle"
          type="button"
          :aria-label="toggleLabel"
          :title="toggleLabel"
          @click="collapsed = !collapsed"
        >
          <svg class="toggle-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
          <span class="toggle-label">{{ toggleLabel }}</span>
        </button>
      </div>
    </aside>
    <div class="sidebar-overlay" :class="{ open: ui.sidebarOpen }" @click="ui.sidebarOpen = false"></div>

    <!-- 主区域：顶栏 + Sub Page -->
    <main class="main">
      <header class="topbar">
        <button class="hamburger" aria-label="打开菜单" @click="ui.sidebarOpen = !ui.sidebarOpen">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </button>
        <h1>{{ viewTitle }}</h1>
        <div class="topbar-actions">
          <button
            class="theme-toggle"
            :title="themeLabel"
            :aria-label="themeLabel"
            @click="cycleTheme"
          >
            <svg
              class="theme-toggle-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path v-for="(d, i) in THEME_ICONS[ui.theme] || THEME_ICONS.dark" :key="i" :d="d" />
            </svg>
          </button>
        </div>
      </header>

      <!-- Sub Page 容器：切换导航即切换这里渲染的页面；内部滚动，不带动顶栏/侧边栏 -->
      <div class="page-host">
        <keep-alive>
          <component :is="currentPage" />
        </keep-alive>
      </div>
    </main>
  </div>

  <!-- 右下角浮动「新增订阅」按钮（替代原侧边栏新增按钮，订阅列表/日历页可见） -->
  <button
    v-if="showNewBtn"
    class="fab-add"
    type="button"
    aria-label="新增订阅"
    title="新增订阅"
    @click="createNew()"
  >
    <span class="fab-icon" aria-hidden="true">+</span>
  </button>

  <!-- 浮动提醒：支持缩小动画，可收起为图标或直接关闭 -->
  <section
    v-if="notice?.list.length && !notice.hidden"
    class="notice-float"
    aria-label="到期提醒"
  >
    <!-- 单一 Transition + mode=out-in 确保打开/收起时不会同时出现两个动画 -->
    <Transition name="notice-switch" mode="out-in" appear>
      <button
        v-if="notice.collapsed"
        key="notice-bubble"
        type="button"
        class="notice-float-toggle"
        title="展开到期提醒"
        aria-label="展开到期提醒"
        aria-expanded="false"
        @click="toggleNoticeCollapsed"
      >
        <svg class="notice-float-bell" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span class="notice-float-count">{{ notice.list.length }}</span>
      </button>
      <div v-else key="notice-panel" class="notice-float-panel" role="status" aria-live="polite">
        <div class="notice-float-head">
          <div class="notice-float-title">
            <svg class="notice-float-bell" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <strong>到期提醒</strong>
            <span class="notice-float-count notice-float-count--inline">{{ notice.list.length }}</span>
          </div>
          <div class="notice-float-actions">
            <button
              type="button"
              class="notice-float-action"
              title="收起提醒"
              aria-label="收起到期提醒"
              @click="toggleNoticeCollapsed"
            >
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
              </svg>
            </button>
            <button
              type="button"
              class="notice-float-action"
              title="关闭提醒"
              aria-label="关闭到期提醒"
              @click="closeNotice"
            >
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
              </svg>
            </button>
          </div>
        </div>
        <ul class="notice-float-list">
          <li v-for="n in notice.list" :key="n.id" class="notice-float-item">
            <strong>{{ n.title }}</strong>
            <span>{{ n.body }}</span>
          </li>
        </ul>
      </div>
    </Transition>
  </section>

  <!-- Toast -->
  <div v-if="toastState.visible" class="toast" :class="toastState.type">{{ toastState.msg }}</div>
</template>

<style scoped>
/* 顶栏主题切换按钮 */
.theme-toggle {
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  background: var(--card-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 图标描边颜色与侧边栏导航图标（订阅列表）一致，暗色模式下清晰可见 */
  color: var(--muted);
  transition: all 0.15s ease;
}
.theme-toggle:hover {
  color: var(--text);
}
.theme-toggle-icon {
  width: 18px;
  height: 18px;
}

.theme-toggle:hover {
  border-color: var(--primary);
  background: var(--card);
}

.theme-toggle:active {
  transform: scale(0.95);
}

/* ---------- 右下角浮动「新增订阅」按钮 (FAB) ---------- */
.fab-add {
  display: flex;
  align-items: center;
  justify-content: center;
  position: fixed;
  right: clamp(16px, 4vw, 24px);
  bottom: clamp(80px, 12vw, 100px);
  width: 56px;
  height: 56px;
  border: none;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
  z-index: 29;
  transition: background 0.15s ease, transform 0.15s ease;
}

.fab-add:hover {
  background: var(--primary-2);
}

.fab-add:active {
  transform: scale(0.94);
}

/* 订阅列表侧边栏 SVG 图标 */
.nav-item-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}
</style>