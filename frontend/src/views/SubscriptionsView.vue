<script setup>
import { ref, computed, onMounted, watch, onDeactivated, onActivated } from "vue";
import {
  getSubscriptions, getCategories, getStatistics,
  createSubscription, updateSubscription, deleteSubscription, renewSubscription,
} from "../services/api.js";
import { fmtCents, daysLeft, PERIOD_LABEL, CUSTOM_UNIT_LABEL, yuanToCents, centsToYuan } from "../utils/format.js";
import { ui, toast, openNewSub } from "../utils/ui.js";

import {
  Dialog, DialogPanel, DialogTitle,
  TransitionRoot, TransitionChild,
} from "@headlessui/vue";

import HeadlessListbox from "../components/HeadlessListbox.vue";
import SubscriptionModal from "../components/SubscriptionModal.vue";

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
const editingSub = ref(null);

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
  loadAll();
  if (ui.showAddModal) {
    openModal();
    ui.showAddModal = false;
  }
});

// keep-alive 切走时关闭弹窗，避免返回后弹窗残留
onDeactivated(() => { modalOpen.value = false; editingSub.value = null; });

// 弹窗关闭时重置编辑对象
watch(modalOpen, (open) => { if (!open) editingSub.value = null; });

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
  editingSub.value = sub || null;
  modalOpen.value = true;
}

async function handleModalSave({ isEdit, id, body, clearDraft }) {
  try {
    if (isEdit && id) {
      await updateSubscription(id, body);
    } else {
      await createSubscription(body);
      clearDraft();
    }
    toast(isEdit ? "已保存" : "已新增");
    modalOpen.value = false;
    editingSub.value = null;
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
  // 不立即清空 delTarget：离场动画期间面板仍在渲染，置 null 会闪一下空内容
  delOpen.value = false;
}

async function confirmDel() {
  const sub = delTarget.value;
  if (!sub) return;
  delBusy.value = true;
  try {
    await deleteSubscription(sub.id);
    toast("已删除");
    // 保留 delTarget 供离场动画渲染
    delOpen.value = false;
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
  // 不立即清空 renewTarget：离场动画期间面板仍在渲染，置 null 会闪一下空内容
  renewOpen.value = false;
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
    // 保留 renewTarget 供离场动画渲染
    renewOpen.value = false;
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
        <span class="search-icon" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.6-3.6" />
          </svg>
        </span>
        <input v-model="search" type="search" placeholder="搜索订阅名称、备注..." />
      </div>
      <div class="filter-selects">
        <HeadlessListbox
          v-model="filterCat"
          :options="catOptions"
          placeholder="全部分类"
        />
        <HeadlessListbox
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
    <SubscriptionModal
      v-model="modalOpen"
      :subscription="editingSub"
      :categories="cats"
      @saved="handleModalSave"
    />

    <!-- 删除确认弹窗（Headless UI Dialog · iOS 弹窗样式） -->
    <TransitionRoot :show="delOpen" as="template">
      <Dialog as="div" class="sub-dialog-root" @close="closeDel">
        <TransitionChild
          as="template"
          enter="sub-dialog-backdrop-enter"
          enter-from="sub-dialog-backdrop-from"
          enter-to="sub-dialog-backdrop-to"
          leave="sub-dialog-backdrop-leave"
          leave-from="sub-dialog-backdrop-to"
          leave-to="sub-dialog-backdrop-from"
        >
          <div class="sub-dialog-backdrop" aria-hidden="true" />
        </TransitionChild>

        <div class="sub-dialog-container">
          <TransitionChild
            as="template"
            enter="sub-dialog-panel-enter"
            enter-from="sub-dialog-panel-from"
            enter-to="sub-dialog-panel-to"
            leave="sub-dialog-panel-leave"
            leave-from="sub-dialog-panel-to"
            leave-to="sub-dialog-panel-from"
          >
            <DialogPanel class="sub-dialog-panel">
              <div class="sub-dialog-body">
                <DialogTitle as="h2" class="sub-dialog-title">删除订阅</DialogTitle>
                <p class="sub-dialog-text">
                  确认删除「<strong>{{ delTarget?.name }}</strong>」？此操作不可撤销。
                </p>
                <div v-if="delTarget" class="sub-dialog-meta">
                  <span class="sub-dialog-meta-item">{{ fmtCents(delTarget.amount, delTarget.currency) }}</span>
                  <span class="sub-dialog-meta-item">{{ PERIOD_LABEL[delTarget.period_type] || delTarget.period_type }}</span>
                  <span class="sub-dialog-meta-item">{{ delTarget.next_due_date || "无下次扣费" }}</span>
                </div>
              </div>
              <div class="sub-dialog-actions">
                <button type="button" class="sub-dialog-btn" :disabled="delBusy" @click="closeDel">取消</button>
                <button type="button" class="sub-dialog-btn is-destructive" :disabled="delBusy" @click="confirmDel">
                  {{ delBusy ? "删除中…" : "删除" }}
                </button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- 续费确认弹窗（Headless UI Dialog · iOS 弹窗样式） -->
    <TransitionRoot :show="renewOpen" as="template">
      <Dialog as="div" class="sub-dialog-root" @close="closeRenew">
        <TransitionChild
          as="template"
          enter="sub-dialog-backdrop-enter"
          enter-from="sub-dialog-backdrop-from"
          enter-to="sub-dialog-backdrop-to"
          leave="sub-dialog-backdrop-leave"
          leave-from="sub-dialog-backdrop-to"
          leave-to="sub-dialog-backdrop-from"
        >
          <div class="sub-dialog-backdrop" aria-hidden="true" />
        </TransitionChild>

        <div class="sub-dialog-container">
          <TransitionChild
            as="template"
            enter="sub-dialog-panel-enter"
            enter-from="sub-dialog-panel-from"
            enter-to="sub-dialog-panel-to"
            leave="sub-dialog-panel-leave"
            leave-from="sub-dialog-panel-to"
            leave-to="sub-dialog-panel-from"
          >
            <DialogPanel class="sub-dialog-panel">
              <div class="sub-dialog-body">
                <DialogTitle as="h2" class="sub-dialog-title">续费确认</DialogTitle>
                <p class="sub-dialog-text">
                  确认将「<strong>{{ renewTarget?.name }}</strong>」续费到下一期？
                </p>
                <div v-if="renewTarget" class="sub-dialog-meta">
                  <span class="sub-dialog-meta-item">{{ fmtCents(renewTarget.amount, renewTarget.currency) }}</span>
                  <span class="sub-dialog-meta-item">{{ PERIOD_LABEL[renewTarget.period_type] || renewTarget.period_type }}</span>
                  <span class="sub-dialog-meta-item">当前扣费日 {{ renewTarget.next_due_date || "—" }}</span>
                </div>
              </div>
              <div class="sub-dialog-actions">
                <button type="button" class="sub-dialog-btn" :disabled="renewBusy" @click="closeRenew">取消</button>
                <button type="button" class="sub-dialog-btn is-primary" :disabled="renewBusy" @click="confirmRenew">
                  {{ renewBusy ? "续费中…" : "确认续费" }}
                </button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- 右下角浮动新增按钮已上移到 BaseLayout 公共壳（所有页可用），这里不再重复 -->
  </div>
</template>

<style scoped>
/* =====================================================================
 * 订阅列表 · iOS 风格
 * 毛玻璃卡片 / SF 排版 / 分组列表 / iOS 弹窗
 * iOS 色板令牌来自 styles/tokens.css（--ios-*，已全局可用）
 * ===================================================================== */

/* ---------- 响应式展示切换 ---------- */
.desktop-only { display: block !important; }
.mobile-only { display: none !important; }

/* ---------------- 顶部统计卡片 ---------------- */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.stat-card {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 16px 18px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 16px;
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
}

/* 顶部装饰渐变条 */
.stat-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  opacity: 0.85;
}
.stat-card:nth-child(1)::before { background: linear-gradient(90deg, var(--ios-green), #30d158); }
.stat-card:nth-child(2)::before { background: linear-gradient(90deg, var(--ios-blue), #5ac8fa); }
.stat-card:nth-child(3)::before { background: linear-gradient(90deg, var(--ios-orange), #ffb340); }
.stat-card:nth-child(4)::before { background: linear-gradient(90deg, #af52de, #da7cfc); }

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

.stat-card .label {
  color: var(--ios-gray);
  font-size: 13px;
  font-weight: 500;
}
.stat-card .value {
  margin: 8px 0 4px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: var(--text);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stat-card .sub {
  color: var(--ios-gray);
  font-size: 12px;
}

/* ---------------- 筛选栏 ---------------- */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin-bottom: 12px;
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
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text);
  transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}
.search-wrap input:focus {
  outline: none;
  background: var(--ios-card-bg);
  border-color: var(--ios-blue);
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}
.search-wrap input::placeholder {
  color: var(--ios-gray);
}
.search-wrap input::-webkit-search-cancel-button {
  -webkit-appearance: none;
}
.search-icon {
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  color: var(--ios-gray);
  pointer-events: none;
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
/* HeadlessListbox 触发器对齐 iOS 搜索框 */
.filter-selects :deep(.custom-select-trigger) {
  height: 38px;
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  font-size: var(--fs-sm);
}
.filter-selects :deep(.custom-select-trigger:hover) {
  background: var(--ios-separator);
}

/* ---------------- 列表摘要 ---------------- */
.list-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 0 2px;
  font-size: var(--fs-xs);
  color: var(--ios-gray);
}
.clear-filters {
  color: var(--ios-blue);
  font-weight: 500;
  cursor: pointer;
}
.clear-filters:hover {
  text-decoration: underline;
}

/* ---------------- 列表容器 ---------------- */
.sub-content-card {
  padding: 4px 8px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 16px;
}

/* ---------------- 桌面端表格（iOS 分组列表） ---------------- */
.table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
}
.table th,
.table td {
  text-align: left;
  padding: 12px 14px;
  border-bottom: 1px solid var(--ios-separator);
}
.table th {
  color: var(--ios-gray);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.table tbody tr {
  transition: background-color 0.15s ease;
}
.table tbody tr:hover {
  background: var(--ios-fill);
}
.table tbody tr:last-child td {
  border-bottom: none;
}

.sub-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sub-avatar {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--ios-blue-soft);
  color: var(--ios-blue);
  font-size: 17px;
  font-weight: 700;
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
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--ios-fill);
  color: var(--ios-gray);
  font-size: 11px;
}
.notes-text {
  max-width: 140px;
  color: var(--ios-gray);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.amount-cell,
.period-cell,
.due-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.amount-main {
  font-weight: 600;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.due-date {
  font-variant-numeric: tabular-nums;
}
.due-countdown {
  font-size: 11px;
  font-weight: 500;
  color: var(--ios-gray);
}
.due-countdown.days-soon { color: var(--ios-orange); }
.due-countdown.days-overdue { color: var(--ios-red); }

.badge {
  display: inline-block;
  padding: 3px 10px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

/* 行内操作：iOS 文字按钮 */
.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
}
.row-actions button {
  padding: 6px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--ios-blue);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}
.row-actions button:hover {
  background: var(--ios-fill);
}
.row-actions button.btn-action-renew {
  border: none !important;
  color: var(--ios-blue) !important;
  font-weight: 600;
}
.row-actions button.btn-action-renew:hover {
  background: var(--ios-fill) !important;
  color: var(--ios-blue) !important;
}
.row-actions button.danger {
  color: var(--ios-red);
}
.row-actions button.danger:hover {
  background: var(--ios-red-soft);
  color: var(--ios-red);
}

/* ---------------- 移动端卡片列表 ---------------- */
.sub-cards-list {
  flex-direction: column;
  gap: 10px;
}
.sub-item-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 16px;
  transition: transform 0.15s ease;
}
.sub-item-card:active {
  transform: scale(0.99);
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
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--ios-blue-soft);
  color: var(--ios-blue);
  font-size: 17px;
  font-weight: 700;
}
.item-title-wrap {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.item-name {
  font-weight: 600;
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item-cat-tag {
  font-size: 11px;
  color: var(--ios-gray);
}
.item-badge-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}
.item-body {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--ios-fill);
}
.item-stat .stat-lbl {
  display: block;
  font-size: 11px;
  color: var(--ios-gray);
}
.item-stat .stat-val {
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.item-amount {
  text-align: right;
}
.amt-val {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.amt-cycle {
  margin-left: 2px;
  font-size: 12px;
  color: var(--ios-gray);
}
.item-notes {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--ios-fill);
  font-size: 12px;
  color: var(--ios-gray);
}
.notes-icon {
  display: inline-flex;
  flex-shrink: 0;
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
  gap: 4px;
  padding-top: 10px;
  border-top: 1px solid var(--ios-separator);
}
.btn-m {
  padding: 7px 12px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--ios-blue);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.btn-m:active {
  background: var(--ios-fill);
}
.btn-m-renew {
  font-weight: 600;
}
.btn-m-danger {
  color: var(--ios-red);
}
.btn-m-danger:active {
  background: var(--ios-red-soft);
}

/* ---------------- 空状态 ---------------- */
.empty-wrap {
  padding: 44px 16px;
  text-align: center;
  color: var(--ios-gray);
}
.empty-icon {
  display: flex;
  justify-content: center;
  margin-bottom: 10px;
  color: var(--ios-gray);
  opacity: 0.5;
}
.empty-text {
  font-size: var(--fs-sm);
}

/* ---------------- 确认弹窗（Headless UI Dialog · iOS 弹窗） ---------------- */
.sub-dialog-root {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  overflow: hidden;
}
.sub-dialog-backdrop {
  position: fixed;
  inset: 0;
  /* Dialog 根节点是 Fragment，根类拿不到本组件的 scoped data-v，规则不生效；z-index 必须写在自己的元素上 */
  z-index: var(--z-modal);
  background: rgba(0, 0, 0, 0.4);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}
.sub-dialog-container {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  pointer-events: none;
}
.sub-dialog-panel {
  pointer-events: auto;
  width: 100%;
  max-width: 320px;
  overflow: hidden;
  border: 1px solid var(--ios-card-border);
  border-radius: 20px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  backdrop-filter: saturate(180%) blur(24px);
  box-shadow: var(--ios-shadow-panel);
  text-align: center;
}
.sub-dialog-body {
  padding: 20px 20px 16px;
}
.sub-dialog-title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
}
.sub-dialog-text {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--text);
}
.sub-dialog-text strong {
  font-weight: 600;
}
.sub-dialog-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  margin-top: 12px;
}
.sub-dialog-meta-item {
  padding: 4px 10px;
  border-radius: 8px;
  background: var(--ios-fill);
  font-size: var(--fs-xs);
  color: var(--ios-gray);
}
.sub-dialog-actions {
  display: flex;
  border-top: 1px solid var(--ios-separator);
}
.sub-dialog-btn {
  flex: 1 1 0;
  padding: 14px 8px;
  border: none;
  background: transparent;
  color: var(--ios-blue);
  font: inherit;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.sub-dialog-btn:hover {
  background: var(--ios-fill);
}
.sub-dialog-btn:focus {
  outline: none;
}
.sub-dialog-btn:focus-visible {
  box-shadow: inset 0 0 0 3px var(--ios-blue-soft);
}
.sub-dialog-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sub-dialog-btn + .sub-dialog-btn {
  border-left: 1px solid var(--ios-separator);
}
.sub-dialog-btn.is-destructive {
  color: var(--ios-red);
  font-weight: 600;
}
.sub-dialog-btn.is-primary {
  font-weight: 600;
}

/* Headless UI 过渡动画类 */
.sub-dialog-backdrop-enter { transition: opacity 0.22s ease-out; }
.sub-dialog-backdrop-from { opacity: 0; }
.sub-dialog-backdrop-to { opacity: 1; }
.sub-dialog-backdrop-leave { transition: opacity 0.18s ease-in; }

.sub-dialog-panel-enter {
  transition: opacity 0.2s ease, transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.sub-dialog-panel-from {
  opacity: 0;
  transform: scale(0.92);
}
.sub-dialog-panel-to {
  opacity: 1;
  transform: none;
}
.sub-dialog-panel-leave {
  transition: opacity 0.15s ease-in, transform 0.15s ease-in;
}

/* ---------------- 响应式断点适配 ---------------- */
@media (max-width: 860px) {
  .desktop-only { display: none !important; }
  .mobile-only { display: flex !important; }

  /* 给右下角浮动「+」按钮留出空间：滚到底时列表末尾不被遮挡 */
  .page { padding-bottom: 92px; }

  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 14px;
  }
  .stat-card {
    padding: 12px 14px;
    border-radius: 14px;
  }
  .stat-card .value {
    font-size: 20px;
    margin: 6px 0 3px;
  }

  /* 移动端筛选栏：搜索独占一行，两个下拉并排 */
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .search-wrap {
    width: 100%;
    flex: 1 1 100%;
    min-width: 0;
  }
  .filter-selects {
    display: flex;
    width: 100%;
    gap: 8px;
  }
  .filter-selects :deep(.custom-select) {
    flex: 1 1 50%;
    width: 50%;
    min-width: 0;
  }

  /* 卡片列表直接浮在页面上，去掉外层容器 */
  .sub-content-card {
    padding: 0;
    background: transparent;
    border: none;
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stat-card,
  .sub-item-card {
    transition: none;
  }
  .sub-dialog-backdrop,
  .sub-dialog-panel {
    transition: none !important;
  }
}
</style>
