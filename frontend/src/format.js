/** 展示格式化工具（移植自 vanilla 版 app.js） */

export const CURRENCY_SYMBOL = { CNY: "¥", USD: "$", HKD: "HK$" };
export const PERIOD_LABEL = {
  month: "月付", quarter: "季付", year: "年付", once: "一次性", custom: "自定义",
};
export const CUSTOM_UNIT_LABEL = { day: "天", week: "周", month: "月", year: "年" };

export function fmtCents(cents, currency) {
  const sym = CURRENCY_SYMBOL[currency];
  if (sym) {
    return `${sym}${(cents / 100).toFixed(2)}`;
  }
  return `${currency || "CNY"} ${(cents / 100).toFixed(2)}`;
}

export function daysLeft(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

/** 元 → 分（后端 amount 以整数分存储） */
export function yuanToCents(v) {
  return Math.round((parseFloat(v) || 0) * 100);
}
export function centsToYuan(c) {
  return (Number(c) / 100).toFixed(2);
}

export function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}