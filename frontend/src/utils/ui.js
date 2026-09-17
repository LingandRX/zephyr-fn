/** 轻量全局状态与 UI 交互工具：Hash 路由 / toast / 主题管理 */
import { reactive, watch } from "vue";

// ========== 主题管理 ==========
const THEME_KEY = "theme";

function loadTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "light";
  } catch {
    return "light";
  }
}

function getSystemTheme() {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (theme === "system") {
    root.dataset.theme = getSystemTheme();
  } else {
    root.dataset.theme = theme;
  }
}

export function setTheme(theme) {
  ui.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // ignore localStorage errors
  }
  applyTheme(theme);
}

// 初始化主题
applyTheme(loadTheme());

// 监听系统主题变化
if (typeof window !== "undefined") {
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (ui.theme === "system") applyTheme("system");
    });
}

// ========== 轻量 Hash 路由管理 ==========
export const VALID_VIEWS = ["subscriptions", "calendar", "statistics", "settings"];
export const DEFAULT_VIEW = "subscriptions";

/**
 * 从 URL Hash 解析视图名称。
 * 支持 "#/calendar"、"#/statistics"、"#calendar"、"#/calendar/"、"#/calendar?..." 等格式。
 * 空 hash 或未知视图统一回退到 DEFAULT_VIEW。
 */
export function getViewFromHash(hash = (typeof window !== "undefined" ? window.location.hash : "")) {
  if (!hash) return DEFAULT_VIEW;
  const clean = String(hash)
    .replace(/^#\/?/, "")
    .split("?")[0]
    .replace(/\/+$/, "")
    .trim();
  return VALID_VIEWS.includes(clean) ? clean : DEFAULT_VIEW;
}

/**
 * 根据视图名称生成对应的标准 Hash 字符串（例如 "calendar" -> "#/calendar"）
 */
export function getHashForView(view) {
  const target = VALID_VIEWS.includes(view) ? view : DEFAULT_VIEW;
  return `#/${target}`;
}

export const ui = reactive({
  view: typeof window !== "undefined" ? getViewFromHash() : DEFAULT_VIEW,
  showAddModal: false,
  sidebarOpen: false,
  sidebarCollapsed: false,
  theme: loadTheme(),
});

/**
 * 编程式跳转到指定视图
 */
export function navigateTo(view) {
  const target = VALID_VIEWS.includes(view) ? view : DEFAULT_VIEW;
  ui.view = target;
}

// 监听浏览器 hashchange 事件（前进/后退、手动修改 URL、锚点点击）
function syncViewFromHash() {
  if (typeof window === "undefined") return;
  const targetView = getViewFromHash(window.location.hash);
  if (ui.view !== targetView) {
    ui.view = targetView;
  }
  if (ui.sidebarOpen) {
    ui.sidebarOpen = false;
  }
  // 规范化 Hash（若输入 "#calendar" 或非法路由，静默矫正为标准 "#/..."，不生成多余历史条目）
  const canonicalHash = getHashForView(targetView);
  if (window.location.hash !== canonicalHash) {
    try {
      history.replaceState(null, "", canonicalHash);
    } catch {
      window.location.hash = canonicalHash;
    }
  }
}

// 监听 ui.view 状态变化（应用内部点击侧边栏、新增按钮等触发路由同步）
watch(
  () => ui.view,
  (newView) => {
    if (typeof window === "undefined") return;
    const targetView = VALID_VIEWS.includes(newView) ? newView : DEFAULT_VIEW;
    if (ui.view !== targetView) {
      ui.view = targetView;
      return;
    }
    const targetHash = getHashForView(targetView);
    if (window.location.hash !== targetHash) {
      window.location.hash = targetHash;
    }
  }
);

// 初始化 Hash 监听与首次规范化（实现页面刷新保活）
if (typeof window !== "undefined") {
  window.addEventListener("hashchange", syncViewFromHash);

  const initialHash = getHashForView(ui.view);
  if (window.location.hash !== initialHash) {
    try {
      history.replaceState(null, "", initialHash);
    } catch {
      window.location.hash = initialHash;
    }
  }
}

export function openNewSub() {
  ui.showAddModal = true;
}

export const toastState = reactive({ items: [] });

/** 显示时长：到点后开始退场 */
const TOAST_VISIBLE_MS = 2300;
/** 退场动画等待时长：须略大于 HeadlessToast 的 leave transition（--dur-base = 0.2s） */
const TOAST_LEAVE_MS = 280;

/**
 * 关闭一条 Toast。
 * 采用两阶段移除：先把 show 置 false 触发退场动画，动画结束后再从列表摘除，
 * 否则元素被立即销毁、退场动画不会播放。
 */
export function removeToast(id) {
  const item = toastState.items.find((it) => it.id === id);
  if (!item || item.show === false) return;
  item.show = false;
  setTimeout(() => {
    const index = toastState.items.findIndex((it) => it.id === id);
    if (index >= 0) {
      toastState.items.splice(index, 1);
    }
  }, TOAST_LEAVE_MS);
}

export function toast(msg, type = "ok") {
  const item = {
    id: Date.now() + Math.random(),
    msg,
    type,
    show: true, // 由 HeadlessToast 消费；退场时置 false
  };

  toastState.items.push(item);
  setTimeout(() => removeToast(item.id), TOAST_VISIBLE_MS);
}
