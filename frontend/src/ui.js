/** 轻量全局状态：视图切换 / toast / 跨组件事件（无需引入状态库） */
import { reactive } from "vue";

export const ui = reactive({
  view: "subscriptions",
  nextComponent: 0, // 触发「新增订阅」弹窗
  sidebarOpen: false, // 移动端抽屉
  sidebarCollapsed: false, // 桌面端折叠
});

export function openNewSub() {
  ui.nextComponent += 1;
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