<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from "vue";

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

const isOpen = ref(false);
const timePickerRef = ref(null);
const dropdownRef = ref(null);
const hoursColRef = ref(null);
const minutesColRef = ref(null);
const dropdownPos = ref({ top: 0, left: 0, placement: "bottom" });

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

function updatePosition() {
  if (!isOpen.value || !timePickerRef.value) return;
  const rect = timePickerRef.value.getBoundingClientRect();

  // 若触发器移出可视区域，自动关闭面板
  if (rect.bottom < 0 || rect.top > window.innerHeight) {
    closeDropdown();
    return;
  }

  const panelWidth = 196;
  const panelHeight = dropdownRef.value?.offsetHeight || 260;
  const gap = 4;
  const padding = 12;

  // 纵向计算：下方空间不足且上方空间更大时向上展开
  const spaceBelow = window.innerHeight - rect.bottom - padding;
  const spaceAbove = rect.top - padding;
  let top = 0;
  let placement = "bottom";

  if (spaceBelow < panelHeight && spaceAbove > spaceBelow) {
    placement = "top";
    top = Math.max(padding, rect.top - panelHeight - gap);
  } else {
    placement = "bottom";
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
    placement,
  };
}

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

watch(isOpen, async (open) => {
  if (open) {
    await nextTick();
    updatePosition();
    scrollColumnsToSelected();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
  } else {
    window.removeEventListener("scroll", updatePosition, true);
    window.removeEventListener("resize", updatePosition);
  }
});

function toggleDropdown() {
  if (props.disabled) return;
  isOpen.value = !isOpen.value;
}

function closeDropdown() {
  isOpen.value = false;
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
  closeDropdown();
}

function handleConfirm(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (!props.modelValue) {
    selectNow(e);
  } else {
    closeDropdown();
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
  closeDropdown();
}

function handleKeydown(e) {
  if (props.disabled) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    toggleDropdown();
  } else if (e.key === "Escape") {
    closeDropdown();
  }
}

function handleClickOutside(event) {
  if (!isOpen.value) return;
  const clickedTrigger = timePickerRef.value && timePickerRef.value.contains(event.target);
  const clickedDropdown = dropdownRef.value && dropdownRef.value.contains(event.target);
  if (!clickedTrigger && !clickedDropdown) {
    closeDropdown();
  }
}

onMounted(() => {
  if (typeof document !== "undefined") {
    document.addEventListener("pointerdown", handleClickOutside);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("scroll", updatePosition, true);
  window.removeEventListener("resize", updatePosition);
  if (typeof document !== "undefined") {
    document.removeEventListener("pointerdown", handleClickOutside);
  }
});
</script>

<template>
  <div
    ref="timePickerRef"
    class="custom-time-picker"
    :class="{ 'is-open': isOpen, 'is-disabled': disabled, 'can-clear': canClear }"
    @keydown="handleKeydown"
  >
    <div
      class="custom-time-picker-trigger"
      :class="{ 'is-disabled': disabled }"
      :tabindex="disabled ? -1 : 0"
      :aria-expanded="isOpen"
      role="combobox"
      @click="toggleDropdown"
    >
      <span class="custom-time-picker-label" :class="{ 'is-placeholder': !hasValue && placeholder }">
        {{ displayLabel }}
      </span>

      <div class="custom-time-picker-actions" @click.stop>
        <button
          v-if="canClear"
          type="button"
          class="custom-time-picker-clear-btn"
          title="清除"
          aria-label="清除所选时间"
          @pointerdown.stop
          @touchstart.stop
          @click.stop.prevent="handleClear"
        >
          <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
          </svg>
        </button>
        <span class="custom-time-picker-icon" aria-hidden="true" @click.stop="toggleDropdown">
          <svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64z m0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"/>
            <path d="M686.4 636.1L544 493.7V256c0-17.7-14.3-32-32-32s-32 14.3-32 32v256c0 8.5 3.4 16.6 9.4 22.6l150.4 150.4c12.5 12.5 32.8 12.5 45.3 0 12.4-12.5 12.4-32.8-0.7-44.9z"/>
          </svg>
        </span>
      </div>
    </div>

    <!-- Teleport 到 body，彻底脱离父级 overflow 裁剪 -->
    <Teleport to="body">
      <transition name="dropdown-fade">
        <div
          v-if="isOpen"
          ref="dropdownRef"
          class="custom-time-picker-dropdown"
          :class="[`placement-${dropdownPos.placement}`]"
          :style="{
            position: 'fixed',
            top: `${dropdownPos.top}px`,
            left: `${dropdownPos.left}px`,
            zIndex: 1000,
          }"
          @click.stop
        >
          <!-- 头部时分指示 -->
          <div class="time-header">
            <span class="time-col-title">时</span>
            <span class="time-col-title">分</span>
          </div>

          <!-- 时/分 两列滚动区 -->
          <div class="time-body">
            <div ref="hoursColRef" class="time-column">
              <button
                v-for="h in hoursList"
                :key="h"
                type="button"
                class="time-cell"
                :class="{ 'is-selected': h === selectedHour }"
                @click.stop="selectHour(h, $event)"
              >
                {{ h }}
              </button>
            </div>
            <div ref="minutesColRef" class="time-column">
              <button
                v-for="m in minutesList"
                :key="m"
                type="button"
                class="time-cell"
                :class="{ 'is-selected': m === selectedMinute }"
                @click.stop="selectMinute(m, $event)"
              >
                {{ m }}
              </button>
            </div>
          </div>

          <!-- 底部操作栏 -->
          <div class="time-footer">
            <button type="button" class="quick-btn" @click.stop="selectNow">此刻</button>
            <div class="footer-actions">
              <button v-if="canClear" type="button" class="quick-btn clear" @click.stop="handleClear">清除</button>
              <button type="button" class="quick-btn confirm" @click.stop="handleConfirm">确定</button>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<style scoped>
.custom-time-picker {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

.custom-time-picker.is-open {
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
.custom-time-picker.is-open .custom-time-picker-trigger {
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

.custom-time-picker.is-open .custom-time-picker-icon {
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

/* 下拉时间面板 (Teleport 挂载到 body) */
.custom-time-picker-dropdown {
  width: 196px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  box-sizing: border-box;
  padding: 8px 10px 10px;
  user-select: none;
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

/* 细长自定义滚动条 (WebKit) */
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
