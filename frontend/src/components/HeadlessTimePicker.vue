<script setup>
import { computed, ref, nextTick, onMounted, onBeforeUnmount } from "vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  placeholder: {
    type: String,
    default: "选择时间",
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  clearable: {
    type: Boolean,
    default: true,
  },
  clearValue: {
    type: String,
    default: "",
  },
  minuteStep: {
    type: Number,
    default: 1,
  },
});

const emit = defineEmits(["update:modelValue", "change", "clear"]);

const timePickerRef = ref(null);
const dropdownRef = ref(null);
const hoursColRef = ref(null);
const minutesColRef = ref(null);
const isOpen = ref(false);
const dropdownPos = ref({ top: 0, left: 0 });

// 解析 modelValue 为时和分
const parsedTime = computed(() => {
  if (!props.modelValue || typeof props.modelValue !== "string") {
    return { hour: null, minute: null };
  }
  const match = props.modelValue.trim().match(/^(\d{1,2}):(\d{1,2})$/);
  if (!match) return { hour: null, minute: null };
  const h = parseInt(match[1], 10);
  const m = parseInt(match[2], 10);
  if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
    return {
      hour: String(h).padStart(2, "0"),
      minute: String(m).padStart(2, "0"),
    };
  }
  return { hour: null, minute: null };
});

const selectedHour = computed(() => parsedTime.value.hour);
const selectedMinute = computed(() => parsedTime.value.minute);

const hasValue = computed(() => {
  return Boolean(props.modelValue && props.modelValue !== props.clearValue);
});

const canClear = computed(() => {
  return props.clearable && !props.disabled && hasValue.value;
});

const displayLabel = computed(() => {
  if (selectedHour.value !== null && selectedMinute.value !== null) {
    return `${selectedHour.value}:${selectedMinute.value}`;
  }
  return props.modelValue || props.placeholder;
});

// 生成小时列表 (00 - 23)
const hoursList = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));

// 生成分钟列表 (根据 minuteStep 生成)
const minutesList = computed(() => {
  const step = Math.max(1, Math.min(30, props.minuteStep || 1));
  const list = [];
  for (let i = 0; i < 60; i += step) {
    list.push(String(i).padStart(2, "0"));
  }
  return list;
});

function scrollColumnsToSelected() {
  if (hoursColRef.value && selectedHour.value !== null) {
    const activeHour = hoursColRef.value.querySelector(".time-cell.is-selected");
    if (activeHour) {
      hoursColRef.value.scrollTop = Math.max(
        0,
        activeHour.offsetTop - hoursColRef.value.clientHeight / 2 + activeHour.clientHeight / 2,
      );
    }
  }
  if (minutesColRef.value && selectedMinute.value !== null) {
    const activeMinute = minutesColRef.value.querySelector(".time-cell.is-selected");
    if (activeMinute) {
      minutesColRef.value.scrollTop = Math.max(
        0,
        activeMinute.offsetTop - minutesColRef.value.clientHeight / 2 + activeMinute.clientHeight / 2,
      );
    }
  }
}

// 动态计算浮层位置（Teleport 到 body 后使用 fixed 定位）
function updatePosition() {
  if (!timePickerRef.value) return;
  const rect = timePickerRef.value.getBoundingClientRect();

  // 若触发器滚动出当前可视区域，自动关闭
  if (rect.bottom < 0 || rect.top > window.innerHeight) {
    onClose();
    return;
  }

  const panelWidth = 196;
  const panelHeight = dropdownRef.value?.offsetHeight || 270;
  const gap = 4;
  const padding = 12;

  // 纵向计算：下方空间不足且上方空间更大时向上展开
  const spaceBelow = window.innerHeight - rect.bottom - padding;
  const spaceAbove = rect.top - padding;
  let top = 0;

  if (spaceBelow < panelHeight && spaceAbove > spaceBelow) {
    top = Math.max(padding, rect.top - panelHeight - gap);
  } else {
    top = rect.bottom + gap;
  }

  // 横向计算：默认与触发器左对齐，右侧超出视口时向左靠齐
  let left = rect.left;
  if (left + panelWidth > window.innerWidth - padding) {
    left = Math.max(padding, rect.right - panelWidth);
  }
  if (left < padding) {
    left = padding;
  }

  dropdownPos.value = {
    top: Math.round(top),
    left: Math.round(left),
  };
}

function onOpen() {
  isOpen.value = true;
  nextTick(() => {
    updatePosition();
    scrollColumnsToSelected();
  });
  window.addEventListener("scroll", updatePosition, true);
  window.addEventListener("resize", updatePosition);
}

function onClose() {
  isOpen.value = false;
  window.removeEventListener("scroll", updatePosition, true);
  window.removeEventListener("resize", updatePosition);
}

function toggleDropdown() {
  if (props.disabled) return;
  if (isOpen.value) {
    onClose();
  } else {
    onOpen();
  }
}

function emitTime(h, m) {
  const timeStr = `${h}:${m}`;
  emit("update:modelValue", timeStr);
  emit("change", timeStr);
}

function selectHour(h, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  const m = selectedMinute.value || "00";
  emitTime(h, m);
}

function selectMinute(m, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  let h = selectedHour.value;
  if (h === null) {
    const now = new Date();
    h = String(now.getHours()).padStart(2, "0");
  }
  emitTime(h, m);
}

function selectNow(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  const d = new Date();
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  emitTime(h, m);
  onClose();
}

function handleConfirm(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (!props.modelValue) {
    selectNow(e);
  } else {
    onClose();
  }
}

function handleClear(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  emit("update:modelValue", props.clearValue);
  emit("change", props.clearValue);
  emit("clear");
  onClose();
}

// 处理点击外部与按键关闭
function handleClickOutside(event) {
  if (!isOpen.value) return;
  const clickedTrigger = timePickerRef.value && timePickerRef.value.contains(event.target);
  const clickedDropdown = dropdownRef.value && dropdownRef.value.contains(event.target);
  if (!clickedTrigger && !clickedDropdown) {
    onClose();
  }
}

function handleKeydown(event) {
  if (event.key === "Escape" && isOpen.value) {
    onClose();
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", handleClickOutside);
  document.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleClickOutside);
  document.removeEventListener("keydown", handleKeydown);
  window.removeEventListener("scroll", updatePosition, true);
  window.removeEventListener("resize", updatePosition);
});
</script>

<template>
  <div
    ref="timePickerRef"
    class="custom-time-picker"
    :class="{
      'is-disabled': disabled,
      'can-clear': canClear,
      'is-open': isOpen,
    }"
  >
    <div
      class="custom-time-picker-trigger"
      :class="{ 'is-disabled': disabled }"
      :tabindex="disabled ? -1 : 0"
      role="combobox"
      :aria-expanded="isOpen"
      @click="toggleDropdown"
    >
      <span
        class="custom-time-picker-label"
        :class="{ 'is-placeholder': !hasValue }"
      >
        {{ displayLabel }}
      </span>

      <div class="custom-time-picker-actions">
        <button
          v-if="canClear"
          type="button"
          class="custom-time-picker-clear-btn"
          title="清除"
          aria-label="清除时间"
          @pointerdown.stop
          @touchstart.stop
          @click.stop.prevent="handleClear"
        >
          <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
          </svg>
        </button>

        <span class="custom-time-picker-icon" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
        </span>
      </div>
    </div>

    <!-- Teleport 到 body，彻底脱离父级 overflow 裁剪与层叠上下文限制 -->
    <Teleport to="body">
      <transition name="ctp-fade">
        <div
          v-if="isOpen"
          ref="dropdownRef"
          class="custom-time-picker-dropdown"
          :style="{
            position: 'fixed',
            top: `${dropdownPos.top}px`,
            left: `${dropdownPos.left}px`,
            zIndex: 1000,
          }"
          @click.stop
        >
          <div class="time-header">
            <span class="time-col-title">时</span>
            <span class="time-col-title">分</span>
          </div>

          <div class="time-body">
            <!-- 小时列 -->
            <div ref="hoursColRef" class="time-column">
              <button
                v-for="h in hoursList"
                :key="h"
                type="button"
                class="time-cell"
                :class="{ 'is-selected': h === selectedHour }"
                @click="selectHour(h, $event)"
              >
                {{ h }}
              </button>
            </div>

            <!-- 分钟列 -->
            <div ref="minutesColRef" class="time-column">
              <button
                v-for="m in minutesList"
                :key="m"
                type="button"
                class="time-cell"
                :class="{ 'is-selected': m === selectedMinute }"
                @click="selectMinute(m, $event)"
              >
                {{ m }}
              </button>
            </div>
          </div>

          <div class="time-footer">
            <button
              type="button"
              class="quick-btn"
              @click="selectNow($event)"
            >
              此刻
            </button>
            <div class="footer-actions">
              <button
                v-if="clearable"
                type="button"
                class="quick-btn clear"
                @click="handleClear($event)"
              >
                清空
              </button>
              <button
                type="button"
                class="quick-btn confirm"
                @click="handleConfirm($event)"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<style>
/* =====================================================================
 * HeadlessTimePicker · iOS 风格（滚轮）
 * - 触发器沿用 .custom-time-picker-* 类名（父组件通过 :deep() 覆盖布局）
 * - 面板内部类名统一收拢在 .custom-time-picker-dropdown 之下，避免全局泄漏
 * - 面板 Teleport 到 body，因此本样式块必须保持非 scoped
 * ===================================================================== */

.custom-time-picker {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

/* ---------------- 触发器 ---------------- */
.custom-time-picker-trigger {
  width: 100%;
  height: 44px;
  box-sizing: border-box;
  padding: 0 10px 0 12px;
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text);
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
  outline: none;
  text-align: left;
  transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.custom-time-picker-trigger:hover {
  background: var(--ios-separator);
}

.custom-time-picker-trigger:focus-visible,
.custom-time-picker.is-open .custom-time-picker-trigger {
  border-color: var(--ios-blue);
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.custom-time-picker-trigger.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-time-picker-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0.5px;
}

.custom-time-picker-label.is-placeholder {
  color: var(--ios-gray);
  font-weight: 400;
}

.custom-time-picker-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-shrink: 0;
}

.custom-time-picker-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--ios-gray);
  transition: color 0.18s ease;
}

.custom-time-picker.is-open .custom-time-picker-icon {
  color: var(--ios-blue);
}

.custom-time-picker-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: var(--ios-separator);
  color: var(--ios-gray);
  cursor: pointer;
  outline: none;
  transition: color 0.18s ease, background-color 0.18s ease;
}

.custom-time-picker-clear-btn:hover {
  color: var(--text);
  background: var(--ios-fill);
}

/* ---------------- 浮层面板 ---------------- */
.custom-time-picker-dropdown {
  width: 280px;
  max-width: min(280px, calc(100vw - 24px));
  box-sizing: border-box;
  padding: 14px;
  border: 1px solid var(--ios-card-border);
  border-radius: 18px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  backdrop-filter: saturate(180%) blur(24px);
  box-shadow: var(--ios-shadow-panel);
  user-select: none;
  outline: none;
  overflow: hidden;
}

/* ---------------- 列标题 ---------------- */
.custom-time-picker-dropdown .time-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding-bottom: 10px;
}

.custom-time-picker-dropdown .time-col-title {
  min-width: 44px;
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ios-gray);
}

/* ---------------- 滚轮：中间选中带 + 上下渐隐 ---------------- */
.custom-time-picker-dropdown .time-body {
  position: relative;
  display: flex;
  gap: 10px;
  height: 208px;
  padding: 4px;
  border-radius: 14px;
  background: var(--ios-fill);
}

/* 中间选中带（iOS 滚轮的高亮条） */
.custom-time-picker-dropdown .time-body::before {
  content: "";
  position: absolute;
  left: 6px;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  height: 40px;
  border-radius: 10px;
  background: var(--ios-card-bg);
  border: 1px solid var(--ios-card-border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  pointer-events: none;
}

.custom-time-picker-dropdown .time-column {
  position: relative;
  z-index: 1;
  flex: 1;
  /* 上下各留 80px（容器 200px 的一半减半格），保证首尾项也能滚到正中 */
  padding: 80px 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  scroll-behavior: smooth;
  scroll-snap-type: y mandatory;
  -webkit-mask-image: linear-gradient(
    to bottom,
    transparent 0,
    #000 22%,
    #000 78%,
    transparent 100%
  );
  mask-image: linear-gradient(
    to bottom,
    transparent 0,
    #000 22%,
    #000 78%,
    transparent 100%
  );
}

.custom-time-picker-dropdown .time-column::-webkit-scrollbar {
  display: none;
}

.custom-time-picker-dropdown .time-cell {
  height: 40px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--ios-gray);
  font-size: 17px;
  font-weight: 500;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  outline: none;
  scroll-snap-align: center;
  letter-spacing: 0.5px;
  font-variant-numeric: tabular-nums;
  transition: color 0.18s ease, font-size 0.18s ease;
}

.custom-time-picker-dropdown .time-cell:hover {
  color: var(--text);
}

.custom-time-picker-dropdown .time-cell.is-selected {
  color: var(--text);
  font-weight: 700;
  font-size: 19px;
}

/* ---------------- 底部操作栏 ---------------- */
.custom-time-picker-dropdown .time-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--ios-separator);
}

.custom-time-picker-dropdown .footer-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.custom-time-picker-dropdown .quick-btn {
  border: none;
  background: transparent;
  padding: 7px 12px;
  border-radius: 10px;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--ios-blue);
  cursor: pointer;
  outline: none;
  transition: background-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.custom-time-picker-dropdown .quick-btn:hover {
  background: var(--ios-fill);
}

.custom-time-picker-dropdown .quick-btn:active {
  transform: scale(0.96);
}

.custom-time-picker-dropdown .quick-btn.confirm {
  background: var(--ios-blue);
  color: #fff;
}

.custom-time-picker-dropdown .quick-btn.confirm:hover {
  background: #0069d9;
}

.custom-time-picker-dropdown .quick-btn.clear {
  color: var(--ios-red);
}

.custom-time-picker-dropdown .quick-btn.clear:hover {
  background: var(--ios-red-soft);
}

/* ---------------- 浮层动效 ---------------- */
.ctp-fade-enter-active,
.ctp-fade-leave-active {
  transition: opacity 0.16s ease, transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}

.ctp-fade-enter-from,
.ctp-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}

@media (prefers-reduced-motion: reduce) {
  .ctp-fade-enter-active,
  .ctp-fade-leave-active {
    transition: none;
  }
}
</style>
