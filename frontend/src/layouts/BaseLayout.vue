<script setup>
// 公共页面壳（BasePage）：
//   侧边栏（导航 / 新增按钮 / 折叠按钮）+ 顶栏 + 浮动到期提醒 + 主区（Sub Page 插槽）+ Toast
//   切换导航 = 切换本壳下的 Sub Page（keep-alive 保留各页状态）
import { computed, ref, watch, onMounted } from "vue";
import { ui, toastState, removeToast, openNewSub, setTheme } from "../utils/ui.js";
import { getUpcomingNotifications } from "../services/api.js";

import Sidebar from "../components/Sidebar.vue";
import HeadlessToast from "../components/HeadlessToast.vue";
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
    <!-- 侧边栏（基于 Headless UI 重写，支持移动端抽屉与桌面端折叠） -->
    <Sidebar
      :nav="NAV"
      :current-view="ui.view"
      v-model:open="ui.sidebarOpen"
      @navigate="switchView"
    />

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
        <!-- out-in：先退场再入场，避免两页重叠导致高度跳动；过渡类见 styles/main.css -->
        <Transition name="page" mode="out-in">
          <keep-alive>
            <component :is="currentPage" />
          </keep-alive>
        </Transition>
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

  <!-- Toast：堆叠容器 + HeadlessToast（自带进出动画，退场由 removeToast 两阶段处理） -->
  <div v-if="toastState.items.length" class="toast-stack" aria-live="polite" aria-atomic="false">
    <HeadlessToast
      v-for="item in toastState.items"
      :key="item.id"
      :show="item.show"
      :type="item.type === 'ok' ? 'success' : 'error'"
      :message="item.msg"
      :duration="0"
      @close="removeToast(item.id)"
    />
  </div>
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
  transition: all var(--dur-fast) ease;
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
  bottom: calc(clamp(80px, 12vw, 100px) + env(safe-area-inset-bottom, 0px));
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
  transition: background var(--dur-fast) ease, transform var(--dur-fast) ease;
}

.fab-add:hover {
  background: var(--primary-2);
}

.fab-add:active {
  transform: scale(0.94);
}

/* 窄屏：内容会从浮动按钮下方滚过，稍微降低不透明度以免完全挡住卡片文字 */
@media (max-width: 860px) {
  .fab-add {
    opacity: 0.88;
  }
  .fab-add:hover,
  .fab-add:active {
    opacity: 1;
  }
}

/* 订阅列表侧边栏 SVG 图标 */
.nav-item-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}
</style>