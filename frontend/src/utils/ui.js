/** 轻量全局状态与 UI 交互工具：视图切换 / toast / 主题管理 */
import { reactive } from "vue";

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

export function toggleTheme() {
  const themes = ["dark", "light", "system"];
  const idx = themes.indexOf(ui.theme);
  setTheme(themes[(idx + 1) % themes.length]);
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

export const ui = reactive({
  view: "subscriptions",
  showAddModal: false,
  sidebarOpen: false,
  sidebarCollapsed: false,
  theme: loadTheme(),
});

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
