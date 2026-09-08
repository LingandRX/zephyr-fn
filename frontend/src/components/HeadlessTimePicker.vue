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
      <transition name="dropdown-fade">
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
/* iOS 风格时间选择器 */
.custom-time-picker {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

.custom-time-picker-trigger {
  width: 100%;
  height: 44px;
  box-sizing: border-box;
  padding: 0 12px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
  text-align: left;
}

.custom-time-picker-trigger:hover {
  border-color: var(--primary);
  background: var(--card);
}

.custom-time-picker-trigger:focus-visible,
.custom-time-picker.is-open .custom-time-picker-trigger {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(var(--primary-rgb), 0.15);
}

.custom-time-picker-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0.5px;
}

.custom-time-picker-label.is-placeholder {
  color: var(--muted);
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
  color: var(--muted);
  cursor: pointer;
  transition: color 0.2s ease;
}

.custom-time-picker.is-open .custom-time-picker-icon {
  color: var(--primary);
}

.custom-time-picker-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: var(--card);
  border-radius: 50%;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
}

.custom-time-picker-clear-btn:hover {
  color: var(--text);
  background: var(--border);
  transform: scale(1.05);
}

.custom-time-picker-trigger.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--card-2);
}

/* iOS 风格下拉面板 */
.custom-time-picker-dropdown {
  width: 280px;
  max-width: min(280px, calc(100vw - 24px));
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(0, 0, 0, 0.05);
  box-sizing: border-box;
  padding: 16px;
  user-select: none;
  outline: none;
  overflow: hidden;
}

/* iOS 风格头部 */
.time-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding-bottom: 12px;
  margin-bottom: 8px;
}

.time-col-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  min-width: 40px;
  text-align: center;
}

/* iOS 风格滚轮容器 */
.time-body {
  display: flex;
  gap: 12px;
  height: 200px;
  background: var(--bg-2);
  border-radius: 12px;
  padding: 8px;
  position: relative;
}

/* iOS 风格滚轮列 */
.time-column {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  scroll-behavior: smooth;
  scroll-snap-type: y mandatory;
}

.time-column::-webkit-scrollbar {
  display: none;
}

/* iOS 风格滚轮单元格 */
.time-cell {
  height: 40px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 18px;
  font-weight: 500;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 0;
  outline: none;
  scroll-snap-align: center;
  letter-spacing: 0.5px;
}

.time-cell:hover {
  background-color: rgba(var(--primary-rgb), 0.1);
  color: var(--primary);
  transform: scale(1.02);
}

.time-cell.is-selected {
  background: var(--primary);
  color: #fff;
  font-weight: 600;
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(var(--primary-rgb), 0.3);
}

/* iOS 风格底部 */
.time-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.footer-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.quick-btn {
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 10px;
  transition: all 0.2s ease;
  outline: none;
  min-width: 48px;
  text-align: center;
}

.quick-btn:hover {
  background-color: var(--card-2);
  color: var(--text);
  transform: translateY(-1px);
}

.quick-btn:active {
  transform: translateY(0);
}

.quick-btn.confirm {
  color: #fff;
  background: var(--primary);
  font-weight: 600;
}

.quick-btn.confirm:hover {
  background: var(--primary-2);
  box-shadow: 0 4px 12px rgba(var(--primary-rgb), 0.3);
}

.quick-btn.clear {
  color: var(--red);
}

.quick-btn.clear:hover {
  background: rgba(239, 68, 68, 0.1);
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

/* iOS 风格滚动指示器 */
.time-body::before,
.time-body::after {
  content: "";
  position: absolute;
  left: 8px;
  right: 8px;
  height: 40px;
  pointer-events: none;
  z-index: 1;
}

.time-body::before {
  top: 8px;
  background: linear-gradient(to bottom, var(--bg-2), transparent);
  border-radius: 12px 12px 0 0;
}

.time-body::after {
  bottom: 8px;
  background: linear-gradient(to top, var(--bg-2), transparent);
  border-radius: 0 0 12px 12px;
}
</style>
