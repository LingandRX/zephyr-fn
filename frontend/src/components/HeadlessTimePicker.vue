<script setup>
import { computed, ref, nextTick, watch } from "vue";
import {
  Popover,
  PopoverButton,
  PopoverPanel,
} from "@headlessui/vue";

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

const hoursColRef = ref(null);
const minutesColRef = ref(null);

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

function onOpen() {
  nextTick(() => {
    scrollColumnsToSelected();
  });
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

function selectNow(closeFn, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  const d = new Date();
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  emitTime(h, m);
  if (closeFn) closeFn();
}

function handleConfirm(closeFn, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (!props.modelValue) {
    selectNow(closeFn, e);
  } else if (closeFn) {
    closeFn();
  }
}

function handleClear(closeFn, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  emit("update:modelValue", props.clearValue);
  emit("change", props.clearValue);
  emit("clear");
  if (closeFn) closeFn();
}
</script>

<template>
  <div
    class="custom-time-picker"
    :class="{ 'is-disabled': disabled, 'can-clear': canClear }"
  >
    <Popover as="div" class="popover-wrapper" v-slot="{ open, close }">
      <PopoverButton
        as="div"
        class="custom-time-picker-trigger"
        :class="{ 'is-disabled': disabled }"
        @click="onOpen"
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
            @click.stop.prevent="handleClear(null, $event)"
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
      </PopoverButton>

      <transition name="dropdown-fade">
        <PopoverPanel class="custom-time-picker-dropdown">
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
              @click="selectNow(close, $event)"
            >
              此刻
            </button>
            <div class="footer-actions">
              <button
                v-if="clearable"
                type="button"
                class="quick-btn clear"
                @click="handleClear(close, $event)"
              >
                清空
              </button>
              <button
                type="button"
                class="quick-btn confirm"
                @click="handleConfirm(close, $event)"
              >
                确定
              </button>
            </div>
          </div>
        </PopoverPanel>
      </transition>
    </Popover>
  </div>
</template>

<style>
.custom-time-picker {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

.popover-wrapper {
  position: relative;
  width: 100%;
}

.custom-time-picker:has([data-headlessui-state*="open"]),
.popover-wrapper[data-headlessui-state*="open"] {
  z-index: 50;
}

.custom-time-picker-trigger {
  width: 100%;
  height: 38px;
  box-sizing: border-box;
  padding: 0 8px 0 12px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: var(--fs-sm);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  text-align: left;
}

.custom-time-picker-trigger:focus-visible,
.custom-time-picker:has([data-headlessui-state*="open"]) .custom-time-picker-trigger,
.popover-wrapper[data-headlessui-state*="open"] .custom-time-picker-trigger {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(var(--primary-rgb), 0.2);
}

.custom-time-picker-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-time-picker-label.is-placeholder {
  color: var(--muted);
}

.custom-time-picker-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-shrink: 0;
}

.custom-time-picker-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s ease;
}

.custom-time-picker:has([data-headlessui-state*="open"]) .custom-time-picker-icon,
.popover-wrapper[data-headlessui-state*="open"] .custom-time-picker-icon {
  color: var(--primary);
}

.custom-time-picker-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 50%;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
  outline: none;
}

.custom-time-picker-clear-btn:hover {
  color: var(--text);
  background-color: var(--card);
}

.custom-time-picker-trigger.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 下拉面板 */
.custom-time-picker-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  width: 196px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  box-sizing: border-box;
  padding: 8px 10px 10px;
  user-select: none;
  z-index: var(--z-notice);
  outline: none;
}

.time-header {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 6px;
}

.time-col-title {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--muted);
}

.time-body {
  display: flex;
  gap: 8px;
  height: 180px;
}

.time-column {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 2px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.time-column::-webkit-scrollbar {
  width: 4px;
}

.time-column::-webkit-scrollbar-track {
  background: transparent;
}

.time-column::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
  transition: background-color 0.15s ease;
}

.time-column::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}

.time-cell {
  height: 28px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: var(--fs-sm);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.15s ease, color 0.15s ease;
  padding: 0;
  outline: none;
}

.time-cell:hover {
  background-color: var(--card-2);
  color: var(--primary);
}

.time-cell.is-selected {
  background: linear-gradient(135deg, var(--grad-a), var(--grad-b));
  color: #fff;
  font-weight: 600;
}

.time-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.footer-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.quick-btn {
  border: none;
  background: transparent;
  font-size: var(--fs-xs);
  color: var(--muted);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  transition: color 0.15s ease, background-color 0.15s ease;
  outline: none;
}

.quick-btn:hover {
  background-color: var(--card-2);
  color: var(--text);
}

.quick-btn.confirm {
  color: var(--primary);
  font-weight: 500;
}

.quick-btn.confirm:hover {
  background-color: var(--card-2);
  color: var(--grad-a);
}

.quick-btn.clear:hover {
  color: var(--red);
}

/* 动效 */
.dropdown-fade-enter-active,
.dropdown-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dropdown-fade-enter-from,
.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
