/* 订阅管理前端 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const CURRENCY_SYMBOL = { CNY: "¥", USD: "$", HKD: "HK$" };
const PERIOD_LABEL = { month: "月付", quarter: "季付", year: "年付", once: "一次性", custom: "自定义" };

const state = {
  view: "subscriptions",
  subs: [],
  cats: [],
  settings: null,
  stats: null,
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth() + 1,
  noticeHidden: false,
};

/* ---------------- API ---------------- */

async function api(path, options = {}) {
  const opts = { method: options.method || "GET", headers: options.headers || {} };
  if (options.body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(options.body);
  }
  if (options.text !== undefined) {
    opts.body = options.text;
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`;
    try { const d = await res.json(); if (d.error) msg = d.error; } catch (_) {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

function toast(msg, type = "ok") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

function fmtCents(cents, currency) {
  const sym = CURRENCY_SYMBOL[currency] || "¥";
  return `${sym}${(cents / 100).toFixed(2)}`;
}

function daysLeft(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

/* ---------------- 数据加载 ---------------- */

async function loadAll() {
  const [subs, cats, settings, stats] = await Promise.all([
    api("api/subscriptions"),
    api("api/categories"),
    api("api/settings"),
    api("api/statistics?mode=nominal"),
  ]);
  state.subs = subs; state.cats = cats; state.settings = settings; state.stats = stats;
  render();
}

/* ---------------- 渲染 ---------------- */

function render() {
  renderNav();
  renderStatsCards();
  renderSubscriptions();
  renderFilters();
  renderCalendar();
  renderStatistics();
  renderSettings();
  renderNotice();
}

function renderNav() {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
  const titles = { subscriptions: "订阅列表", calendar: "日历", statistics: "统计", settings: "设置" };
  $("#view-title").textContent = titles[state.view];
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${state.view}`));
}

function renderStatsCards() {
  const s = state.stats; if (!s) return;
  const cur = s.currency;
  const cards = [
    ["本月支出", fmtCents(s.monthly_expense, cur), `实际到期 ${fmtCents(s.monthly_actual_expense, cur)}`],
    ["年支出", fmtCents(s.yearly_expense, cur), "按到期周期计"],
    ["未来 30 天", fmtCents(s.upcoming_30_days, cur), "即将扣费"],
    ["活跃订阅", `${s.active_count}`, "个"],
  ];
  $("#stats-cards").innerHTML = cards.map(([l, v, sub]) => `
    <div class="stat-card"><div class="label">${l}</div>
    <div class="value">${v}</div><div class="sub">${sub}</div></div>`).join("");
}

function renderFilters() {
  const catSel = $("#filter-category");
  const cur = catSel.value;
  catSel.innerHTML = `<option value="">全部分类</option>` +
    state.cats.map((c) => `<option value="${c.id}">${c.icon || ""} ${c.name}</option>`).join("");
  catSel.value = cur;
}

function renderSubscriptions() {
  const q = ($("#filter-search").value || "").toLowerCase();
  const cat = $("#filter-category").value;
  const st = $("#filter-status").value;
  const rows = state.subs.filter((s) => {
    if (q && !(s.name || "").toLowerCase().includes(q) && !((s.notes || "") + "").toLowerCase().includes(q)) return false;
    if (cat && s.category_id !== cat) return false;
    if (st && s.status !== st) return false;
    return true;
  });

  const tbody = $("#sub-tbody");
  $("#sub-empty").classList.toggle("hidden", rows.length > 0);
  tbody.innerHTML = rows.map((s) => {
    const catName = state.cats.find((c) => c.id === s.category_id);
    const dl = s.next_due_date ? daysLeft(s.next_due_date) : null;
    const dueHtml = dl === null ? '<span class="muted">—</span>'
      : dl < 0 ? `<span class="days-overdue">已过 ${-dl} 天</span>`
      : dl === 0 ? '<span class="days-soon">今天</span>'
      : dl <= 7 ? `<span class="days-soon">${dl} 天</span>` : `${dl} 天`;
    return `<tr>
      <td><div class="sub-name">${esc(s.name)}<small>${catName ? esc(catName.icon + " " + catName.name) : "未分类"}${s.notes ? " · " + esc(s.notes) : ""}</small></div></td>
      <td>${fmtCents(s.amount, s.currency)}<small class="muted" style="display:block">${s.actual_amount ? "实付 " + fmtCents(s.actual_amount, s.currency) : ""}</small></td>
      <td>${PERIOD_LABEL[s.period_type] || s.period_type}${s.custom_period_value ? ` (${s.custom_period_value}${s.custom_period_unit})` : ""}</td>
      <td>${s.next_due_date || "—"}</td>
      <td>${dueHtml}</td>
      <td><span class="badge" style="color:${s.status_color}">${s.status_label}</span></td>
      <td class="ta-r"><div class="row-actions">
        ${s.period_type !== "once" ? `<button data-act="renew" data-id="${s.id}" title="续费：推进到下一期">续费</button>` : ""}
        <button data-act="edit" data-id="${s.id}">编辑</button>
        <button data-act="del" data-id="${s.id}" class="danger">删除</button>
      </div></td></tr>`;
  }).join("");
}

function renderNotice() {
  const box = $("#notice-banner");
  if (state.noticeHidden) { box.classList.add("hidden"); return; }
  api("api/notifications/upcoming").then((list) => {
    if (!list.length) { box.classList.add("hidden"); return; }
    box.innerHTML = `<strong>⏰ 到期提醒</strong> <ul>` +
      list.map((n) => `<li>${esc(n.title)} — ${esc(n.body)}</li>`).join("") +
      `</ul><button class="btn btn-ghost" id="notice-close" style="margin-top:6px">知道了</button>`;
    box.classList.remove("hidden");
    $("#notice-close").onclick = () => { state.noticeHidden = true; box.classList.add("hidden"); };
  }).catch(() => {});
}

/* ---------------- 日历 ---------------- */

function renderCalendar() {
  $("#cal-title").textContent = `${state.calYear} 年 ${state.calMonth} 月`;
  const first = new Date(state.calYear, state.calMonth - 1, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(state.calYear, state.calMonth, 0).getDate();
  const prevDays = new Date(state.calYear, state.calMonth - 1, 0).getDate();

  api(`api/calendar?year=${state.calYear}&month=${state.calMonth}`).then((events) => {
    const byDate = {};
    events.forEach((e) => { (byDate[e.date] = byDate[e.date] || []).push(e); });
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const todayStr = today.toISOString().slice(0, 10);

    let html = ["日", "一", "二", "三", "四", "五", "六"].map((d) => `<div class="cal-dow">${d}</div>`).join("");
    for (let i = 0; i < startDow; i++) {
      const d = new Date(state.calYear, state.calMonth - 1, -startDow + i + 1);
      html += `<div class="cal-day other"><div class="num">${d.getDate()}</div></div>`;
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const ds = `${state.calYear}-${String(state.calMonth).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const evs = byDate[ds] || [];
      html += `<div class="cal-day ${ds === todayStr ? "today" : ""}">
        <div class="num">${day}</div>` +
        evs.slice(0, 3).map((e) => `<div class="cal-event ${e.event_type === "service_end" ? "end" : "due"}" title="${esc(e.name)} ${e.amount_formatted}">${esc(e.name)} ${e.amount_formatted}</div>`).join("") +
        (evs.length > 3 ? `<div class="cal-event muted">+${evs.length - 3}</div>` : "") +
        `</div>`;
    }
    const remaining = 42 - (startDow + daysInMonth);
    for (let i = 1; i <= remaining; i++) {
      html += `<div class="cal-day other"><div class="num">${i}</div></div>`;
    }
    $("#cal-grid").innerHTML = html;
  }).catch(() => {});
}

/* ---------------- 统计 ---------------- */

function renderStatistics() {
  const s = state.stats; if (!s) return;
  const cur = s.currency;
  const cards = [
    ["本月支出", fmtCents(s.monthly_expense, cur), ""],
    ["本月实际到期", fmtCents(s.monthly_actual_expense, cur), ""],
    ["年支出", fmtCents(s.yearly_expense, cur), ""],
    ["未来 30 天", fmtCents(s.upcoming_30_days, cur), ""],
  ];
  $("#stats-big").innerHTML = cards.map(([l, v]) => `
    <div class="stat-card"><div class="label">${l}</div><div class="value">${v}</div></div>`).join("");
  $("#trend-unit").textContent = `(单位: ${cur})`;

  const max = Math.max(...s.monthly_trend.map((m) => m.amount), 1);
  $("#trend-chart").innerHTML = s.monthly_trend.map((m) => `
    <div class="trend-col"><div class="trend-bar-wrap">
      <div class="trend-bar" style="height:${Math.max(2, (m.amount / max) * 100)}%" title="${m.month} ${fmtCents(m.amount, cur)}"></div>
    </div><div class="trend-month">${m.month.slice(5)}月</div></div>`).join("");

  $("#cat-tbody").innerHTML = s.category_stats.map((c) => `
    <tr><td>${esc(c.category_name)}</td><td>${fmtCents(c.amount, cur)}</td>
    <td>${fmtCents(c.yearly_amount, cur)}</td><td>${c.percentage}%</td></tr>`).join("") ||
    `<tr><td colspan="4" class="muted">暂无数据</td></tr>`;
}

/* ---------------- 设置 ---------------- */

function renderSettings() {
  const s = state.settings; if (!s) return;
  $("#set-default-currency").value = s.default_currency || "CNY";
  $("#set-rate-usd").value = s.exchange_rate_usd ?? 7.2;
  $("#set-rate-hkd").value = s.exchange_rate_hkd ?? 0.92;
  $("#set-notify-days").value = s.notification_days ?? 3;
  $("#set-notify-enabled").checked = !!s.notification_enabled;
  $("#set-dnd-start").value = s.do_not_disturb_start || "";
  $("#set-dnd-end").value = s.do_not_disturb_end || "";
  $("#set-email-enabled").checked = !!s.email_enabled;
  $("#set-smtp-host").value = s.smtp_host || "";
  $("#set-smtp-port").value = s.smtp_port || "";
  $("#set-smtp-user").value = s.smtp_username || "";
  $("#set-smtp-pass").value = s.smtp_password || "";
  $("#set-smtp-from").value = s.smtp_from_address || "";
  $("#set-pushplus-enabled").checked = !!s.pushplus_enabled;
  $("#set-pushplus-token").value = s.pushplus_token || "";

  $("#cat-list").innerHTML = state.cats.map((c) => `
    <span class="cat-chip">${esc(c.icon || "")} ${esc(c.name)}
      <button data-del-cat="${c.id}" title="删除分类">✕</button></span>`).join("") || '<span class="muted">暂无分类</span>';
  loadBackupFiles();
}

async function loadBackupFiles() {
  try {
    const files = await api("api/backup/files");
    $("#backup-tbody").innerHTML = files.map((f) => `
      <tr><td>${esc(f.name)}</td><td>${(f.size / 1024).toFixed(1)} KB</td></tr>`).join("") ||
      '<tr><td colspan="2" class="muted">暂无备份</td></tr>';
  } catch (_) {}
}

async function saveSettings() {
  const body = {
    default_currency: $("#set-default-currency").value,
    exchange_rate_usd: parseFloat($("#set-rate-usd").value) || 7.2,
    exchange_rate_hkd: parseFloat($("#set-rate-hkd").value) || 0.92,
    notification_days: parseInt($("#set-notify-days").value, 10) || 3,
    notification_enabled: $("#set-notify-enabled").checked,
    do_not_disturb_start: $("#set-dnd-start").value || null,
    do_not_disturb_end: $("#set-dnd-end").value || null,
    email_enabled: $("#set-email-enabled").checked,
    smtp_host: $("#set-smtp-host").value || null,
    smtp_port: parseInt($("#set-smtp-port").value, 10) || null,
    smtp_username: $("#set-smtp-user").value || null,
    smtp_password: $("#set-smtp-pass").value || null,
    smtp_from_address: $("#set-smtp-from").value || null,
    pushplus_enabled: $("#set-pushplus-enabled").checked,
    pushplus_token: $("#set-pushplus-token").value || null,
  };
  state.settings = await api("api/settings", { method: "PUT", body });
  toast("设置已保存");
}

/* ---------------- 订阅表单 ---------------- */

function openModal(sub) {
  $("#modal").classList.remove("hidden");
  $("#modal-title").textContent = sub ? "编辑订阅" : "新增订阅";
  $("#f-id").value = sub ? sub.id : "";
  $("#f-name").value = sub ? sub.name : "";
  $("#f-amount").value = sub ? (sub.amount / 100).toFixed(2) : "";
  $("#f-currency").value = sub ? sub.currency : (state.settings?.default_currency || "CNY");
  $("#f-period").value = sub ? sub.period_type : "month";
  $("#f-custom-value").value = sub?.custom_period_value || 1;
  $("#f-custom-unit").value = sub?.custom_period_unit || "month";
  $("#f-custom-wrap").hidden = $("#f-period").value !== "custom";
  $("#f-auto-renew").checked = sub ? sub.auto_renew : true;
  $("#f-start").value = sub?.start_date || "";
  $("#f-first-pay").value = sub?.first_payment_date || "";
  $("#f-next-due").value = sub?.next_due_date || "";
  $("#f-notes").value = sub?.notes || "";

  $("#f-category").innerHTML = `<option value="">未分类</option>` +
    state.cats.map((c) => `<option value="${c.id}" ${sub?.category_id === c.id ? "selected" : ""}>${esc(c.icon || "")} ${esc(c.name)}</option>`).join("");
}

async function saveSubscription(e) {
  e.preventDefault();
  const body = {
    name: $("#f-name").value.trim(),
    category_id: $("#f-category").value || null,
    amount: Math.round(parseFloat($("#f-amount").value || "0") * 100),
    currency: $("#f-currency").value,
    period_type: $("#f-period").value,
    custom_period_value: parseInt($("#f-custom-value").value, 10) || 1,
    custom_period_unit: $("#f-custom-unit").value,
    auto_renew: $("#f-auto-renew").checked,
    start_date: $("#f-start").value || null,
    first_payment_date: $("#f-first-pay").value || null,
    next_due_date: $("#f-next-due").value || null,
    notes: $("#f-notes").value.trim() || null,
  };
  if (!body.name) { toast("请输入名称", "err"); return; }
  const id = $("#f-id").value;
  try {
    if (id) await api(`api/subscriptions/${id}`, { method: "PUT", body });
    else await api("api/subscriptions", { method: "POST", body });
    $("#modal").classList.add("hidden");
    toast("已保存");
    await refresh();
  } catch (err) { toast(err.message, "err"); }
}

/* ---------------- 刷新 ---------------- */

async function refresh() {
  const [subs, cats, settings, stats] = await Promise.all([
    api("api/subscriptions"), api("api/categories"), api("api/settings"),
    api("api/statistics?mode=nominal"),
  ]);
  state.subs = subs; state.cats = cats; state.settings = settings; state.stats = stats;
  render();
}

/* ---------------- 事件绑定 ---------------- */

function bindEvents() {
  $$(".nav-item").forEach((b) => b.onclick = () => { state.view = b.dataset.view; renderNav(); if (b.dataset.view === "calendar") renderCalendar(); if (b.dataset.view === "statistics") refresh(); });

  $("#btn-new").onclick = () => openModal(null);
  $("#modal-close").onclick = () => $("#modal").classList.add("hidden");
  $("#btn-cancel").onclick = () => $("#modal").classList.add("hidden");
  $("#sub-form").onsubmit = saveSubscription;
  $("#modal").addEventListener("click", (e) => { if (e.target === $("#modal")) $("#modal").classList.add("hidden"); });

  $("#f-period").onchange = () => { $("#f-custom-wrap").hidden = $("#f-period").value !== "custom"; };

  $("#filter-search").oninput = renderSubscriptions;
  $("#filter-category").onchange = renderSubscriptions;
  $("#filter-status").onchange = renderSubscriptions;

  $("#sub-tbody").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]"); if (!btn) return;
    const { act, id } = btn.dataset;
    try {
      if (act === "del") {
        if (!confirm("确定删除该订阅？")) return;
        await api(`api/subscriptions/${id}`, { method: "DELETE" });
        toast("已删除");
      } else if (act === "renew") {
        await api(`api/subscriptions/${id}/renew`, { method: "POST" });
        toast("已续费，推进到下一期");
      } else if (act === "edit") {
        const sub = state.subs.find((s) => s.id === id);
        openModal(sub); return;
      }
      await refresh();
    } catch (err) { toast(err.message, "err"); }
  });

  $("#cal-prev").onclick = () => { prevMonth(-1); };
  $("#cal-next").onclick = () => { prevMonth(1); };
  $("#cal-today").onclick = () => { const n = new Date(); state.calYear = n.getFullYear(); state.calMonth = n.getMonth() + 1; renderCalendar(); };
  function prevMonth(delta) {
    state.calMonth += delta;
    if (state.calMonth < 1) { state.calMonth = 12; state.calYear--; }
    if (state.calMonth > 12) { state.calMonth = 1; state.calYear++; }
    renderCalendar();
  }

  $("#btn-backup").onclick = backupNow;
  $("#btn-backup-now").onclick = backupNow;

  async function backupNow() {
    try {
      const r = await api("api/backup", { method: "POST" });
      toast(`备份完成：${r.file} (${r.count} 条)`);
      loadBackupFiles();
    } catch (err) { toast(err.message, "err"); }
  }

  $("#btn-export-json").onclick = () => download("api/backup/export-json", "subscriptions.json");
  $("#btn-export-csv").onclick = () => download("api/export/csv", "subscriptions.csv");
  function download(url, filename) {
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
  }

  $("#file-import-json").onchange = async (e) => {
    const text = await e.target.files[0].text();
    try {
      const r = await api("api/backup/import-json", { text, headers: { "Content-Type": "application/json" } });
      toast(`导入完成：新增 ${r.success_count}，跳过重复 ${r.skipped_duplicates}`);
      e.target.value = ""; await refresh();
    } catch (err) { toast(err.message, "err"); }
  };
  $("#file-import-csv").onchange = async (e) => {
    const text = await e.target.files[0].text();
    try {
      const r = await api("api/backup/import-csv", { text, headers: { "Content-Type": "text/csv" } });
      toast(`导入完成：新增 ${r.success_count}，跳过 ${r.skipped_duplicates + (r.failed_rows || []).length}`);
      e.target.value = ""; await refresh();
    } catch (err) { toast(err.message, "err"); }
  };

  $("#btn-add-cat").onclick = async () => {
    const name = $("#cat-name").value.trim();
    if (!name) { toast("请输入分类名称", "err"); return; }
    try {
      await api("api/categories", { method: "POST", body: { name, icon: $("#cat-icon").value.trim() || null } });
      $("#cat-name").value = ""; $("#cat-icon").value = "";
      toast("分类已添加"); await refresh();
    } catch (err) { toast(err.message, "err"); }
  };
  $("#cat-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-del-cat]"); if (!btn) return;
    if (!confirm("确定删除该分类？（订阅保留为未分类）")) return;
    try {
      await api(`api/categories/${btn.dataset.delCat}`, { method: "DELETE" });
      toast("已删除"); await refresh();
    } catch (err) { toast(err.message, "err"); }
  });

  // 设置保存（输入变化后延迟保存）
  let saveTimer = null;
  $$("#view-settings input, #view-settings select").forEach((el) => {
    el.addEventListener("change", () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(async () => {
        try { await saveSettings(); } catch (err) { toast(err.message, "err"); }
      }, 400);
    });
  });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------- 启动 ---------------- */

bindEvents();
loadAll().catch((err) => toast(err.message, "err"));
setInterval(() => {
  if (document.visibilityState === "visible") refresh().catch(() => {});
}, 60000);
