/**
 * 后端 API 封装（对齐 fnOS 统一网关约定）
 *
 * - dev：页面在根路径，API 走 /api（Vite proxy → 127.0.0.1:5001）
 * - prod：页面在 /app/subscription/，API 走 /app/subscription/api（网关转发，后端剥离前缀）
 * - 绝不携带用户身份：身份由网关注入 X-Trim-* Header，后端统一取用
 * - 统一响应信封 {code, message, data}：code === 0 视为成功，本层自动解包出 data；
 *   非 0 或 HTTP 错误统一抛 Error(message)
 */

export const API_BASE = import.meta.env.DEV ? "/api" : "/app/subscription/api";

export async function api(path, options = {}) {
  const opts = {
    method: options.method || "GET",
    headers: options.headers || {},
  };
  if (options.body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(options.body);
  } else if (options.text !== undefined) {
    opts.body = options.text;
  }
  const res = await fetch(API_BASE + path, opts);
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("json")) {
    let d;
    try {
      d = await res.json();
    } catch (_) {
      throw new Error(`请求失败 (${res.status})`);
    }
    // 信封协议：code === 0 成功；否则把 message 作为异常抛出
    if (d && typeof d === "object" && "code" in d) {
      if (d.code === 0) return d.data;
      throw new Error(d.message || `请求失败 (${res.status})`);
    }
    if (!res.ok) {
      throw new Error(d.error || `请求失败 (${res.status})`);
    }
    return d;
  }
  if (!res.ok) {
    throw new Error(`请求失败 (${res.status})`);
  }
  return res.text();
}

/** 直接下载端点（导出 JSON/CSV）：与页面同源，浏览器导航即可触发下载 */
export function exportUrl(path) {
  return API_BASE + path;
}
export function download(path, filename) {
  const a = document.createElement("a");
  a.href = exportUrl(path);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ---------- 订阅 ----------
export const getSubscriptions = () => api("/subscriptions");
export const createSubscription = (body) =>
  api("/subscriptions", { method: "POST", body });
export const updateSubscription = (id, body) =>
  api(`/subscriptions/${id}`, { method: "PUT", body });
export const deleteSubscription = (id) =>
  api(`/subscriptions/${id}`, { method: "DELETE" });
export const renewSubscription = (id) =>
  api(`/subscriptions/${id}/renew`, { method: "POST" });

// ---------- 分类 ----------
export const getCategories = () => api("/categories");
export const createCategory = (body) =>
  api("/categories", { method: "POST", body });
export const deleteCategory = (id) =>
  api(`/categories/${id}`, { method: "DELETE" });

// ---------- 统计 / 日历 / 设置 / 提醒 ----------
export const getStatistics = (mode = "nominal") =>
  api(`/statistics?mode=${mode}`);
export const getCalendar = (year, month) =>
  api(`/calendar?year=${year}&month=${month}`);
export const getSettings = () => api("/settings");
export const saveSettings = (body) => api("/settings", { method: "PUT", body });
export const getUpcomingNotifications = () => api("/notifications/upcoming");
export const testEmailNotification = (body) =>
  api("/notifications/test-email", { method: "POST", body });
export const testPushPlusNotification = (body) =>
  api("/notifications/test-pushplus", { method: "POST", body });

// ---------- 日志 ----------
export const getLogTail = (lines = 200) => api(`/logs/tail?lines=${lines}`);

// ---------- 备份 / 导入导出 ----------
export const backupNow = () => api("/backup", { method: "POST" });
export const getBackupFiles = () => api("/backup/files");
export const deleteBackupFile = (name) =>
  api(`/backup/files?name=${encodeURIComponent(name)}`, { method: "DELETE" });
/** 下载备份文件：浏览器导航触发下载 */
export function downloadBackupFile(name) {
  download(`/backup/files/download?name=${encodeURIComponent(name)}`, name);
}
export const importJson = (text) =>
  api("/backup/import-json", {
    method: "POST",
    text,
    headers: { "Content-Type": "application/json" },
  });
export const importCsv = (text) =>
  api("/backup/import-csv", {
    method: "POST",
    text,
    headers: { "Content-Type": "text/csv" },
  });
