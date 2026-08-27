<script setup>
import { ref, computed, onMounted, watch, onDeactivated, onActivated } from "vue";
import {
  getSubscriptions, getCategories, getStatistics,
  createSubscription, updateSubscription, deleteSubscription, renewSubscription,
} from "../api.js";
import { fmtCents, daysLeft, PERIOD_LABEL, CUSTOM_UNIT_LABEL, yuanToCents, centsToYuan } from "../format.js";
import { ui, toast, openNewSub } from "../ui.js";
import CustomSelect from "../components/CustomSelect.vue";

const subs = ref([]);
const cats = ref([]);
const stats = ref(null);
const loading = ref(false);

const search = ref("");
const filterCat = ref("");
const filterStatus = ref("");
const NOTES_MAX_LENGTH = 120;

const statusOptions = [
  { label: "全部状态", value: "" },
  { label: "活跃", value: "active" },
  { label: "即将到期", value: "expiring" },
  { label: "待支付", value: "in_payment" },
  { label: "宽限期", value: "grace_period" },
  { label: "已取消", value: "canceled" },
  { label: "已过期", value: "expired" },
];

const catOptions = computed(() => [
  { label: "全部分类", value: "" },
  ...cats.value.map((c) => ({ label: c.name, value: c.id })),
]);

// ---------- 弹窗状态 ----------
const modalOpen = ref(false);
const modalTitle = ref("新增订阅");
const editingId = ref(null);
const form = ref(emptyForm());

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function emptyForm() {
  return {
    name: "", category_id: "", currency: "CNY", amount: "", period_type: "month",
    custom_value: "1", custom_unit: "month", auto_renew: true,
    start_date: todayStr(), first_payment_date: "", next_due_date: "", notes: "",
  };
}

const notesLength = computed(() => Array.from(form.value.notes || "").length);
const isEditingSubscription = ref(false);

function limitNotes(event) {
  const notes = Array.from(event.target.value).slice(0, NOTES_MAX_LENGTH).join("");
  if (event.target.value !== notes) event.target.value = notes;
  form.value.notes = notes;
}

// 根据开始日期和周期类型自动计算下次扣费日期
function calcNextDueDate(startDate, periodType) {
  if (!startDate || !['month', 'quarter', 'year'].includes(periodType)) return null;
  const [y, m, d] = startDate.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const months = periodType === 'month' ? 1 : periodType === 'quarter' ? 3 : 12;
  // 目标月份和年份
  const targetMonth = date.getMonth() + months;
  const targetYear = date.getFullYear() + Math.floor(targetMonth / 12);
  const modMonth = targetMonth % 12;
  // 获取目标月份的最大天数，处理月末溢出（如 1月31日 → 2月28日）
  const maxDay = new Date(targetYear, modMonth + 1, 0).getDate();
  const targetDay = Math.min(d, maxDay);
  const result = new Date(targetYear, modMonth, targetDay);
  return `${result.getFullYear()}-${String(result.getMonth() + 1).padStart(2, '0')}-${String(result.getDate()).padStart(2, '0')}`;
}

watch(
  () => [form.value.start_date, form.value.period_type],
  ([sd, pt]) => {
    // 编辑模式下不自动计算 next_due_date，避免覆盖续费后的正确值
    if (!isEditingSubscription.value) {
      const next = calcNextDueDate(sd, pt);
      if (next) form.value.next_due_date = next;
    }
    // 开始日期变化时，始终同步更新首次付款日期
    if (sd) {
      form.value.first_payment_date = sd;
    }
  },
);

// 侧边栏「新增订阅」按钮触发（跨组件响应式状态）
watch(
  () => ui.showAddModal,
  (show) => {
    if (show) {
      openModal();
      ui.showAddModal = false;
    }
  },
  { immediate: true },
);

onActivated(() => {
  if (ui.showAddModal) {
    openModal();
    ui.showAddModal = false;
  }
});

// keep-alive 切走时关闭弹窗，避免返回后弹窗残留
onDeactivated(() => { modalOpen.value = false; isEditingSubscription.value = false; });

// 弹窗关闭时重置编辑标志
watch(modalOpen, (open) => { if (!open) isEditingSubscription.value = false; });

async function loadAll() {
  loading.value = true;
  try {
    const [s, c, st] = await Promise.all([getSubscriptions(), getCategories(), getStatistics()]);
    subs.value = s; cats.value = c; stats.value = st;
  } catch (err) {
    toast(err.message, "err");
  } finally {
    loading.value = false;
  }
}

// ---------- 过滤 ----------
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  return subs.value.filter((s) => {
    if (q && !s.name.toLowerCase().includes(q)) return false;
    if (filterCat.value && s.category_id !== filterCat.value) return false;
    if (filterStatus.value && s.status !== filterStatus.value) return false;
    return true;
  });
});

function statusText(s) {
  const dl = daysLeft(s.next_due_date);
  if (s.lifecycle !== "active") return s.status_label;
  if (dl === null) return "";
  if (dl < 0) return `已逾期 ${-dl} 天`;
  if (dl === 0) return "今天扣费";
  if (dl === 1) return "明天扣费";
  return `剩余 ${dl} 天`;
}

function statusClass(s) {
  const dl = daysLeft(s.next_due_date);
  return dl !== null && dl < 0 ? "days-overdue" : dl !== null && dl <= 7 ? "days-soon" : "";
}

const statCards = computed(() => {
  const st = stats.value;
  if (!st) return [];
  const cur = st.currency;
  return [
    { label: "本月支出", value: fmtCents(st.monthly_expense, cur), sub: `实际到期 ${fmtCents(st.monthly_actual_expense, cur)}` },
    { label: "年支出", value: fmtCents(st.yearly_expense, cur), sub: "按到期周期计" },
    { label: "未来 30 天", value: fmtCents(st.upcoming_30_days, cur), sub: "即将扣费" },
    { label: "活跃订阅", value: `${st.active_count}`, sub: "个" },
  ];
});

const catName = (id) => cats.value.find((c) => c.id === id);

// 分类图标已下线：头像区域改为显示订阅名称首字符
function initialOf(name) {
  const s = String(name ?? "").trim();
  return s ? [...s][0].toUpperCase() : "?"; 
}

// ---------- 操作 ----------
function openModal(sub = null) {
  editingId.value = sub?.id ?? null;
  modalTitle.value = sub ? "编辑订阅" : "新增订阅";
  isEditingSubscription.value = !!sub;
  if (sub) {
    const sd = sub.start_date || "";
    form.value = {
      name: sub.name, category_id: sub.category_id || "", currency: sub.currency,
      amount: centsToYuan(sub.amount), period_type: sub.period_type,
      custom_value: sub.custom_period_value ?? "1", custom_unit: sub.custom_period_unit || "month",
      auto_renew: !!sub.auto_renew, start_date: sd,
      first_payment_date: sub.first_payment_date || sd || "",
      next_due_date: sub.next_due_date || "",
      notes: sub.notes || "",
    };
  } else {
    const fresh = emptyForm();
    fresh.first_payment_date = fresh.start_date;
    form.value = fresh;
  }
  modalOpen.value = true;
}

async function save() {
  const f = form.value;
  if (!f.name.trim()) return toast("名称不能为空", "err");
  if (!f.start_date) return toast("请选择开始日期", "err");
  if (notesLength.value > NOTES_MAX_LENGTH) {
    return toast(`备注不能超过${NOTES_MAX_LENGTH}字`, "err");
  }
  const body = {
    name: f.name.trim(),
    category_id: f.category_id || null,
    currency: f.currency,
    amount: yuanToCents(f.amount),
    period_type: f.period_type,
    custom_period_value: f.period_type === "custom" ? f.custom_value : null,
    custom_period_unit: f.period_type === "custom" ? f.custom_unit : null,
    auto_renew: f.auto_renew,
    start_date: f.start_date,
    first_payment_date: f.first_payment_date || null,
    next_due_date: f.next_due_date || null,
    notes: f.notes.trim() || null,
  };
  try {
    if (editingId.value) {
      await updateSubscription(editingId.value, body);
    } else {
      await createSubscription(body);
    }
    toast(editingId.value ? "已保存" : "已新增");
    modalOpen.value = false;
    isEditingSubscription.value = false;
    await loadAll();
  } catch (err) {
    toast(err.message, "err");
  }
}

// ---------- 删除确认弹窗 ----------
const delOpen = ref(false);
const delTarget = ref(null);     // 待删除的订阅对象
const delBusy = ref(false);      // 防重复提交

function askDel(sub) {
  delTarget.value = sub;
  delOpen.value = true;
}

function closeDel() {
  if (delBusy.value) return;     // 删除进行中不允许关闭
  delOpen.value = false;
  delTarget.value = null;
}

async function confirmDel() {
  const sub = delTarget.value;
  if (!sub) return;
  delBusy.value = true;
  try {
    await deleteSubscription(sub.id);
    toast("已删除");
    delOpen.value = false;
    delTarget.value = null;
    await loadAll();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    delBusy.value = false;
  }
}

// ---------- 续费确认弹窗 ----------
const renewOpen = ref(false);
const renewTarget = ref(null);
const renewBusy = ref(false);

function askRenew(sub) {
  renewTarget.value = sub;
  renewOpen.value = true;
}

function closeRenew() {
  if (renewBusy.value) return;
  renewOpen.value = false;
  renewTarget.value = null;
}

async function confirmRenew() {
  const sub = renewTarget.value;
  if (!sub) return;
  renewBusy.value = true;
  try {
    const updated = await renewSubscription(sub.id);
    // 立即用返回的最新数据更新 subs 数组，避免 loadAll 异步延迟期间编辑弹窗拿到旧数据
    const idx = subs.value.findIndex((s) => s.id === updated.id);
    if (idx !== -1) Object.assign(subs.value[idx], updated);
    toast("已续费到下一期");
    renewOpen.value = false;
    renewTarget.value = null;
    await loadAll();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    renewBusy.value = false;
  }
}

onMounted(loadAll);

// openNewSub re-export 保证模板按钮可用（App.vue 用 ui.nextComponent 间接触发）
</script>

<template>
  <div class="page">
    <!-- 统计卡片 -->
    <div v-if="stats" class="stats-grid">
      <div v-for="c in statCards" :key="c.label" class="stat-card">
        <div class="label">{{ c.label }}</div>
        <div class="value">{{ c.value }}</div>
        <div class="sub">{{ c.sub }}</div>
      </div>
    </div>

    <!-- 筛选控制栏 -->
    <div class="filter-bar">
      <div class="search-wrap">
        <span class="search-icon"><svg width="15" height="15" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M945.066667 898.133333l-189.866667-189.866666c55.466667-64 87.466667-149.333333 87.466667-241.066667 0-204.8-168.533333-373.333333-373.333334-373.333333S96 264.533333 96 469.333333 264.533333 842.666667 469.333333 842.666667c91.733333 0 174.933333-34.133333 241.066667-87.466667l189.866667 189.866667c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333c8.533333-12.8 8.533333-34.133333-2.133333-46.933334zM469.333333 778.666667C298.666667 778.666667 160 640 160 469.333333S298.666667 160 469.333333 160 778.666667 298.666667 778.666667 469.333333 640 778.666667 469.333333 778.666667z"/></svg></span>
        <input v-model="search" type="search" placeholder="搜索订阅名称、备注..." />
      </div>
      <div class="filter-selects">
        <CustomSelect
          v-model="filterCat"
          :options="catOptions"
          placeholder="全部分类"
        />
        <CustomSelect
          v-model="filterStatus"
          :options="statusOptions"
          placeholder="全部状态"
        />
      </div>
    </div>

    <!-- 结果统计摘要 -->
    <div class="list-summary" v-if="subs.length">
      <span>共 {{ filtered.length }} 项订阅</span>
      <span v-if="filterCat || filterStatus || search" class="clear-filters" @click="search = ''; filterCat = ''; filterStatus = ''">清除筛选</span>
    </div>

    <!-- 列表展示容器 -->
    <div class="card sub-content-card">
      <!-- 桌面端表格视图 (>= 768px) -->
      <div class="desktop-only table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>订阅</th>
              <th>金额</th>
              <th>周期</th>
              <th>下次扣费</th>
              <th>状态</th>
              <th class="ta-r">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filtered" :key="s.id" class="sub-table-row">
              <td>
                <div class="sub-cell">
                  <div class="sub-avatar">{{ initialOf(s.name) }}</div>
                  <div class="sub-info">
                    <span class="sub-title">{{ s.name }}</span>
                    <div class="sub-meta">
                      <span class="cat-badge">{{ catName(s.category_id)?.name || "未分类" }}</span>
                      <span v-if="s.notes" class="notes-text" :title="s.notes">{{ s.notes }}</span>
                    </div>
                  </div>
                </div>
              </td>
              <td>
                <div class="amount-cell">
                  <span class="amount-main">{{ fmtCents(s.amount, s.currency) }}</span>
                  <small v-if="s.actual_amount" class="muted">实付 {{ fmtCents(s.actual_amount, s.currency) }}</small>
                </div>
              </td>
              <td>
                <div class="period-cell">
                  <span>{{ PERIOD_LABEL[s.period_type] || s.period_type }}</span>
                  <small v-if="s.period_type === 'custom'" class="muted">
                    {{ s.custom_period_value }}{{ CUSTOM_UNIT_LABEL[s.custom_period_unit] }}
                  </small>
                </div>
              </td>
              <td>
                <div class="due-cell">
                  <span class="due-date">{{ s.next_due_date || "—" }}</span>
                  <span v-if="s.next_due_date" class="due-countdown" :class="statusClass(s)">
                    {{ statusText(s) }}
                  </span>
                </div>
              </td>
              <td>
                <span class="badge" :style="{ color: s.status_color, borderColor: s.status_color + '40', background: s.status_color + '15' }">
                  {{ s.status_label }}
                </span>
              </td>
              <td class="ta-r">
                <div class="row-actions">
                  <button v-if="s.period_type !== 'once'" class="btn-action-renew" @click="askRenew(s)">续费</button>
                  <button @click="openModal(s)">编辑</button>
                  <button class="danger" @click="askDel(s)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 移动端卡片视图 (< 768px) -->
      <div class="mobile-only sub-cards-list">
        <div v-for="s in filtered" :key="s.id" class="sub-item-card">
          <div class="item-header">
            <div class="item-brand">
              <span class="item-avatar">{{ initialOf(s.name) }}</span>
              <div class="item-title-wrap">
                <div class="item-name">{{ s.name }}</div>
                <div class="item-cat-tag">{{ catName(s.category_id)?.name || "未分类" }}</div>
              </div>
            </div>
            <div class="item-badge-wrap">
              <span class="badge" :style="{ color: s.status_color, borderColor: s.status_color + '40', background: s.status_color + '15' }">
                {{ s.status_label }}
              </span>
              <span v-if="s.next_due_date && statusText(s)" class="due-countdown" :class="statusClass(s)">
                {{ statusText(s) }}
              </span>
            </div>
          </div>

          <div class="item-body">
            <div class="item-stat">
              <span class="stat-lbl">下次扣费</span>
              <span class="stat-val">{{ s.next_due_date || "—" }}</span>
            </div>
            <div class="item-amount">
              <span class="amt-val">{{ fmtCents(s.amount, s.currency) }}</span>
              <span class="amt-cycle">/ {{ PERIOD_LABEL[s.period_type] || s.period_type }}</span>
            </div>
          </div>

          <div v-if="s.notes" class="item-notes">
            <span class="notes-icon"><svg width="11" height="11" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M853.333333 501.333333c-17.066667 0-32 14.933333-32 32v320c0 6.4-4.266667 10.666667-10.666666 10.666667H170.666667c-6.4 0-10.666667-4.266667-10.666667-10.666667V213.333333c0-6.4 4.266667-10.666667 10.666667-10.666666h320c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32H170.666667c-40.533333 0-74.666667 34.133333-74.666667 74.666666v640c0 40.533333 34.133333 74.666667 74.666667 74.666667h640c40.533333 0 74.666667-34.133333 74.666666-74.666667V533.333333c0-17.066667-14.933333-32-32-32zM405.333333 484.266667l-32 125.866666c-2.133333 10.666667 0 23.466667 8.533334 29.866667 6.4 6.4 14.933333 8.533333 23.466666 8.533333h8.533334l125.866666-32c6.4-2.133333 10.666667-4.266667 14.933334-8.533333l300.8-300.8c38.4-38.4 38.4-102.4 0-140.8-38.4-38.4-102.4-38.4-140.8 0L413.866667 469.333333c-4.266667 4.266667-6.4 8.533333-8.533334 14.933334z m59.733334 23.466666L761.6 213.333333c12.8-12.8 36.266667-12.8 49.066667 0 12.8 12.8 12.8 36.266667 0 49.066667L516.266667 558.933333l-66.133334 17.066667 14.933334-68.266667z"/></svg></span>
            <span class="notes-content">{{ s.notes }}</span>
          </div>

          <div class="item-actions">
            <button v-if="s.period_type !== 'once'" class="btn-m btn-m-renew" @click="askRenew(s)">续费</button>
            <button class="btn-m" @click="openModal(s)">编辑</button>
            <button class="btn-m btn-m-danger" @click="askDel(s)">删除</button>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && !filtered.length" class="empty-wrap">
        <div class="empty-icon"><svg width="32" height="32" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M403.2 160c25.6 0 51.2 12.8 64 36.266667l38.4 66.133333c2.133333 4.266667 6.4 4.266667 8.533333 4.266667H853.333333c40.533333 0 74.666667 34.133333 74.666667 74.666666v448c0 40.533333-34.133333 74.666667-74.666667 74.666667H170.666667c-40.533333 0-74.666667-34.133333-74.666667-74.666667V234.666667c0-40.533333 34.133333-74.666667 74.666667-74.666667h232.533333z m87.466667 256H253.866667c-17.066667 2.133333-29.866667 14.933333-29.866667 32s14.933333 32 32 32h236.8c17.066667-2.133333 29.866667-14.933333 29.866667-32s-14.933333-32-32-32z"/></svg></div>
        <div class="empty-text">
          {{ subs.length ? "没有匹配的订阅条件" : "还没有订阅，点击右下角「+」开始记录" }}
        </div>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <div v-if="modalOpen" class="modal" @click.self="modalOpen = false">
      <div class="modal-card">
        <div class="modal-head">
          <h2>{{ modalTitle }}</h2>
          <button class="modal-close" @click="modalOpen = false"><svg width="16" height="16" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/></svg></button>
        </div>
        <form class="modal-form" @submit.prevent="save">
          <div class="modal-scroll">
          <div class="form-grid">
            <label class="field span-2"><span>名称 *</span><input v-model="form.name" required placeholder="如 Netflix" /></label>
            <label class="field"><span>分类</span>
              <select v-model="form.category_id">
                <option value="">未分类</option>
                <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </label>
            <label class="field"><span>货币</span>
              <select v-model="form.currency">
                <option value="CNY">CNY (¥)</option>
                <option value="USD">USD ($)</option>
                <option value="HKD">HKD (HK$)</option>
              </select>
            </label>
            <label class="field"><span>金额（{{ form.currency === 'USD' ? '美元' : form.currency === 'HKD' ? '港币' : '元' }}）*</span>
              <input v-model="form.amount" type="number" required min="0" step="0.01" placeholder="68" />
            </label>
            <label class="field"><span>周期</span>
              <select v-model="form.period_type">
                <option value="month">月付</option>
                <option value="quarter">季付</option>
                <option value="year">年付</option>
                <option value="once">一次性</option>
                <option value="custom">自定义</option>
              </select>
            </label>
            <label v-if="form.period_type === 'custom'" class="field span-2"><span>自定义周期</span>
              <span class="inline">
                <input v-model="form.custom_value" type="number" min="1" />
                <select v-model="form.custom_unit">
                  <option v-for="(label, u) in CUSTOM_UNIT_LABEL" :key="u" :value="u">{{ label }}</option>
                </select>
              </span>
            </label>
            <label class="field checkbox span-2">
              <input v-model="form.auto_renew" type="checkbox" />
              <span>自动续费</span>
            </label>
            <label class="field"><span>开始日期 *</span><input v-model="form.start_date" type="date" required /></label>
            <label class="field"><span>首次付款日</span><input v-model="form.first_payment_date" type="date" /></label>
            <label class="field span-2"><span>下次扣费日</span><input v-model="form.next_due_date" type="date" /></label>
            <label class="field span-2 notes-field">
              <span>备注</span>
              <textarea
                v-model="form.notes"
                class="notes-input"
                rows="3"
                maxlength="120"
                placeholder="可选"
                @input="limitNotes"
              ></textarea>
              <span class="notes-counter" :class="{ 'is-limit': notesLength >= NOTES_MAX_LENGTH }">
                {{ notesLength }}/{{ NOTES_MAX_LENGTH }}
              </span>
            </label>
          </div>
          </div>
          <div class="modal-foot">
            <button type="button" class="btn" @click="modalOpen = false">取消</button>
            <button type="submit" class="btn btn-primary">保存</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="delOpen" class="modal" @click.self="closeDel">
      <div class="modal-card modal-confirm">
        <div class="modal-head">
          <h2>删除订阅</h2>
          <button class="modal-close" :disabled="delBusy" @click="closeDel"><svg width="16" height="16" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/></svg></button>
        </div>
        <div class="modal-scroll">
        <div class="confirm-body">
          <p class="confirm-text">
            确认删除「<strong>{{ delTarget?.name }}</strong>」？此操作不可撤销。
          </p>
          <div v-if="delTarget" class="confirm-meta">
            <span class="confirm-meta-item">{{ fmtCents(delTarget.amount, delTarget.currency) }}</span>
            <span class="confirm-meta-item">{{ PERIOD_LABEL[delTarget.period_type] || delTarget.period_type }}</span>
            <span class="confirm-meta-item">{{ delTarget.next_due_date || "无下次扣费" }}</span>
          </div>
        </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn" :disabled="delBusy" @click="closeDel">取消</button>
          <button type="button" class="btn btn-danger" :disabled="delBusy" @click="confirmDel">
            {{ delBusy ? "删除中…" : "确认删除" }}
          </button>
        </div>
      </div>
    </div>

    <!-- 续费确认弹窗 -->
    <div v-if="renewOpen" class="modal" @click.self="closeRenew">
      <div class="modal-card modal-confirm">
        <div class="modal-head">
          <h2>续费确认</h2>
          <button class="modal-close" :disabled="renewBusy" @click="closeRenew"><svg width="16" height="16" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/></svg></button>
        </div>
        <div class="modal-scroll">
        <div class="confirm-body">
          <p class="confirm-text">
            确认将「<strong>{{ renewTarget?.name }}</strong>」续费到下一期？
          </p>
          <div v-if="renewTarget" class="confirm-meta">
            <span class="confirm-meta-item">{{ fmtCents(renewTarget.amount, renewTarget.currency) }}</span>
            <span class="confirm-meta-item">{{ PERIOD_LABEL[renewTarget.period_type] || renewTarget.period_type }}</span>
            <span class="confirm-meta-item">当前扣费日 {{ renewTarget.next_due_date || "—" }}</span>
          </div>
        </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn" :disabled="renewBusy" @click="closeRenew">取消</button>
          <button type="button" class="btn btn-primary" :disabled="renewBusy" @click="confirmRenew">
            {{ renewBusy ? "续费中…" : "确认续费" }}
          </button>
        </div>
      </div>
    </div>

    <!-- 右下角浮动新增按钮已上移到 BaseLayout 公共壳（所有页可用），这里不再重复 -->
  </div>
</template>

<style scoped>
/* ---------- 响应式展示切换 ---------- */
.desktop-only { display: block !important; }
.mobile-only { display: none !important; }

/* 筛选栏与搜索 */
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: var(--space-3);
  align-items: center;
  width: 100%;
}
.search-wrap {
  position: relative;
  flex: 1 1 auto;
  min-width: 200px;
}
.search-wrap input[type="search"],
.search-wrap input {
  width: 100%;
  height: 38px;
  line-height: 38px;
  padding: 0 12px 0 34px;
  box-sizing: border-box;
  -webkit-appearance: none;
  appearance: none;
  font-size: var(--fs-sm);
  border-radius: var(--radius-sm);
}
.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  line-height: 1;
  opacity: 0.6;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.filter-selects {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}
.filter-selects select,
.filter-selects :deep(.custom-select) {
  min-width: 130px;
}
.filter-selects select {
  height: 38px;
  box-sizing: border-box;
  padding: 0 12px;
  font-size: var(--fs-sm);
  border-radius: var(--radius-sm);
}

/* 列表摘要统计 */
.list-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--fs-xs);
  color: var(--muted);
  margin-bottom: var(--space-2);
  padding: 0 2px;
}
.clear-filters {
  color: var(--primary);
  cursor: pointer;
  text-decoration: underline;
}

.sub-content-card {
  padding: var(--space-3);
}

/* ---------- 桌面端表格优化 ---------- */
.sub-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sub-avatar {
  width: 36px;
  height: 36px;
  background: var(--card-2);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.sub-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.sub-title {
  font-weight: 600;
  font-size: var(--fs-md);
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
}
.cat-badge {
  background: var(--card-2);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--muted);
}
.notes-text {
  color: var(--muted);
  max-width: 140px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.notes-field .notes-input {
  width: 100%;
  box-sizing: border-box;
  height: 84px;
  min-height: 84px;
  max-height: 120px;
  resize: vertical;
  overflow-y: auto;
  line-height: 1.5;
}
.notes-field .notes-counter {
  align-self: flex-end;
  color: var(--muted);
  font-size: 11px;
  line-height: 1;
}
.notes-field .notes-counter.is-limit {
  color: var(--amber);
}

.amount-cell, .period-cell, .due-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.amount-main {
  font-weight: 600;
  color: var(--text);
}
.due-countdown {
  font-size: 11px;
  font-weight: 500;
}
.due-countdown.days-soon { color: var(--amber); }
.due-countdown.days-overdue { color: var(--red); }

.badge {
  border: 1px solid currentColor;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  display: inline-block;
}

.btn-action-renew {
  border-color: var(--primary) !important;
  color: var(--primary) !important;
}
.btn-action-renew:hover {
  background: var(--primary) !important;
  color: #fff !important;
}

/* ---------- 移动端卡片列表 ---------- */
.sub-cards-list {
  flex-direction: column;
  gap: 10px;
}
.sub-item-card {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.sub-item-card:active {
  border-color: var(--primary);
}
.item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.item-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.item-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--card);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.item-title-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.item-name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item-cat-tag {
  font-size: 11px;
  color: var(--muted);
}
.item-badge-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  flex-shrink: 0;
}
.item-body {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  background: var(--card);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255, 255, 255, 0.03);
}
.item-stat .stat-lbl {
  display: block;
  font-size: 11px;
  color: var(--muted);
}
.item-stat .stat-val {
  font-size: 13px;
  font-weight: 500;
}
.item-amount {
  text-align: right;
}
.amt-val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}
.amt-cycle {
  font-size: 12px;
  color: var(--muted);
  margin-left: 2px;
}
.item-notes {
  font-size: 12px;
  color: var(--muted);
  background: var(--card);
  padding: 6px 10px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.notes-icon {
  font-size: 11px;
  opacity: 0.8;
}
.notes-content {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  margin-top: 2px;
}
.btn-m {
  padding: 5px 12px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  cursor: pointer;
}
.btn-m-renew {
  border-color: var(--primary);
  color: var(--primary);
  font-weight: 500;
}
.btn-m-danger {
  color: var(--red);
}

/* 空状态 */
.empty-wrap {
  text-align: center;
  padding: 36px 16px;
  color: var(--muted);
}
.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}
.empty-text {
  font-size: var(--fs-sm);
}

/* ---------- 响应式断点适配 ---------- */
@media (max-width: 860px) {
  .desktop-only { display: none !important; }
  .mobile-only { display: flex !important; }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 8px !important;
  }
  .stat-card {
    padding: 10px 12px !important;
  }
  .stat-card .value {
    font-size: 17px !important;
  }

  /* 移动端筛选栏：搜索独占一行，下拉并排 2 列 */
  .filter-bar {
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 8px !important;
  }
  .search-wrap {
    width: 100% !important;
    flex: 1 1 100% !important;
    min-width: 0 !important;
  }
  .filter-selects {
    display: flex !important;
    width: 100% !important;
    gap: 8px !important;
  }
  .filter-selects select,
  .filter-selects :deep(.custom-select) {
    flex: 1 1 50% !important;
    width: 50% !important;
    min-width: 0 !important;
  }

  .sub-content-card {
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
  }
}

/* ---------------- 删除确认弹窗 ---------------- */
.modal-confirm { width: 420px; }
.confirm-body { padding: 4px 0 2px; }
.confirm-text {
  margin: 0 0 14px;
  font-size: var(--fs-sm);
  line-height: 1.6;
  color: var(--text);
}
.confirm-text strong { color: var(--text); font-weight: 600; }
.confirm-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.confirm-meta-item {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.btn-danger {
  background: var(--red);
  border-color: var(--red);
  color: #fff;
}
.btn-danger:hover:not(:disabled) { filter: brightness(0.92); }
.btn-danger:disabled { opacity: 0.6; cursor: not-allowed; }

/* ---------------- 弹窗移动端适配 (<=860px) ---------------- */
@media (max-width: 860px) {
  /* 弹窗整体上下留足安全距离，避免被地址栏 / 键盘遮挡 */
  .modal {
    align-items: center;
    padding: max(12px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom));
  }

  /* 全宽弹窗：去掉固定宽度、加大圆角、内容可滚动 */
  .modal-card,
  .modal-confirm {
    width: 100%;
    max-width: 100%;
    border-radius: var(--radius-lg);
  }
  .modal-card {
    max-height: 90vh;
    max-height: 90dvh;
    overflow: hidden;
  }
  .modal-scroll {
    -webkit-overflow-scrolling: touch;
  }

  /* 表单单列布局，跨列字段不再跨列 */
  .form-grid {
    grid-template-columns: 1fr;
  }
  .span-2 {
    grid-column: span 1;
  }

  /* 放大触控目标，字号不小于 16px 防止 iOS 自动缩放 */
  .form-grid input:not([type="checkbox"]),
  .form-grid select {
    height: 44px;
    font-size: 16px;
  }
  .form-grid textarea {
    min-height: 80px;
    font-size: 16px;
  }

  /* 操作按钮固定在弹窗底部，内容滚动时始终可见 */
  .modal-foot {
    position: sticky;
    bottom: 0;
    z-index: 1;
    background: var(--card);
    margin: var(--space-3) -20px 0;
    padding: 12px 20px 6px;
    border-top: 1px solid var(--border);
  }
}
</style>