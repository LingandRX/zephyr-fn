<script setup>
import { ref, computed, onMounted, watch, onDeactivated } from "vue";
import {
  getSubscriptions, getCategories, getStatistics,
  createSubscription, updateSubscription, deleteSubscription, renewSubscription,
} from "../api.js";
import { fmtCents, daysLeft, PERIOD_LABEL, CUSTOM_UNIT_LABEL, yuanToCents, centsToYuan } from "../format.js";
import { ui, toast, openNewSub } from "../ui.js";

const subs = ref([]);
const cats = ref([]);
const stats = ref(null);
const loading = ref(false);

const search = ref("");
const filterCat = ref("");
const filterStatus = ref("");

// ---------- 弹窗状态 ----------
const modalOpen = ref(false);
const modalTitle = ref("新增订阅");
const editingId = ref(null);
const form = ref(emptyForm());

function emptyForm() {
  return {
    name: "", category_id: "", currency: "CNY", amount: "", period_type: "month",
    custom_value: "1", custom_unit: "month", auto_renew: true,
    start_date: "", first_payment_date: "", next_due_date: "", notes: "",
  };
}

// 侧边栏「新增订阅」按钮触发（跨组件事件，避免模板 ref 耦合）
watch(() => ui.nextComponent, () => openModal());

// keep-alive 切走时关闭弹窗，避免返回后弹窗残留
onDeactivated(() => { modalOpen.value = false; });

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
  if (dl < 0) return `已过 ${-dl} 天`;
  if (dl === 0) return "今天";
  if (dl <= 7) return `${dl} 天`;
  return `${dl} 天`;
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

// ---------- 操作 ----------
function openModal(sub = null) {
  editingId.value = sub?.id ?? null;
  modalTitle.value = sub ? "编辑订阅" : "新增订阅";
  form.value = sub
    ? {
        name: sub.name, category_id: sub.category_id || "", currency: sub.currency,
        amount: centsToYuan(sub.amount), period_type: sub.period_type,
        custom_value: sub.custom_period_value ?? "1", custom_unit: sub.custom_period_unit || "month",
        auto_renew: !!sub.auto_renew, start_date: sub.start_date || "",
        first_payment_date: sub.first_payment_date || "", next_due_date: sub.next_due_date || "",
        notes: sub.notes || "",
      }
    : emptyForm();
  modalOpen.value = true;
}

async function save() {
  const f = form.value;
  if (!f.name.trim()) return toast("名称不能为空", "err");
  const body = {
    name: f.name.trim(),
    category_id: f.category_id || null,
    currency: f.currency,
    amount: yuanToCents(f.amount),
    period_type: f.period_type,
    custom_period_value: f.period_type === "custom" ? f.custom_value : null,
    custom_period_unit: f.period_type === "custom" ? f.custom_unit : null,
    auto_renew: f.auto_renew,
    start_date: f.start_date || null,
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
    await loadAll();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function del(sub) {
  if (!confirm(`确认删除「${sub.name}」？`)) return;
  try {
    await deleteSubscription(sub.id);
    toast("已删除");
    await loadAll();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function renew(sub) {
  try {
    await renewSubscription(sub.id);
    toast("已续费到下一期");
    await loadAll();
  } catch (err) {
    toast(err.message, "err");
  }
}

onMounted(loadAll);

// openNewSub re-export 保证模板按钮可用（App.vue 用 ui.nextComponent 间接触发）
</script>

<template>
  <div class="page">
    <div v-if="stats" class="stats-grid">
      <div v-for="c in statCards" :key="c.label" class="stat-card">
        <div class="label">{{ c.label }}</div>
        <div class="value">{{ c.value }}</div>
        <div class="sub">{{ c.sub }}</div>
      </div>
    </div>

    <div class="filter-bar">
      <input v-model="search" type="search" placeholder="搜索订阅名称..." />
      <select v-model="filterCat">
        <option value="">全部分类</option>
        <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.icon || "" }} {{ c.name }}</option>
      </select>
      <select v-model="filterStatus">
        <option value="">全部状态</option>
        <option value="active">活跃</option>
        <option value="expiring">即将到期</option>
        <option value="in_payment">待支付</option>
        <option value="grace_period">宽限期</option>
        <option value="canceled">已取消</option>
        <option value="expired">已过期</option>
      </select>
    </div>

    <div class="card">
      <div class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>订阅</th><th>金额</th><th>周期</th><th>下次扣费</th>
              <th>剩余</th><th>状态</th><th class="ta-r">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filtered" :key="s.id">
              <td>
                <div class="sub-name">
                  {{ s.name }}
                  <small>
                    {{ catName(s.category_id) ? catName(s.category_id).icon + " " + catName(s.category_id).name : "未分类" }}
                    {{ s.notes ? " · " + s.notes : "" }}
                  </small>
                </div>
              </td>
              <td>
                {{ fmtCents(s.amount, s.currency) }}
                <small v-if="s.actual_amount" class="muted" style="display: block">实付 {{ fmtCents(s.actual_amount, s.currency) }}</small>
              </td>
              <td>{{ PERIOD_LABEL[s.period_type] || s.period_type }}
                <small v-if="s.period_type === 'custom'" class="muted" style="display: block">
                  {{ s.custom_period_value }}{{ CUSTOM_UNIT_LABEL[s.custom_period_unit] }}
                </small>
              </td>
              <td>{{ s.next_due_date || "—" }}</td>
              <td :class="statusClass(s)">{{ statusText(s) }}</td>
              <td><span class="badge" :style="{ color: s.status_color }">{{ s.status_label }}</span></td>
              <td class="ta-r">
                <div class="row-actions">
                  <button v-if="s.period_type !== 'once'" @click="renew(s)">续费</button>
                  <button @click="openModal(s)">编辑</button>
                  <button class="danger" @click="del(s)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!loading && !filtered.length" class="empty">
        {{ subs.length ? "没有匹配的订阅" : "还没有订阅，点击左侧「新增订阅」开始记录" }}
      </div>
    </div>

    <!-- 新增/编辑弹窗（嵌套在视图根节点内，保证组件单根 -> v-show 生效） -->
    <div v-if="modalOpen" class="modal" @click.self="modalOpen = false">
    <div class="modal-card">
      <div class="modal-head">
        <h2>{{ modalTitle }}</h2>
        <button class="modal-close" @click="modalOpen = false">✕</button>
      </div>
      <form @submit.prevent="save">
        <div class="form-grid">
          <label class="field span-2"><span>名称 *</span><input v-model="form.name" required placeholder="如 Netflix" /></label>
          <label class="field"><span>分类</span>
            <select v-model="form.category_id">
              <option value="">未分类</option>
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.icon || "" }} {{ c.name }}</option>
            </select>
          </label>
          <label class="field"><span>货币</span>
            <select v-model="form.currency">
              <option value="CNY">CNY (¥)</option>
              <option value="USD">USD ($)</option>
              <option value="HKD">HKD (HK$)</option>
            </select>
          </label>
          <label class="field"><span>金额（元）*</span>
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
          <label class="field"><span>开始日期</span><input v-model="form.start_date" type="date" /></label>
          <label class="field"><span>首次付款日</span><input v-model="form.first_payment_date" type="date" /></label>
          <label class="field span-2"><span>下次扣费日</span><input v-model="form.next_due_date" type="date" /></label>
          <label class="field span-2"><span>备注</span><textarea v-model="form.notes" rows="2" placeholder="可选"></textarea></label>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn" @click="modalOpen = false">取消</button>
          <button type="submit" class="btn btn-primary">保存</button>
        </div>
      </form>
    </div>
  </div>
</div>
</template>