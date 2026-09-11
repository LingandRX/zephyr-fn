<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from "vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  type: {
    type: String,
    default: "date", // 'date' | 'month'
  },
  placeholder: {
    type: String,
    default: "",
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
  displayFormatter: {
    type: Function,
    default: null,
  },
});

const emit = defineEmits(["update:modelValue", "change", "clear"]);

const viewMode = ref(props.type === "month" ? "month" : "date");
const pickerContainerRef = ref(null);
const dropdownRef = ref(null);
const isOpen = ref(false);
const dropdownPos = ref({ top: 0, left: 0 });

function getTodayParts() {
  const d = new Date();
  return {
    year: d.getFullYear(),
    month: d.getMonth() + 1,
    day: d.getDate(),
  };
}

function formatYearMonthDay(y, m, d) {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

const currentYear = ref(getTodayParts().year);
const currentMonth = ref(getTodayParts().month);

// 当外部 modelValue 变动时若格式有效则同步日历面板年月
watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(val) || /^\d{4}-\d{2}$/.test(val)) {
        const [y, m] = val.split("-").map(Number);
        currentYear.value = y;
        currentMonth.value = m;
      }
    }
  },
  { immediate: true },
);

const hasValue = computed(() => {
  if (props.type === "month") {
    const t = getTodayParts();
    const thisMonthStr = `${t.year}-${String(t.month).padStart(2, "0")}`;
    return Boolean(props.modelValue && props.modelValue !== thisMonthStr);
  }
  return Boolean(props.modelValue && props.modelValue !== props.clearValue);
});

const canClear = computed(() => {
  return props.clearable && !props.disabled && hasValue.value;
});

const defaultPlaceholder = computed(() => {
  return props.placeholder || (props.type === "month" ? "选择月份" : "选择日期");
});

const displayLabel = computed(() => {
  if (props.displayFormatter) {
    return props.displayFormatter(props.modelValue);
  }
  return props.modelValue || defaultPlaceholder.value;
});

const weekdays = ["一", "二", "三", "四", "五", "六", "日"];

// 生成当月 42 格日历矩阵（周一为起始）
const calendarDays = computed(() => {
  const y = currentYear.value;
  const m = currentMonth.value;

  const firstDayOfWeek = new Date(y, m - 1, 1).getDay();
  const startOffset = (firstDayOfWeek + 6) % 7;

  const daysInCurrentMonth = new Date(y, m, 0).getDate();
  const daysInPrevMonth = new Date(y, m - 1, 0).getDate();

  const today = getTodayParts();
  const todayStr = formatYearMonthDay(today.year, today.month, today.day);

  const days = [];

  // 上月补足
  for (let i = startOffset - 1; i >= 0; i--) {
    const dayNum = daysInPrevMonth - i;
    const prevYear = m === 1 ? y - 1 : y;
    const prevMonth = m === 1 ? 12 : m - 1;
    const dateStr = formatYearMonthDay(prevYear, prevMonth, dayNum);
    days.push({
      dateStr,
      day: dayNum,
      isCurrentMonth: false,
      isToday: dateStr === todayStr,
      isSelected: dateStr === props.modelValue,
    });
  }

  // 当月
  for (let d = 1; d <= daysInCurrentMonth; d++) {
    const dateStr = formatYearMonthDay(y, m, d);
    days.push({
      dateStr,
      day: d,
      isCurrentMonth: true,
      isToday: dateStr === todayStr,
      isSelected: dateStr === props.modelValue,
    });
  }

  // 下月补足 42 格
  const remaining = 42 - days.length;
  for (let d = 1; d <= remaining; d++) {
    const nextYear = m === 12 ? y + 1 : y;
    const nextMonth = m === 12 ? 1 : m + 1;
    const dateStr = formatYearMonthDay(nextYear, nextMonth, d);
    days.push({
      dateStr,
      day: d,
      isCurrentMonth: false,
      isToday: dateStr === todayStr,
      isSelected: dateStr === props.modelValue,
    });
  }

  return days;
});

function isThisMonth(m) {
  const t = getTodayParts();
  return t.year === currentYear.value && t.month === m;
}

function isMonthSelected(m) {
  if (!props.modelValue) return false;
  const parts = props.modelValue.split("-").map(Number);
  return parts[0] === currentYear.value && parts[1] === m;
}

// 计算浮层位置（传送到 body 后使用 fixed 定位）
function updatePosition() {
  if (!pickerContainerRef.value) return;
  const rect = pickerContainerRef.value.getBoundingClientRect();
  // 用实测尺寸：iOS 样式改版后面板宽高已变，写死常量会让翻转/贴边判断失准
  const panelWidth = dropdownRef.value?.offsetWidth || 296;
  const panelHeight = dropdownRef.value?.offsetHeight || 340;
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
  viewMode.value = props.type === "month" ? "month" : "date";
  if (props.modelValue && (/^\d{4}-\d{2}-\d{2}$/.test(props.modelValue) || /^\d{4}-\d{2}$/.test(props.modelValue))) {
    const [y, m] = props.modelValue.split("-").map(Number);
    currentYear.value = y;
    currentMonth.value = m;
  } else {
    const t = getTodayParts();
    currentYear.value = t.year;
    currentMonth.value = t.month;
  }
  isOpen.value = true;
  nextTick(() => {
    updatePosition();
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

function prevMonth() {
  if (currentMonth.value === 1) {
    currentYear.value -= 1;
    currentMonth.value = 12;
  } else {
    currentMonth.value -= 1;
  }
}

function nextMonth() {
  if (currentMonth.value === 12) {
    currentYear.value += 1;
    currentMonth.value = 1;
  } else {
    currentMonth.value += 1;
  }
}

function prevYear() {
  currentYear.value -= 1;
}

function nextYear() {
  currentYear.value += 1;
}

function selectDay(dayItem, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  emit("update:modelValue", dayItem.dateStr);
  emit("change", dayItem.dateStr);
  onClose();
}

function selectMonth(m, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  currentMonth.value = m;
  if (props.type === "month") {
    const formattedMonth = `${currentYear.value}-${String(m).padStart(2, "0")}`;
    emit("update:modelValue", formattedMonth);
    emit("change", formattedMonth);
    onClose();
  } else {
    viewMode.value = "date";
  }
}

function selectCurrent(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  const t = getTodayParts();
  currentYear.value = t.year;
  currentMonth.value = t.month;
  if (props.type === "month") {
    const monthStr = `${t.year}-${String(t.month).padStart(2, "0")}`;
    emit("update:modelValue", monthStr);
    emit("change", monthStr);
  } else {
    const todayStr = formatYearMonthDay(t.year, t.month, t.day);
    emit("update:modelValue", todayStr);
    emit("change", todayStr);
  }
  onClose();
}

function handleClear(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  if (props.type === "month") {
    const t = getTodayParts();
    const thisMonthStr = `${t.year}-${String(t.month).padStart(2, "0")}`;
    currentYear.value = t.year;
    currentMonth.value = t.month;
    emit("update:modelValue", thisMonthStr);
    emit("change", thisMonthStr);
    emit("clear");
  } else {
    emit("update:modelValue", props.clearValue);
    emit("change", props.clearValue);
    emit("clear");
  }
  onClose();
}

// 处理点击外部关闭
function handleClickOutside(event) {
  if (!isOpen.value) return;
  const clickedTrigger = pickerContainerRef.value && pickerContainerRef.value.contains(event.target);
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
    ref="pickerContainerRef"
    class="custom-date-picker"
    :class="{
      'is-disabled': disabled,
      'can-clear': canClear,
      'is-open': isOpen,
    }"
  >
    <div
      class="custom-date-picker-trigger"
      :class="{ 'is-disabled': disabled }"
      :tabindex="disabled ? -1 : 0"
      role="combobox"
      :aria-expanded="isOpen"
      @click="toggleDropdown"
    >
      <span
        class="custom-date-picker-label"
        :class="{ 'is-placeholder': !modelValue && placeholder }"
      >
        {{ displayLabel }}
      </span>

      <div class="custom-date-picker-actions">
        <button
          v-if="canClear"
          type="button"
          class="custom-date-picker-clear-btn"
          title="清除"
          aria-label="清除所选日期"
          @pointerdown.stop
          @touchstart.stop
          @click.stop.prevent="handleClear"
        >
          <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
          </svg>
        </button>
        <span class="custom-date-picker-icon" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M832 128H768V64c0-17.7-14.3-32-32-32s-32 14.3-32 32v64H320V64c0-17.7-14.3-32-32-32s-32 14.3-32 32v64H192c-53 0-96 43-96 96v640c0 53 43 96 96 96h640c53 0 96-43 96-96V224c0-53-43-96-96-96z m32 736c0 17.7-14.3 32-32 32H192c-17.7 0-32-14.3-32-32V384h704v480z m0-544H160v-96c0-17.7 14.3-32 32-32h64v64c0 17.7 14.3 32 32 32s32-14.3 32-32V192h384v64c0 17.7 14.3 32 32 32s32-14.3 32-32V192h64c17.7 0 32 14.3 32 32v96z" />
          </svg>
        </span>
      </div>
    </div>

    <!-- Teleport 到 body，彻底脱离父级 overflow 裁剪 -->
    <Teleport to="body">
      <transition name="cdp-fade">
        <div
          v-if="isOpen"
          ref="dropdownRef"
          class="custom-date-picker-dropdown"
          :style="{
            position: 'fixed',
            top: `${dropdownPos.top}px`,
            left: `${dropdownPos.left}px`,
            zIndex: 1000,
          }"
          @click.stop
        >
          <!-- 日历头部导航 -->
          <div class="calendar-header">
            <template v-if="viewMode === 'date'">
              <div class="nav-btn-group">
                <button type="button" class="nav-btn" title="上一年" @click.stop="prevYear">
                  <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                    <path d="M512 512l275.2-277.333333c12.8-12.8 12.8-32 0-44.8s-32-12.8-44.8 0L444.8 489.6c-12.8 12.8-12.8 32 0 44.8l297.6 299.733333c12.8 12.8 32 12.8 44.8 0s12.8-32 0-44.8L512 512z M277.333333 512l275.2-277.333333c12.8-12.8 12.8-32 0-44.8s-32-12.8-44.8 0L210.133333 489.6c-12.8 12.8-12.8 32 0 44.8l297.6 299.733333c12.8 12.8 32 12.8 44.8 0s12.8-32 0-44.8L277.333333 512z"/>
                  </svg>
                </button>
                <button type="button" class="nav-btn" title="上个月" @click.stop="prevMonth">
                  <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                    <path d="M640 768a32 32 0 0 1-22.6-9.4l-320-320a32 32 0 0 1 0-45.2l320-320a32 32 0 1 1 45.2 45.2L387.2 512l275.4 275.4A32 32 0 0 1 640 768z" />
                  </svg>
                </button>
              </div>

              <button
                type="button"
                class="current-period-btn"
                title="切换到月份视图"
                @click.stop="viewMode = 'month'"
              >
                {{ currentYear }}年 {{ currentMonth }}月
              </button>

              <div class="nav-btn-group">
                <button type="button" class="nav-btn" title="下个月" @click.stop="nextMonth">
                  <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                    <path d="M384 768a32 32 0 0 1-22.6-9.4L636.8 512 361.4 236.6a32 32 0 1 1 45.2-45.2l320 320a32 32 0 0 1 0 45.2l-320 320A32 32 0 0 1 384 768z" />
                  </svg>
                </button>
                <button type="button" class="nav-btn" title="下一年" @click.stop="nextYear">
                  <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                    <path d="M512 512L236.8 789.333333c-12.8 12.8-12.8 32 0 44.8s32 12.8 44.8 0L579.2 534.4c12.8-12.8 12.8-32 0-44.8L281.6 189.866667c-12.8-12.8-32-12.8-44.8 0s-12.8 32 0 44.8L512 512z M746.666667 512L471.466667 789.333333c-12.8 12.8-12.8 32 0 44.8s32 12.8 44.8 0l297.6-299.733333c12.8-12.8 12.8-32 0-44.8L516.266667 189.866667c-12.8-12.8-32-12.8-44.8 0s-12.8 32 0 44.8L746.666667 512z"/>
                  </svg>
                </button>
              </div>
            </template>

            <!-- 月份模式下的头部 -->
            <template v-else>
              <button type="button" class="nav-btn" title="上一年" @click.stop="prevYear">
                <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                  <path d="M512 512l275.2-277.333333c12.8-12.8 12.8-32 0-44.8s-32-12.8-44.8 0L444.8 489.6c-12.8 12.8-12.8 32 0 44.8l297.6 299.733333c12.8 12.8 32 12.8 44.8 0s12.8-32 0-44.8L512 512z M277.333333 512l275.2-277.333333c12.8-12.8 12.8-32 0-44.8s-32-12.8-44.8 0L210.133333 489.6c-12.8 12.8-12.8 32 0 44.8l297.6 299.733333c12.8 12.8 32 12.8 44.8 0s12.8-32 0-44.8L277.333333 512z"/>
                </svg>
              </button>
              <span class="year-label">{{ currentYear }}年</span>
              <button type="button" class="nav-btn" title="下一年" @click.stop="nextYear">
                <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                  <path d="M512 512L236.8 789.333333c-12.8 12.8-12.8 32 0 44.8s32 12.8 44.8 0L579.2 534.4c12.8-12.8 12.8-32 0-44.8L281.6 189.866667c-12.8-12.8-32-12.8-44.8 0s-12.8 32 0 44.8L512 512z M746.666667 512L471.466667 789.333333c-12.8 12.8-12.8 32 0 44.8s32 12.8 44.8 0l297.6-299.733333c12.8-12.8 12.8-32 0-44.8L516.266667 189.866667c-12.8-12.8-32-12.8-44.8 0s-12.8 32 0 44.8L746.666667 512z"/>
                </svg>
              </button>
            </template>
          </div>

          <!-- 日期选择面板 -->
          <div v-if="viewMode === 'date'" class="calendar-body">
            <div class="weekdays-grid">
              <span v-for="w in weekdays" :key="w" class="weekday-cell">{{ w }}</span>
            </div>
            <div class="days-grid">
              <button
                v-for="d in calendarDays"
                :key="d.dateStr"
                type="button"
                class="day-cell"
                :class="{
                  'other-month': !d.isCurrentMonth,
                  'is-today': d.isToday,
                  'is-selected': d.isSelected,
                }"
                @click="selectDay(d, $event)"
              >
                {{ d.day }}
              </button>
            </div>
          </div>

          <!-- 月份选择面板 -->
          <div v-else class="months-grid">
            <button
              v-for="m in 12"
              :key="m"
              type="button"
              class="month-cell"
              :class="{
                'this-month': isThisMonth(m),
                'is-selected': isMonthSelected(m),
              }"
              @click="selectMonth(m, $event)"
            >
              {{ m }}月
            </button>
          </div>

          <!-- 底部快捷栏 -->
          <div class="calendar-footer">
            <button
              type="button"
              class="quick-btn"
              @click="selectCurrent($event)"
            >
              {{ type === 'month' ? '本月' : '今天' }}
            </button>
            <button
              v-if="canClear"
              type="button"
              class="quick-btn clear"
              @click="handleClear($event)"
            >
              清除
            </button>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<style>
/* =====================================================================
 * HeadlessDatePicker · iOS 风格
 * - 触发器沿用 .custom-date-picker-* 类名（父组件通过 :deep() 覆盖高度/字号）
 * - 面板内部类名统一收拢在 .custom-date-picker-dropdown 之下，避免全局泄漏
 * - 面板 Teleport 到 body，因此本样式块必须保持非 scoped
 * ===================================================================== */

.custom-date-picker {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

/* ---------------- 触发器 ---------------- */
.custom-date-picker-trigger {
  width: 100%;
  height: 38px;
  box-sizing: border-box;
  padding: 0 10px 0 12px;
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text);
  font-size: var(--fs-sm);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  cursor: pointer;
  outline: none;
  transition: background-color var(--dur-quick) ease, border-color var(--dur-quick) ease, box-shadow var(--dur-quick) ease;
  text-align: left;
}

.custom-date-picker-trigger:hover {
  background: var(--ios-separator);
}

.custom-date-picker-trigger:focus-visible,
.custom-date-picker.is-open .custom-date-picker-trigger {
  border-color: var(--ios-blue);
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.custom-date-picker-trigger.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-date-picker-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-date-picker-label.is-placeholder {
  color: var(--ios-gray);
}

.custom-date-picker-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-shrink: 0;
}

.custom-date-picker-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--ios-gray);
  transition: color var(--dur-quick) ease;
}

.custom-date-picker.is-open .custom-date-picker-icon {
  color: var(--ios-blue);
}

.custom-date-picker-clear-btn {
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
  transition: color var(--dur-quick) ease, background-color var(--dur-quick) ease;
}

.custom-date-picker-clear-btn:hover {
  color: var(--text);
  background: var(--ios-fill);
}

/* ---------------- 浮层面板 ---------------- */
.custom-date-picker-dropdown {
  width: 296px;
  max-width: min(296px, calc(100vw - 24px));
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

/* ---------------- 头部导航 ---------------- */
.custom-date-picker-dropdown .calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 10px;
}

.custom-date-picker-dropdown .nav-btn-group {
  display: flex;
  gap: 4px;
}

.custom-date-picker-dropdown .nav-btn {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--ios-blue);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  outline: none;
  transition: background-color var(--dur-quick) ease, transform var(--dur-quick) ease;
}

.custom-date-picker-dropdown .nav-btn:hover {
  background: var(--ios-fill);
}

.custom-date-picker-dropdown .nav-btn:active {
  transform: scale(0.9);
}

.custom-date-picker-dropdown .current-period-btn {
  border: none;
  background: transparent;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--text);
  cursor: pointer;
  outline: none;
  transition: background-color var(--dur-quick) ease, color var(--dur-quick) ease;
}

.custom-date-picker-dropdown .current-period-btn:hover {
  background: var(--ios-fill);
  color: var(--ios-blue);
}

.custom-date-picker-dropdown .year-label {
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--text);
  padding: 0 6px;
}

/* ---------------- 星期表头 ---------------- */
.custom-date-picker-dropdown .weekdays-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 4px;
}

.custom-date-picker-dropdown .weekday-cell {
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--ios-gray);
  padding: 4px 0 6px;
}

/* ---------------- 日期矩阵：圆形日期 ---------------- */
.custom-date-picker-dropdown .days-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.custom-date-picker-dropdown .day-cell {
  aspect-ratio: 1;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  outline: none;
  transition: background-color var(--dur-fast) ease, color var(--dur-fast) ease, transform var(--dur-fast) ease;
}

.custom-date-picker-dropdown .day-cell:hover {
  background: var(--ios-fill);
}

.custom-date-picker-dropdown .day-cell:active {
  transform: scale(0.92);
}

.custom-date-picker-dropdown .day-cell:focus-visible {
  box-shadow: 0 0 0 2px var(--ios-blue);
}

.custom-date-picker-dropdown .day-cell.other-month {
  color: var(--ios-gray);
  opacity: 0.5;
}

.custom-date-picker-dropdown .day-cell.is-today {
  color: var(--ios-red);
  font-weight: 700;
}

.custom-date-picker-dropdown .day-cell.is-selected {
  background: var(--ios-blue);
  color: #fff !important;
  font-weight: 600;
}

.custom-date-picker-dropdown .day-cell.is-selected.is-today {
  background: var(--ios-red);
}

/* ---------------- 月份矩阵 ---------------- */
.custom-date-picker-dropdown .months-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 6px 0;
}

.custom-date-picker-dropdown .month-cell {
  height: 44px;
  border: none;
  background: var(--ios-fill);
  color: var(--text);
  font-size: var(--fs-sm);
  font-weight: 500;
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  outline: none;
  transition: background-color var(--dur-fast) ease, color var(--dur-fast) ease, transform var(--dur-fast) ease;
}

.custom-date-picker-dropdown .month-cell:hover {
  background: var(--ios-separator);
}

.custom-date-picker-dropdown .month-cell:active {
  transform: scale(0.96);
}

.custom-date-picker-dropdown .month-cell.this-month {
  color: var(--ios-red);
  font-weight: 700;
}

.custom-date-picker-dropdown .month-cell.is-selected {
  background: var(--ios-blue);
  color: #fff !important;
  font-weight: 600;
}

/* ---------------- 底部快捷栏 ---------------- */
.custom-date-picker-dropdown .calendar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--ios-separator);
}

.custom-date-picker-dropdown .quick-btn {
  border: none;
  background: transparent;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--ios-blue);
  cursor: pointer;
  outline: none;
  transition: background-color var(--dur-quick) ease, color var(--dur-quick) ease;
}

.custom-date-picker-dropdown .quick-btn:hover {
  background: var(--ios-fill);
}

.custom-date-picker-dropdown .quick-btn.clear {
  color: var(--ios-red);
}

.custom-date-picker-dropdown .quick-btn.clear:hover {
  background: var(--ios-red-soft);
}

/* ---------------- 浮层动效 ---------------- */
.cdp-fade-enter-active,
.cdp-fade-leave-active {
  transition: opacity var(--dur-fast) ease, transform var(--dur-fast) var(--ease-decelerate);
}

.cdp-fade-enter-from,
.cdp-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}

@media (prefers-reduced-motion: reduce) {
  .cdp-fade-enter-active,
  .cdp-fade-leave-active {
    transition: none;
  }
}
</style>
