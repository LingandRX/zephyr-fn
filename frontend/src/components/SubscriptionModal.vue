<script setup>
import { ref, computed, watch } from "vue";
import {
  Dialog,
  DialogPanel,
  DialogTitle,
} from "@headlessui/vue";
import { CUSTOM_UNIT_LABEL, yuanToCents, centsToYuan } from "../utils/format.js";
import { toast } from "../utils/ui.js";
import HeadlessListbox from "./HeadlessListbox.vue";
import HeadlessDatePicker from "./HeadlessDatePicker.vue";
import HeadlessSwitch from "./HeadlessSwitch.vue";
import HeadlessButton from "./HeadlessButton.vue";
import TemplateSelector from "./TemplateSelector.vue";

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
const showTemplateSelector = ref(false);

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

function handleTemplateSelect(template) {
  form.value.name = template.name;
  form.value.currency = template.currency || "CNY";
  form.value.amount = (template.amount / 100).toFixed(2);
  form.value.period_type = template.period_type || "month";
  form.value.auto_renew = template.auto_renew !== false;
  if (template.notes) {
    form.value.notes = template.notes;
  }
}
</script>

<template>
  <Dialog
    :open="modelValue"
    @close="close"
    class="modal-dialog-root"
  >
    <div class="modal-dialog-backdrop" aria-hidden="true" />

    <div class="modal-dialog-container">
      <DialogPanel class="modal-card">
        <div class="modal-head">
          <DialogTitle as="h2">{{ modalTitle }}</DialogTitle>
          <button type="button" class="modal-close" @click="close" aria-label="关闭弹窗">
            <svg width="16" height="16" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
              <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
            </svg>
          </button>
        </div>
      <form class="modal-form" @submit.prevent="save">
        <div class="modal-scroll">
          <div class="form-grid">
            <div class="field span-2">
              <span>名称 *</span>
              <div class="name-input-group">
                <input v-model="form.name" required placeholder="如 Netflix" class="name-input" />
                <HeadlessButton
                  v-if="!isEditing"
                  @click="showTemplateSelector = true"
                  class="template-btn"
                  title="从模板选择"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
                    <rect x="3" y="3" width="7" height="7" rx="2" />
                    <rect x="14" y="3" width="7" height="7" rx="2" />
                    <rect x="3" y="14" width="7" height="7" rx="2" />
                    <rect x="14" y="14" width="7" height="7" rx="2" />
                  </svg>
                  模板
                </HeadlessButton>
              </div>
            </div>
            <div class="field">
              <span>分类</span>
              <HeadlessListbox
                v-model="form.category_id"
                :options="formCatOptions"
                placeholder="未分类"
              />
            </div>
            <div class="field">
              <span>货币</span>
              <HeadlessListbox
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
              <HeadlessListbox
                v-model="form.period_type"
                :options="periodTypeOptions"
                :clearable="false"
              />
            </div>
            <div v-if="form.period_type === 'custom'" class="field span-2">
              <span>自定义周期</span>
              <span class="inline">
                <input v-model="form.custom_value" type="number" min="1" />
                <HeadlessListbox
                  v-model="form.custom_unit"
                  :options="customUnitOptions"
                  :clearable="false"
                />
              </span>
            </div>
            <HeadlessSwitch
              v-model="form.auto_renew"
              label="自动续费"
              class="span-2"
            />
            <div class="field">
              <span>开始日期 *</span>
              <HeadlessDatePicker
                v-model="form.start_date"
                placeholder="选择开始日期"
                :clearable="false"
              />
            </div>
            <div class="field">
              <span>首次付款日</span>
              <HeadlessDatePicker
                v-model="form.first_payment_date"
                placeholder="首次付款日"
                :clearable="true"
              />
            </div>
            <div class="field span-2">
              <span>下次扣费日</span>
              <HeadlessDatePicker
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
          <HeadlessButton @click="resetForm">重置</HeadlessButton>
          <div class="modal-foot-actions">
            <HeadlessButton @click="close">取消</HeadlessButton>
            <HeadlessButton type="submit" variant="primary" :disabled="saving">保存</HeadlessButton>
          </div>
        </div>
      </form>
      </DialogPanel>
    </div>

    <!-- 模板选择器：必须嵌套在本 Dialog 内部，作为组件树后代。
         HeadlessUI 的堆栈机制在子 Dialog 打开时会把父 Dialog 的计数加一，
         从而禁用父 Dialog 的「外部点击关闭」，否则点击模板卡片会被父弹窗
         判定为外部点击而把整个新增弹窗关掉。 -->
    <TemplateSelector
      :model-value="showTemplateSelector"
      @update:model-value="showTemplateSelector = $event"
      @select="handleTemplateSelect"
    />
  </Dialog>
</template>

<style scoped>
/* =====================================================================
 * 新增/编辑订阅弹窗 · iOS 风格
 * 毛玻璃卡片 / iOS 表单控件 / iOS 文字按钮
 * iOS 令牌来自 styles/tokens.css（--ios-*，已全局可用）
 * ===================================================================== */

:global(.modal-dialog-root) {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
}

:global(.modal-dialog-backdrop) {
  position: fixed;
  inset: 0;
  /* Dialog 根节点是 Fragment，根类拿不到本组件的 scoped data-v，规则不生效；z-index 必须写在自己的元素上 */
  z-index: var(--z-modal);
  background: rgba(0, 0, 0, 0.4);
  -webkit-backdrop-filter: blur(3px);
  backdrop-filter: blur(3px);
  animation: modal-fade-in var(--dur-quick) ease-out;
}

:global(.modal-dialog-container) {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  pointer-events: none;
}

/* ---------------- 弹窗卡片 ---------------- */
.modal-dialog-container .modal-card {
  pointer-events: auto;
  width: 560px;
  max-width: 100%;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  backdrop-filter: saturate(180%) blur(24px);
  border: 1px solid var(--ios-card-border);
  border-radius: 18px;
  box-shadow: var(--ios-shadow-panel);
  animation: modal-zoom-in var(--dur-base) var(--ease-decelerate);
}

@keyframes modal-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes modal-zoom-in {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

/* ---------------- 头部 ---------------- */
.modal-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 0;
  margin-bottom: 14px;
}

.modal-head h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.2px;
  color: var(--text);
}

.modal-close {
  flex: none;
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--ios-fill);
  color: var(--ios-gray);
  cursor: pointer;
  transition: background-color var(--dur-fast) ease, color var(--dur-fast) ease;
}

.modal-close:hover {
  background: var(--ios-separator);
  color: var(--text);
}

.modal-close:focus {
  outline: none;
}

.modal-close:focus-visible {
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

/* ---------------- 表单控件 ---------------- */
.modal-form .form-grid {
  gap: 14px 16px;
}

.modal-form .field {
  gap: 6px;
}

/* 字段标签（排除 .inline 容器与备注计数器） */
.modal-form .field > span:not(.inline):not(.notes-counter) {
  color: var(--ios-gray);
  font-size: 13px;
}

.modal-form input:not([type="checkbox"]):not([type="radio"]),
.modal-form textarea {
  box-sizing: border-box;
  width: 100%;
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text);
  font-family: inherit;
  font-size: var(--fs-sm);
  transition: background-color var(--dur-quick) ease, border-color var(--dur-quick) ease, box-shadow var(--dur-quick) ease;
}

.modal-form input:not([type="checkbox"]):not([type="radio"]) {
  height: 38px;
  padding: 0 12px;
}

.modal-form textarea {
  padding: 10px 12px;
  min-height: 84px;
  line-height: 1.5;
}

.modal-form input:focus,
.modal-form textarea:focus {
  outline: none;
  background: var(--ios-card-bg);
  border-color: var(--ios-blue);
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.modal-form input::placeholder,
.modal-form textarea::placeholder {
  color: var(--ios-gray);
}

/* 自动续费开关：iOS 绿 */
.modal-form :deep(.switch-on) {
  background-color: var(--ios-green);
}

.modal-form :deep(.switch-button:focus-visible) {
  outline: none;
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.modal-form :deep(.switch-label) {
  color: var(--text);
  font-weight: 500;
}

/* 备注 */
.notes-field {
  position: relative;
}

.notes-input {
  resize: vertical;
}

.notes-counter {
  margin-top: 2px;
  text-align: right;
  font-size: var(--fs-xs);
  color: var(--ios-gray);
}

.notes-counter.is-limit {
  color: var(--ios-red);
}

/* 名称 + 模板按钮 */
.name-input-group {
  display: flex;
  gap: var(--space-2);
  align-items: stretch;
}

.name-input {
  flex: 1 1 auto;
  min-width: 0;
}

.template-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 38px;
  padding: 0 14px;
  border: none;
  border-radius: 10px;
  background: var(--ios-blue-soft);
  color: var(--ios-blue);
  font-family: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color var(--dur-quick) ease, transform var(--dur-instant) ease;
}

.template-btn:hover {
  background: rgba(0, 122, 255, 0.2);
}

.template-btn:active {
  transform: scale(0.97);
}

.template-btn:focus {
  outline: none;
}

.template-btn:focus-visible {
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.template-btn svg {
  width: 14px;
  height: 14px;
}

/* ---------------- 底部操作栏 ---------------- */
.modal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: 14px 20px 18px;
}

.modal-foot-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 文字按钮：取消/保存蓝色，重置灰色 */
.modal-foot :deep(.headless-btn) {
  height: 38px;
  padding: 0 14px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--ios-blue);
  font-weight: 500;
  transition: background-color var(--dur-fast) ease, color var(--dur-fast) ease;
}

.modal-foot :deep(.headless-btn:hover:not(:disabled)) {
  background: var(--ios-fill);
  border-color: transparent;
}

.modal-foot > :deep(.headless-btn) {
  color: var(--ios-gray);
}

.modal-foot :deep(.headless-btn.btn-primary) {
  background: var(--ios-blue);
  color: #fff;
  font-weight: 600;
}

.modal-foot :deep(.headless-btn.btn-primary:hover:not(:disabled)) {
  background: #0069d9;
}

.modal-foot :deep(.headless-btn:focus-visible) {
  outline: none;
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

/* ---------------- 移动端适配 (<=860px) ---------------- */
@media (max-width: 860px) {
  :global(.modal-dialog-container) {
    align-items: center;
    padding: max(12px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom));
  }

  .modal-card {
    width: 100%;
    max-width: 100%;
    border-radius: 18px;
    max-height: 90vh;
    max-height: 90dvh;
    overflow: hidden;
  }

  .modal-scroll {
    -webkit-overflow-scrolling: touch;
  }

  .form-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .span-2 {
    grid-column: span 1;
  }

  /* 触控目标放大到 44px，字号 16px 防止 iOS 聚焦自动缩放 */
  .modal-form input:not([type="checkbox"]):not([type="radio"]),
  .modal-form select,
  .modal-form :deep(.custom-select-trigger),
  .modal-form :deep(.custom-date-picker-trigger),
  .template-btn {
    height: 44px;
    font-size: 16px;
  }

  .modal-form textarea {
    min-height: 88px;
    font-size: 16px;
  }

  /* 底部按钮吸底，内容滚动时始终可见 */
  .modal-foot {
    position: sticky;
    bottom: 0;
    z-index: 1;
    margin: var(--space-3) -20px 0;
    padding: 12px 20px calc(10px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--ios-separator);
    background: var(--ios-card-bg);
    -webkit-backdrop-filter: saturate(180%) blur(24px);
    backdrop-filter: saturate(180%) blur(24px);
  }

  .modal-foot :deep(.headless-btn) {
    height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  :global(.modal-dialog-backdrop),
  .modal-dialog-container .modal-card {
    animation: none;
  }
}
</style>
