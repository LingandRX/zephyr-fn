<script setup>
import { ref, computed, watch } from "vue";
import { CUSTOM_UNIT_LABEL, yuanToCents, centsToYuan } from "../utils/format.js";
import { toast } from "../utils/ui.js";
import CustomSelect from "./CustomSelect.vue";
import CustomDatePicker from "./CustomDatePicker.vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  subscription: {
    type: Object,
    default: null,
  },
  categories: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["update:modelValue", "saved"]);

const NOTES_MAX_LENGTH = 120;
const NEW_SUB_DRAFT_KEY = "zephyr_new_sub_draft";

const CURRENCY_OPTIONS = [
  { label: "CNY (¥)", value: "CNY" },
  { label: "USD ($)", value: "USD" },
  { label: "HKD (HK$)", value: "HKD" },
];

const periodTypeOptions = [
  { label: "月付", value: "month" },
  { label: "季付", value: "quarter" },
  { label: "年付", value: "year" },
  { label: "一次性", value: "once" },
  { label: "自定义", value: "custom" },
];

const customUnitOptions = Object.entries(CUSTOM_UNIT_LABEL).map(([unit, label]) => ({
  label,
  value: unit,
}));

const formCatOptions = computed(() => [
  { label: "未分类", value: "" },
  ...props.categories.map((c) => ({ label: c.name, value: c.id })),
]);

const modalTitle = computed(() => (props.subscription ? "编辑订阅" : "新增订阅"));
const isEditing = computed(() => !!props.subscription);
const form = ref(emptyForm());
const saving = ref(false);

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

function loadDraft() {
  try {
    const raw = localStorage.getItem(NEW_SUB_DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : null;
  } catch {
    return null;
  }
}

function saveDraft() {
  if (isEditing.value) return;
  try {
    localStorage.setItem(NEW_SUB_DRAFT_KEY, JSON.stringify(form.value));
  } catch {
    // 忽略存储异常
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(NEW_SUB_DRAFT_KEY);
  } catch {
    // 忽略存储异常
  }
}

function calcNextDueDate(startDate, periodType) {
  if (!startDate || !["month", "quarter", "year"].includes(periodType)) return null;
  const [y, m, d] = startDate.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const months = periodType === "month" ? 1 : periodType === "quarter" ? 3 : 12;
  const targetMonth = date.getMonth() + months;
  const targetYear = date.getFullYear() + Math.floor(targetMonth / 12);
  const modMonth = targetMonth % 12;
  const maxDay = new Date(targetYear, modMonth + 1, 0).getDate();
  const targetDay = Math.min(d, maxDay);
  const result = new Date(targetYear, modMonth, targetDay);
  return `${result.getFullYear()}-${String(result.getMonth() + 1).padStart(2, "0")}-${String(result.getDate()).padStart(2, "0")}`;
}

function resetForm() {
  const fresh = emptyForm();
  fresh.first_payment_date = fresh.start_date;
  const next = calcNextDueDate(fresh.start_date, fresh.period_type);
  if (next) fresh.next_due_date = next;
  form.value = fresh;
  if (!isEditing.value) {
    clearDraft();
  }
}

const notesLength = computed(() => Array.from(form.value.notes || "").length);

function limitNotes(event) {
  const notes = Array.from(event.target.value).slice(0, NOTES_MAX_LENGTH).join("");
  if (event.target.value !== notes) event.target.value = notes;
  form.value.notes = notes;
}

function isMobileDevice() {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(max-width: 860px)").matches;
}

function handleBackdropClick() {
  if (isMobileDevice()) {
    close();
  }
}

function close() {
  emit("update:modelValue", false);
}

// 监听弹窗打开状态，初始化表单
watch(
  () => [props.modelValue, props.subscription],
  ([visible, sub]) => {
    if (!visible) return;
    if (sub) {
      const sd = sub.start_date || "";
      form.value = {
        name: sub.name,
        category_id: sub.category_id || "",
        currency: sub.currency,
        amount: centsToYuan(sub.amount),
        period_type: sub.period_type,
        custom_value: sub.custom_period_value ?? "1",
        custom_unit: sub.custom_period_unit || "month",
        auto_renew: !!sub.auto_renew,
        start_date: sd,
        first_payment_date: sub.first_payment_date || sd || "",
        next_due_date: sub.next_due_date || "",
        notes: sub.notes || "",
      };
    } else {
      const draft = loadDraft();
      if (draft) {
        form.value = { ...emptyForm(), ...draft };
      } else {
        const fresh = emptyForm();
        fresh.first_payment_date = fresh.start_date;
        const next = calcNextDueDate(fresh.start_date, fresh.period_type);
        if (next) fresh.next_due_date = next;
        form.value = fresh;
      }
    }
  },
  { immediate: true },
);

watch(
  () => [form.value.start_date, form.value.period_type],
  ([sd, pt]) => {
    if (!props.modelValue) return;
    if (!isEditing.value) {
      const next = calcNextDueDate(sd, pt);
      if (next) form.value.next_due_date = next;
    }
    if (sd && !form.value.first_payment_date) {
      form.value.first_payment_date = sd;
    }
  },
);

watch(
  form,
  () => {
    if (props.modelValue && !isEditing.value) {
      saveDraft();
    }
  },
  { deep: true },
);

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

  saving.value = true;
  try {
    emit("saved", {
      isEdit: isEditing.value,
      id: props.subscription?.id,
      body,
      clearDraft: () => clearDraft(),
    });
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div v-if="modelValue" class="modal" @click.self="handleBackdropClick">
    <div class="modal-card">
      <div class="modal-head">
        <h2>{{ modalTitle }}</h2>
        <button class="modal-close" @click="close">
          <svg width="16" height="16" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
            <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
          </svg>
        </button>
      </div>
      <form class="modal-form" @submit.prevent="save">
        <div class="modal-scroll">
          <div class="form-grid">
            <label class="field span-2">
              <span>名称 *</span>
              <input v-model="form.name" required placeholder="如 Netflix" />
            </label>
            <div class="field">
              <span>分类</span>
              <CustomSelect
                v-model="form.category_id"
                :options="formCatOptions"
                placeholder="未分类"
              />
            </div>
            <div class="field">
              <span>货币</span>
              <CustomSelect
                v-model="form.currency"
                :options="CURRENCY_OPTIONS"
                :clearable="false"
              />
            </div>
            <label class="field">
              <span>金额（{{ form.currency === 'USD' ? '美元' : form.currency === 'HKD' ? '港币' : '元' }}）*</span>
              <input v-model="form.amount" type="number" required min="0" step="0.01" placeholder="68" />
            </label>
            <div class="field">
              <span>周期</span>
              <CustomSelect
                v-model="form.period_type"
                :options="periodTypeOptions"
                :clearable="false"
              />
            </div>
            <div v-if="form.period_type === 'custom'" class="field span-2">
              <span>自定义周期</span>
              <span class="inline">
                <input v-model="form.custom_value" type="number" min="1" />
                <CustomSelect
                  v-model="form.custom_unit"
                  :options="customUnitOptions"
                  :clearable="false"
                />
              </span>
            </div>
            <label class="field checkbox span-2">
              <input v-model="form.auto_renew" type="checkbox" />
              <span>自动续费</span>
            </label>
            <div class="field">
              <span>开始日期 *</span>
              <CustomDatePicker
                v-model="form.start_date"
                placeholder="选择开始日期"
                :clearable="false"
              />
            </div>
            <div class="field">
              <span>首次付款日</span>
              <CustomDatePicker
                v-model="form.first_payment_date"
                placeholder="首次付款日"
                :clearable="true"
              />
            </div>
            <div class="field span-2">
              <span>下次扣费日</span>
              <CustomDatePicker
                v-model="form.next_due_date"
                placeholder="下次扣费日"
                :clearable="true"
              />
            </div>
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
          <button type="button" class="btn" @click="resetForm">重置</button>
          <div class="modal-foot-actions">
            <button type="button" class="btn" @click="close">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="saving">保存</button>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.notes-field {
  position: relative;
}

.notes-input {
  resize: vertical;
}

.notes-counter {
  margin-top: 4px;
  text-align: right;
  font-size: var(--fs-xs);
  color: var(--muted);
}

.notes-counter.is-limit {
  color: var(--amber);
}

.modal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-foot-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* ---------------- 弹窗移动端适配 (<=860px) ---------------- */
@media (max-width: 860px) {
  .modal {
    align-items: center;
    padding: max(12px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom));
  }

  .modal-card {
    width: 100%;
    max-width: 100%;
    border-radius: var(--radius-lg);
    max-height: 90vh;
    max-height: 90dvh;
    overflow: hidden;
  }

  .modal-scroll {
    -webkit-overflow-scrolling: touch;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .span-2 {
    grid-column: span 1;
  }

  .form-grid input:not([type="checkbox"]),
  .form-grid select,
  .form-grid :deep(.custom-select-trigger),
  .form-grid :deep(.custom-date-picker-trigger) {
    height: 44px;
    font-size: 16px;
  }

  .form-grid textarea {
    min-height: 80px;
    font-size: 16px;
  }

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
