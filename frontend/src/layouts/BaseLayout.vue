<script setup>
// 公共页面壳（BasePage）：
//   侧边栏（导航 / 新增按钮 / 折叠按钮）+ 顶栏 + 浮动到期提醒 + 主区（Sub Page 插槽）+ Toast
//   切换导航 = 切换本壳下的 Sub Page（keep-alive 保留各页状态）
import { computed, ref, watch, onMounted } from "vue";
import { ui, toastState, toast, openNewSub, setTheme } from "../ui.js";
import { getUpcomingNotifications } from "../api.js";
import logo from "../assets/icon_64.png";
import SubscriptionsView from "../views/SubscriptionsView.vue";
import CalendarView from "../views/CalendarView.vue";
import StatisticsView from "../views/StatisticsView.vue";
import SettingsView from "../views/SettingsView.vue";

const THEMES = ["dark", "light", "system"];
const THEME_ICONS = { dark: "🌙", light: "☀️", system: "💻" };
const THEME_LABELS = { dark: "深色模式", light: "浅色模式", system: "跟随系统" };

const NAV = [
  { key: "subscriptions", icon: "📋", label: "订阅列表", title: "订阅列表" },
  { key: "calendar", icon: "📅", label: "日历", title: "日历" },
  { key: "statistics", icon: "📊", label: "统计", title: "统计" },
  { key: "settings", icon: "⚙️", label: "设置", title: "设置" },
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
const themeIcon = computed(() => THEME_ICONS[ui.theme] || "🌙");
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
          <span class="nav-icon" aria-hidden="true">{{ n.icon }}</span>
          <span class="nav-label">{{ n.label }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button v-if="showNewBtn" class="btn btn-primary btn-block btn-new-sub" title="新增订阅" @click="createNew()">
          <span class="btn-icon">+</span>
          <span class="btn-label">新增订阅</span>
        </button>
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
            {{ themeIcon }}
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
  transition: all 0.15s ease;
}

.theme-toggle:hover {
  border-color: var(--primary);
  background: var(--card);
}

.theme-toggle:active {
  transform: scale(0.95);
}
</style>