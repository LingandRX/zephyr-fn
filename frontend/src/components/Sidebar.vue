<script setup>
/**
 * Sidebar 侧边栏组件（基于 @headlessui/vue 重写）：
 * 1. 移动端抽屉：基于 Headless UI 的 Dialog / DialogPanel / DialogTitle / TransitionRoot / TransitionChild 实现
 *    - 具备完整的可访问性（role="dialog"、aria-modal、焦点锁定、ESC 退出、背景遮罩点击退出）
 *    - 平滑的入场与离场过渡动画（背景淡入淡出、面板滑入滑出）
 *    - 移动端专有头部与关闭按钮
 * 2. 桌面端侧边栏：静态 aside，支持宽度折叠（220px <-> 64px）
 *    - 状态持久化到 localStorage
 *    - 折叠时图标居中、标签以动画收缩
 *    - 底部折叠切换按钮
 */
import { computed, ref, watch } from "vue";
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  TransitionRoot,
  TransitionChild,
} from "@headlessui/vue";
import { ui } from "../utils/ui.js";
import logo from "../assets/icon_64.png";

const props = defineProps({
  open: {
    type: Boolean,
    default: undefined,
  },
  currentView: {
    type: String,
    default: undefined,
  },
  nav: {
    type: Array,
    default: () => [],
  },
  collapsed: {
    type: Boolean,
    default: undefined,
  },
});

const emit = defineEmits([
  "update:open",
  "update:currentView",
  "update:collapsed",
  "navigate",
]);

const DEFAULT_NAV = [
  { key: "subscriptions", icon: "list", label: "订阅", title: "订阅" },
  { key: "calendar", icon: "calendar", label: "日历", title: "日历" },
  { key: "statistics", icon: "statistics", label: "统计", title: "统计" },
  { key: "settings", icon: "settings", label: "设置", title: "设置" },
];

const navItems = computed(() => (props.nav && props.nav.length > 0 ? props.nav : DEFAULT_NAV));

const activeView = computed(() => {
  if (props.currentView !== undefined) return props.currentView;
  return ui.view || "subscriptions";
});

const isMobileOpen = computed({
  get: () => (props.open !== undefined ? props.open : ui.sidebarOpen),
  set: (val) => {
    emit("update:open", val);
    ui.sidebarOpen = val;
  },
});

// ---------- 侧边栏折叠（持久化到 localStorage） ----------
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
  } catch {}
}

const internalCollapsed = ref(readStoredCollapsed());

watch(
  () => props.collapsed,
  (val) => {
    if (val !== undefined) internalCollapsed.value = val;
  }
);

const isCollapsed = computed({
  get: () => (props.collapsed !== undefined ? props.collapsed : internalCollapsed.value),
  set: (val) => {
    internalCollapsed.value = val;
    writeStoredCollapsed(val);
    emit("update:collapsed", val);
    ui.sidebarCollapsed = val;
  },
});

const toggleLabel = computed(() => (isCollapsed.value ? "展开导航" : "收起导航"));

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value;
}

function handleNavClick(key) {
  emit("update:currentView", key);
  emit("navigate", key);
  ui.view = key;
  closeMobile();
}

function closeMobile() {
  isMobileOpen.value = false;
}
</script>

<template>
  <!-- 移动端抽屉：基于 Headless UI Dialog + Transition -->
  <TransitionRoot :show="isMobileOpen" as="template">
    <Dialog as="div" class="sidebar-dialog-root" @close="closeMobile">
      <!-- 遮罩背景过渡 -->
      <TransitionChild
        as="template"
        enter="sidebar-backdrop-enter"
        enter-from="sidebar-backdrop-from"
        enter-to="sidebar-backdrop-to"
        leave="sidebar-backdrop-leave"
        leave-from="sidebar-backdrop-to"
        leave-to="sidebar-backdrop-from"
      >
        <div class="sidebar-dialog-backdrop" aria-hidden="true" />
      </TransitionChild>

      <!-- 抽屉容器与面板 -->
      <div class="sidebar-dialog-container">
        <TransitionChild
          as="template"
          enter="sidebar-panel-enter"
          enter-from="sidebar-panel-from"
          enter-to="sidebar-panel-to"
          leave="sidebar-panel-leave"
          leave-from="sidebar-panel-to"
          leave-to="sidebar-panel-from"
        >
          <DialogPanel class="sidebar mobile-sidebar">
            <div class="sidebar-mobile-header">
              <div class="brand">
                <img class="brand-logo" :src="logo" alt="订阅管理" />
                <DialogTitle as="span" class="brand-name">订阅管理</DialogTitle>
              </div>
              <button
                type="button"
                class="sidebar-mobile-close"
                aria-label="关闭侧边栏"
                title="关闭"
                @click="closeMobile"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>

            <nav class="nav" aria-label="移动端主导航">
              <button
                v-for="n in navItems"
                :key="n.key"
                class="nav-item"
                :class="{ active: activeView === n.key }"
                :title="n.label"
                @click="handleNavClick(n.key)"
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
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>

  <!-- 桌面端侧边栏（固定视口高度，内部导航滚动，底部支持折叠切换） -->
  <aside class="sidebar desktop-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="brand">
      <img class="brand-logo" :src="logo" alt="订阅管理" />
      <span class="brand-name">订阅管理</span>
    </div>

    <nav class="nav" aria-label="桌面端主导航">
      <button
        v-for="n in navItems"
        :key="n.key"
        class="nav-item"
        :class="{ active: activeView === n.key }"
        :title="n.label"
        @click="handleNavClick(n.key)"
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
        @click="toggleCollapse"
      >
        <svg class="toggle-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
        <span class="toggle-label">{{ toggleLabel }}</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
/* 导航图标规范 */
.nav-item-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* 移动端专有头部与关闭按钮 */
.sidebar-mobile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.sidebar-mobile-header .brand {
  flex: 1;
  padding: var(--space-1) 0 18px;
}

.sidebar-mobile-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--card-2);
  color: var(--muted);
  cursor: pointer;
  margin-bottom: 18px;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.sidebar-mobile-close:hover {
  background: var(--card);
  color: var(--text);
  border-color: var(--primary);
}

.sidebar-mobile-close:active {
  transform: scale(0.95);
}

/* =====================================================================
 * iOS 风格侧边栏（桌面 aside + 移动抽屉共用导航样式）
 * 覆盖 styles/main.css 里的全局 .sidebar/.nav-item 规则
 * ===================================================================== */

/* 外壳：iOS 分组底色 + 发丝分隔线 */
.desktop-sidebar {
  background: var(--card-2);
  border-right: 1px solid var(--ios-separator);
}

/* 品牌区 */
.brand-logo {
  border-radius: 10px;
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.2px;
}

/* 导航行：iOS 列表行 */
.nav {
  gap: 2px;
}
.nav-item {
  height: 42px;
  padding: 0 12px;
  gap: 12px;
  border-radius: 10px;
  color: var(--ios-gray);
  font-size: var(--fs-sm);
  font-weight: 500;
  transition: background-color 0.15s ease, color 0.15s ease;
}
.nav-item:hover {
  background: var(--ios-fill);
  color: var(--text);
}
.nav-item.active {
  background: var(--ios-blue-soft);
  color: var(--ios-blue);
  font-weight: 600;
}
/* 去掉原左侧竖条指示器（非 iOS 习惯，选中态靠底色 + 蓝色文字） */
.nav-item.active::before {
  display: none;
}
.nav-icon {
  width: 22px;
}
.nav-item-icon {
  width: 20px;
  height: 20px;
}

/* 底部折叠按钮 */
.sidebar-footer {
  border-top: 1px solid var(--ios-separator);
  padding-top: 10px;
}
.sidebar-toggle {
  height: 40px;
  padding: 0 12px;
  gap: 12px;
  border: none;
  border-radius: 10px;
  color: var(--ios-gray);
  font-size: var(--fs-sm);
  font-weight: 500;
}
.sidebar-toggle:hover {
  background: var(--ios-fill);
  color: var(--text);
}
.sidebar-toggle:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

/* 折叠态：图标居中 */
.desktop-sidebar.collapsed .nav-item,
.desktop-sidebar.collapsed .sidebar-toggle {
  padding: 0;
}

/* 移动抽屉：同一套底色 + 圆形关闭按钮 */
:global(.mobile-sidebar) {
  background: var(--card-2);
  border-right: 1px solid var(--ios-separator);
}
.sidebar-mobile-close {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: var(--ios-fill);
  color: var(--ios-gray);
}
.sidebar-mobile-close:hover {
  background: var(--ios-separator);
  color: var(--text);
  border-color: transparent;
}
.sidebar-mobile-close:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

/* ---------- Headless UI Dialog 移动端样式（Teleport 到 body） ---------- */
:global(.sidebar-dialog-root) {
  position: fixed;
  inset: 0;
  z-index: var(--z-sidebar);
  overflow: hidden;
}

:global(.sidebar-dialog-backdrop) {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  z-index: var(--z-sidebar);
}

:global(.sidebar-dialog-container) {
  position: fixed;
  inset: 0;
  display: flex;
  z-index: var(--z-sidebar);
  pointer-events: none;
}

:global(.mobile-sidebar) {
  pointer-events: auto;
  position: relative;
  width: 250px;
  max-width: 85vw;
  height: 100vh;
  height: 100dvh;
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  box-shadow: var(--shadow-drawer);
  display: flex;
  flex-direction: column;
  padding: var(--space-4) var(--space-3);
  user-select: none;
  transform: translateX(0);
}

/* ---------- Headless UI 过渡动画类 ---------- */
:global(.sidebar-backdrop-enter) {
  transition: opacity 0.25s ease-out;
}
:global(.sidebar-backdrop-from) {
  opacity: 0;
}
:global(.sidebar-backdrop-to) {
  opacity: 1;
}
:global(.sidebar-backdrop-leave) {
  transition: opacity 0.2s ease-in;
}

:global(.sidebar-panel-enter) {
  transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
}
:global(.sidebar-panel-from) {
  transform: translateX(-100%);
}
:global(.sidebar-panel-to) {
  transform: translateX(0);
}
:global(.sidebar-panel-leave) {
  transition: transform 0.22s cubic-bezier(0.4, 0, 1, 1);
}

/* 桌面视口下强制隐藏移动端 Dialog（防止屏幕尺寸变化瞬态残留） */
@media (min-width: 861px) {
  :global(.sidebar-dialog-root) {
    display: none !important;
  }
}

/* 移动端下隐藏桌面端 aside */
@media (max-width: 860px) {
  .desktop-sidebar {
    display: none !important;
  }
}
</style>
