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

const isOpen = ref(false);
const datePickerRef = ref(null);
const dropdownRef = ref(null);
const dropdownPos = ref({ top: 0, left: 0, placement: "bottom" });
const viewMode = ref(props.type === "month" ? "month" : "date"); // 'date' | 'month'

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

  const firstDayOfWeek = new Date(y, m - 1, 1).getDay(); // 0(Sun) - 6(Sat)
  // 周一转换为 0，周日转换为 6
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

function updatePosition() {
  if (!isOpen.value || !datePickerRef.value) return;
  const rect = datePickerRef.value.getBoundingClientRect();

  // 若触发器移出可视区域，自动关闭面板
  if (rect.bottom < 0 || rect.top > window.innerHeight) {
    closeDropdown();
    return;
  }

  const panelWidth = 280;
  const panelHeight = dropdownRef.value?.offsetHeight || 310;
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

watch(isOpen, async (open) => {
  if (open) {
    viewMode.value = props.type === "month" ? "month" : "date";
    await nextTick();
    updatePosition();
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
  if (isOpen.value) {
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
  }
}

function closeDropdown() {
  isOpen.value = false;
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
  closeDropdown();
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
    closeDropdown();
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
    closeDropdown();
  } else {
    const todayStr = formatYearMonthDay(t.year, t.month, t.day);
    emit("update:modelValue", todayStr);
    emit("change", todayStr);
    closeDropdown();
  }
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
    closeDropdown();
  } else {
    emit("update:modelValue", props.clearValue);
    emit("change", props.clearValue);
    emit("clear");
    closeDropdown();
  }
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
  const clickedTrigger = datePickerRef.value && datePickerRef.value.contains(event.target);
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
    ref="datePickerRef"
    class="custom-date-picker"
    :class="{ 'is-open': isOpen, 'is-disabled': disabled, 'can-clear': canClear }"
    @keydown="handleKeydown"
  >
    <div
      class="custom-date-picker-trigger"
      :class="{ 'is-disabled': disabled }"
      :tabindex="disabled ? -1 : 0"
      :aria-expanded="isOpen"
      role="combobox"
      @click="toggleDropdown"
    >
      <span class="custom-date-picker-label" :class="{ 'is-placeholder': !modelValue && placeholder }">
        {{ displayLabel }}
      </span>

      <div class="custom-date-picker-actions" @click.stop>
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
            <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
          </svg>
        </button>
        <span class="custom-date-picker-icon" aria-hidden="true" @click.stop="toggleDropdown">
          <svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M832 128H768V64c0-17.7-14.3-32-32-32s-32 14.3-32 32v64H320V64c0-17.7-14.3-32-32-32s-32 14.3-32 32v64H192c-53 0-96 43-96 96v640c0 53 43 96 96 96h640c53 0 96-43 96-96V224c0-53-43-96-96-96z m32 736c0 17.7-14.3 32-32 32H192c-17.7 0-32-14.3-32-32V384h704v480z m0-544H160v-96c0-17.7 14.3-32 32-32h64v64c0 17.7 14.3 32 32 32s32-14.3 32-32V192h384v64c0 17.7 14.3 32 32 32s32-14.3 32-32V192h64c17.7 0 32 14.3 32 32v96z" />
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
          class="custom-date-picker-dropdown"
          :class="[`placement-${dropdownPos.placement}`]"
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
            <!-- 日期模式下的头部 -->
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
                class="calendar-title-btn"
                title="选择月份"
                @click.stop="viewMode = 'month'"
              >
                {{ currentYear }}年 {{ currentMonth }}月
                <span class="title-arrow">▾</span>
              </button>

              <div class="nav-btn-group">
                <button type="button" class="nav-btn" title="下个月" @click.stop="nextMonth">
                  <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                    <path d="M384 768a32 32 0 0 1-22.6-54.6L636.8 512 361.4 236.6a32 32 0 1 1 45.2-45.2l320 320a32 32 0 0 1 0 45.2l-320 320a32 32 0 0 1-22.6 9.4z" />
                  </svg>
                </button>
                <button type="button" class="nav-btn" title="下一年" @click.stop="nextYear">
                  <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                    <path d="M444.8 512L169.6 234.666667c-12.8-12.8-12.8-32 0-44.8s32-12.8 44.8 0l297.6 299.733333c12.8 12.8 12.8 32 0 44.8l-297.6 299.733333c-12.8 12.8-32 12.8-44.8 0s-12.8-32 0-44.8L444.8 512z M679.466667 512L404.266667 234.666667c-12.8-12.8-12.8-32 0-44.8s32-12.8 44.8 0l297.6 299.733333c12.8 12.8 12.8 32 0 44.8l-297.6 299.733333c-12.8 12.8-32 12.8-44.8 0s-12.8-32 0-44.8L679.466667 512z"/>
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

              <div class="calendar-title">
                {{ currentYear }}年
              </div>

              <button type="button" class="nav-btn" title="下一年" @click.stop="nextYear">
                <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                  <path d="M444.8 512L169.6 234.666667c-12.8-12.8-12.8-32 0-44.8s32-12.8 44.8 0l297.6 299.733333c12.8 12.8 12.8 32 0 44.8l-297.6 299.733333c-12.8 12.8-32 12.8-44.8 0s-12.8-32 0-44.8L444.8 512z M679.466667 512L404.266667 234.666667c-12.8-12.8-12.8-32 0-44.8s32-12.8 44.8 0l297.6 299.733333c12.8 12.8 12.8 32 0 44.8l-297.6 299.733333c-12.8 12.8-32 12.8-44.8 0s-12.8-32 0-44.8L679.466667 512z"/>
                </svg>
              </button>
            </template>
          </div>

          <!-- 日期视图 -->
          <template v-if="viewMode === 'date'">
            <!-- 星期标题行 -->
            <div class="calendar-weekdays">
              <span v-for="w in weekdays" :key="w" class="weekday-cell">{{ w }}</span>
            </div>

            <!-- 日期网格 -->
            <div class="calendar-grid">
              <button
                v-for="d in calendarDays"
                :key="d.dateStr"
                type="button"
                class="day-cell"
                :class="{
                  'is-current-month': d.isCurrentMonth,
                  'is-other-month': !d.isCurrentMonth,
                  'is-today': d.isToday,
                  'is-selected': d.isSelected,
                }"
                @click.stop="selectDay(d, $event)"
              >
                {{ d.day }}
              </button>
            </div>
          </template>

          <!-- 月份视图 (4列 x 3行) -->
          <template v-else>
            <div class="calendar-month-grid">
              <button
                v-for="m in 12"
                :key="m"
                type="button"
                class="month-cell"
                :class="{
                  'is-this-month': isThisMonth(m),
                  'is-selected': isMonthSelected(m),
                }"
                @click.stop="selectMonth(m, $event)"
              >
                <span class="month-text">{{ m }}月</span>
                <span v-if="isThisMonth(m) && !isMonthSelected(m)" class="this-month-dot" title="本月"></span>
              </button>
            </div>
          </template>

          <!-- 日历快捷底部栏 -->
          <div class="calendar-footer">
            <button type="button" class="quick-btn" @click.stop="selectCurrent">
              {{ type === 'month' ? '本月' : '今天' }}
            </button>
            <button v-if="canClear" type="button" class="quick-btn clear" @click.stop="handleClear">清除</button>
          </div>
      </div>
    </transition>
    </Teleport>
  </div>
</template>

<style scoped>
.custom-date-picker {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

.custom-date-picker.is-open {
  z-index: 50;
}

.custom-date-picker-trigger {
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

.custom-date-picker-trigger:focus-visible,
.custom-date-picker.is-open .custom-date-picker-trigger {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(var(--primary-rgb), 0.2);
}

.custom-date-picker-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-date-picker-label.is-placeholder {
  color: var(--muted);
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
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s ease;
}

.custom-date-picker.is-open .custom-date-picker-icon {
  color: var(--primary);
}

.custom-date-picker-clear-btn {
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

.custom-date-picker-clear-btn:hover {
  color: var(--text);
  background-color: var(--card);
}

.custom-date-picker-trigger.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 下拉日历卡片 (Teleport 挂载到 body) */
.custom-date-picker-dropdown {
  width: 280px;
  max-width: calc(100vw - 24px);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  box-sizing: border-box;
  padding: 12px;
  user-select: none;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.calendar-title {
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--text);
}

.calendar-title-btn {
  border: none;
  background: transparent;
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--text);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.calendar-title-btn:hover {
  background-color: var(--card-2);
  color: var(--primary);
}

.title-arrow {
  font-size: 10px;
  color: var(--muted);
}

.nav-btn-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 4px;
  color: var(--muted);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.nav-btn:hover {
  background-color: var(--card-2);
  color: var(--text);
}

.calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 6px;
  text-align: center;
}

.weekday-cell {
  font-size: 11px;
  color: var(--muted);
  font-weight: 500;
  padding: 2px 0;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.day-cell {
  aspect-ratio: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  padding: 0;
  margin: 0;
  transition: background-color 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}

.day-cell:hover:not(.is-selected) {
  background-color: var(--card-2);
}

.day-cell.is-other-month {
  color: var(--muted);
  opacity: 0.35;
}

.day-cell.is-today:not(.is-selected) {
  border: 1px solid var(--primary);
  font-weight: 600;
}

.day-cell.is-selected {
  background-color: var(--primary) !important;
  color: #ffffff !important;
  font-weight: 600;
}

/* 月份 4x3 网格 */
.calendar-month-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  margin: 6px 0;
}

.month-cell {
  position: relative;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  background: var(--card-2);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.month-cell:hover:not(.is-selected) {
  border-color: var(--border);
  color: var(--primary);
}

.month-cell.is-this-month:not(.is-selected) {
  border-color: var(--amber);
  color: var(--amber);
  font-weight: 600;
}

.month-cell.is-selected {
  background: var(--primary) !important;
  color: #ffffff !important;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(var(--primary-rgb), 0.3);
}

.this-month-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--amber);
}

.calendar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.quick-btn {
  padding: 4px 8px;
  border: none;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.15s ease;
}

.quick-btn:hover {
  background-color: var(--card-2);
}

.quick-btn.clear {
  color: var(--muted);
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

.custom-date-picker-dropdown.placement-top.dropdown-fade-enter-from,
.custom-date-picker-dropdown.placement-top.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
