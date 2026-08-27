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
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
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
  } catch {}
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

export const toastState = reactive({ msg: "", type: "ok", visible: false });

let _t = null;
export function toast(msg, type = "ok") {
  toastState.msg = msg;
  toastState.type = type;
  toastState.visible = true;
  clearTimeout(_t);
  _t = setTimeout(() => { toastState.visible = false; }, 2600);
}
