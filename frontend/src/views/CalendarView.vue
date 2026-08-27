<script setup>
// 日历视图：按月渲染扣费 / 服务到期事件
import { ref, computed, watch, nextTick, onMounted, onActivated, onBeforeUnmount } from "vue";
import { getCalendar } from "../api.js";
import { toast } from "../ui.js";
import CustomDatePicker from "../components/CustomDatePicker.vue";

const now = new Date();
const calYear = ref(now.getFullYear());
const calMonth = ref(now.getMonth() + 1);
const events = ref([]);
const selectedDateStr = ref(null);
const detailsCardRef = ref(null);
const detailsVisible = ref(false);
const detailsVisibilityReady = ref(false);
let detailsObserver = null;

// 格式化顶部日历年月显示
function formatCalHeader(val) {
  if (!val) return `${calYear.value} 年 ${calMonth.value} 月`;
  const [y, m] = val.split("-").map(Number);
  return `${y} 年 ${m} 月`;
}

const calendarPickerDate = computed({
  get: () => `${calYear.value}-${String(calMonth.value).padStart(2, "0")}`,
  set: (val) => {
    if (!val) return;
    const [y, m] = val.split("-").map(Number);
    const monthChanged = calYear.value !== y || calMonth.value !== m;
    calYear.value = y;
    calMonth.value = m;
    selectedDateStr.value = `${y}-${String(m).padStart(2, "0")}-01`;
    if (monthChanged) {
      loadMonth();
    }
  },
});

// 6 行 7 列 = 42 格
const grid = ref([]);

async function loadMonth() {
  const y = calYear.value;
  const m = calMonth.value;
  const prevY = m === 1 ? y - 1 : y;
  const prevM = m === 1 ? 12 : m - 1;
  const nextY = m === 12 ? y + 1 : y;
  const nextM = m === 12 ? 1 : m + 1;

  try {
    const [prevEvents, curEvents, nextEvents] = await Promise.all([
      getCalendar(prevY, prevM),
      getCalendar(y, m),
      getCalendar(nextY, nextM),
    ]);
    events.value = [...prevEvents, ...curEvents, ...nextEvents];
  } catch (err) {
    toast(err.message, "err");
    events.value = [];
  }
  buildGrid();
}

function buildGrid() {
  const year = calYear.value;
  const month = calMonth.value;
  const byDate = {};
  for (const e of events.value) (byDate[e.date] = byDate[e.date] || []).push(e);

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayStr = today.toISOString().slice(0, 10);

  const first = new Date(year, month - 1, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(year, month, 0).getDate();

  const cells = [];
  // 上月占位
  for (let i = 0; i < startDow; i++) {
    const d = new Date(year, month - 1, -startDow + i + 1);
    const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const dayEvents = byDate[ds] || [];
    cells.push({
      day: d.getDate(),
      dateStr: ds,
      other: true,
      today: ds === todayStr,
      events: dayEvents,
      visibleEvents: dayEvents.slice(0, 2),
      more: dayEvents.length > 2 ? dayEvents.length - 2 : 0,
    });
  }
  // 当月
  for (let day = 1; day <= daysInMonth; day++) {
    const ds = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayEvents = byDate[ds] || [];
    cells.push({
      day,
      dateStr: ds,
      other: false,
      today: ds === todayStr,
      events: dayEvents,
      visibleEvents: dayEvents.slice(0, 2),
      more: dayEvents.length > 2 ? dayEvents.length - 2 : 0,
    });
  }
  // 下月占位至 42 格
  const nextMonthYear = month === 12 ? year + 1 : year;
  const nextMonthNum = month === 12 ? 1 : month + 1;
  for (let i = 1; cells.length < 42; i++) {
    const ds = `${nextMonthYear}-${String(nextMonthNum).padStart(2, "0")}-${String(i).padStart(2, "0")}`;
    const dayEvents = byDate[ds] || [];
    cells.push({
      day: i,
      dateStr: ds,
      other: true,
      today: ds === todayStr,
      events: dayEvents,
      visibleEvents: dayEvents.slice(0, 2),
      more: dayEvents.length > 2 ? dayEvents.length - 2 : 0,
    });
  }

  grid.value = cells;

  // 默认选中今天或当月第一个有事件的日期
  if (!selectedDateStr.value || !selectedDateStr.value.startsWith(`${year}-${String(month).padStart(2, "0")}`)) {
    selectedDateStr.value = todayStr.startsWith(`${year}-${String(month).padStart(2, "0")}`) ? todayStr : null;
  }
}

function selectDay(cell) {
  if (cell.other) {
    const [y, m] = cell.dateStr.split("-").map(Number);
    calYear.value = y;
    calMonth.value = m;
    selectedDateStr.value = cell.dateStr;
    loadMonth();
    return;
  }
  selectedDateStr.value = cell.dateStr;
}

const selectedDayEvents = computed(() => {
  if (!selectedDateStr.value) return [];
  const target = grid.value.find((c) => c.dateStr === selectedDateStr.value);
  return target ? target.events : [];
});

const selectedDayTotal = computed(() => {
  return selectedDayEvents.value.reduce((acc, cur) => acc + (cur.amount || 0), 0);
});
// 明细展开态：选中且有事件的日期（供 details-collapsed 类驱动开合动画）
const detailsOpen = computed(() => !!selectedDateStr.value && selectedDayEvents.value.length > 0);

function observeDetailsCard() {
  detailsObserver?.disconnect();
  detailsObserver = null;
  // 切换日期时先隐藏跳转按钮，等新明细卡片完成可见性检测后再决定是否显示，避免闪烁。
  detailsVisibilityReady.value = false;

  if (!selectedDayEvents.value.length) {
    detailsVisible.value = false;
    return;
  }

  nextTick(() => {
    const card = detailsCardRef.value;
    if (!card) return;

    if (typeof IntersectionObserver === "undefined") {
      detailsVisible.value = false;
      detailsVisibilityReady.value = true;
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (detailsObserver !== observer) return;
      detailsVisible.value = entry.isIntersecting;
      detailsVisibilityReady.value = true;
    }, { threshold: 0.25 });
    detailsObserver = observer;
    observer.observe(card);
  });
}

function scrollToDetails() {
  detailsCardRef.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 关闭扣费明细（浮层/并排两种模式共用）：清空选中日期即可
function closeDetails() {
  selectedDateStr.value = null;
  detailsVisible.value = false;
}

function prevMonth(delta) {
  calMonth.value += delta;
  if (calMonth.value < 1) { calMonth.value = 12; calYear.value--; }
  if (calMonth.value > 12) { calMonth.value = 1; calYear.value++; }
  selectedDateStr.value = `${calYear.value}-${String(calMonth.value).padStart(2, "0")}-01`;
  loadMonth();
}

function goToday() {
  const n = new Date();
  calYear.value = n.getFullYear();
  calMonth.value = n.getMonth() + 1;
  const todayStr = `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
  selectedDateStr.value = todayStr;
  loadMonth();
}

watch(() => [selectedDateStr.value, selectedDayEvents.value.length], observeDetailsCard);
// keep-alive 下「切换回本页」不会重新 onMounted，需在 onActivated 重新拉取当月数据，
// 否则在其他页面新增订阅后切回时日历仍显示旧数据。
onMounted(loadMonth);
onActivated(loadMonth);
onBeforeUnmount(() => detailsObserver?.disconnect());
</script>

<template>
  <div class="page cal-page">
    <div class="cal-head">
      <div class="cal-nav">
        <button class="btn btn-sm" title="上一月" @click="prevMonth(-1)">‹</button>
        <div class="cal-title-wrap">
          <CustomDatePicker
            v-model="calendarPickerDate"
            type="month"
            :clearable="true"
            :display-formatter="formatCalHeader"
            placeholder="选择月份"
            @clear="goToday"
          />
        </div>
        <button class="btn btn-sm" title="下一月" @click="prevMonth(1)">›</button>
        <!-- <button class="btn btn-sm btn-ghost today-btn" @click="goToday">今天</button> -->
      </div>
      <div class="cal-legend">
        <span class="legend-item"><i class="dot dot-due"></i>扣费</span>
        <span class="legend-item"><i class="dot dot-end"></i>服务到期</span>
      </div>
    </div>

    <div class="cal-content">
      <div class="card cal-card">
        <div class="cal-grid">
          <div v-for="(d, i) in ['日', '一', '二', '三', '四', '五', '六']" :key="'dow-' + i" class="cal-dow">{{ d }}</div>
          <div
            v-for="(c, i) in grid"
            :key="c.dateStr"
            class="cal-day"
            :style="{ '--d': 'calc(' + Math.floor(i / 7) * 18 + 'ms)' }"
            :class="{
              other: c.other,
              today: c.today,
              selected: c.dateStr === selectedDateStr && !c.other,
              'has-events': c.events && c.events.length > 0
            }"
            @click="selectDay(c)"
          >
            <div class="cal-day-header">
              <span class="num">{{ c.day }}</span>
              <span v-if="c.today" class="today-tag">今</span>
            </div>

            <!-- 桌面端/宽屏：文字条模式 -->
            <div class="events-wrap desktop-events">
              <template v-if="c.visibleEvents">
                <div
                  v-for="(e, j) in c.visibleEvents"
                  :key="j"
                  class="cal-event"
                  :class="e.event_type === 'service_end' ? 'end' : 'due'"
                  :title="`${e.name} ${e.amount_formatted}`"
                >
                  <span class="event-name">{{ e.name }}</span>
                  <span class="event-amt">{{ e.amount_formatted }}</span>
                </div>
                <div v-if="c.more" class="cal-event more-badge">+{{ c.more }} 项</div>
              </template>
            </div>

            <!-- 移动端：精致圆点模式 -->
            <div class="mobile-dots" v-if="c.events && c.events.length">
              <span
                v-for="(e, j) in c.events.slice(0, 3)"
                :key="j"
                class="mob-dot"
                :class="e.event_type === 'service_end' ? 'dot-end' : 'dot-due'"
              ></span>
              <span v-if="c.events.length > 3" class="mob-dot-more">+</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 选中日期明细：桌面端浮叠在日历右上/并排，窄屏显示在日历下方；
          常驻元素 + details-collapsed 类控制收起态，桌面端开合带平滑动画 -->
      <div
        id="day-details"
        ref="detailsCardRef"
        class="card day-details-card"
        :class="{ 'details-collapsed': !detailsOpen }"
      >
        <!-- 内容容器以日期为 key：切换日期时仅内容淡入，宽度/位置不变 -->
        <div :key="selectedDateStr" class="details-body">
        <div class="details-head">
          <div class="details-date">
            <span class="details-date-label">
              <svg class="detail-cal-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M853.333333 149.333333h-138.666666V106.666667c0-17.066667-14.933333-32-32-32s-32 14.933333-32 32v42.666666h-277.333334V106.666667c0-17.066667-14.933333-32-32-32s-32 14.933333-32 32v42.666666H170.666667c-40.533333 0-74.666667 34.133333-74.666667 74.666667v618.666667C96 883.2 130.133333 917.333333 170.666667 917.333333h682.666666c40.533333 0 74.666667-34.133333 74.666667-74.666666v-618.666667C928 183.466667 893.866667 149.333333 853.333333 149.333333zM170.666667 213.333333h138.666666v64c0 17.066667 14.933333 32 32 32s32-14.933333 32-32v-64h277.333334v64c0 17.066667 14.933333 32 32 32s32-14.933333 32-32v-64H853.333333c6.4 0 10.666667 4.266667 10.666667 10.666667v194.133333c-4.266667-2.133333-6.4-2.133333-10.666667-2.133333H170.666667c-4.266667 0-6.4 0-10.666667 2.133333v-194.133333c0-6.4 4.266667-10.666667 10.666667-10.666667z m682.666666 640H170.666667c-6.4 0-10.666667-4.266667-10.666667-10.666666V477.866667c4.266667 2.133333 6.4 2.133333 10.666667 2.133333h682.666666c4.266667 0 6.4 0 10.666667-2.133333v364.8c0 6.4-4.266667 10.666667-10.666667 10.666666z"/><path d="M384 608h-85.333333c-17.066667 0-32 14.933333-32 32s14.933333 32 32 32h85.333333c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32zM725.333333 608h-192c-17.066667 0-32 14.933333-32 32s14.933333 32 32 32h192c17.066667 0 32-14.933333 32-32s-14.933333-32-32-32z"/></svg>
              {{ selectedDateStr }} 扣费明细
            </span>
            <span class="details-count">共 {{ selectedDayEvents.length }} 笔 (合计 ¥{{ (selectedDayTotal / 100).toFixed(2) }})</span>
          </div>
          <button
            type="button"
            class="details-close"
            title="关闭扣费明细"
            aria-label="关闭扣费明细"
            @click="closeDetails"
          ><svg class="detail-close-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466667 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/></svg></button>
        </div>
        <div class="details-list">
          <div v-for="(e, idx) in selectedDayEvents" :key="idx" class="detail-item">
            <div class="detail-left">
              <span class="detail-dot" :class="e.event_type === 'service_end' ? 'dot-end' : 'dot-due'"></span>
              <span class="detail-name">{{ e.name }}</span>
              <span class="detail-type-tag">{{ e.event_type === 'service_end' ? '服务到期' : '续费扣款' }}</span>
            </div>
            <div class="detail-right">
              <span class="detail-amount">{{ e.amount_formatted }}</span>
            </div>
          </div>
        </div>
        </div>
      </div>
    </div>

    <!-- 窄屏时明细位于日历下方，用浮动按钮提示并快捷跳转 -->
    <button
      v-if="selectedDateStr && selectedDayEvents.length && detailsVisibilityReady && !detailsVisible"
      class="details-jump"
      type="button"
      aria-label="跳转到扣费明细"
      aria-controls="day-details"
      @click="scrollToDetails"
    >
      <span>查看扣费明细</span>
      <span class="details-jump-arrow" aria-hidden="true">↓</span>
    </button>
  </div>
</template>

<style scoped>
.cal-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

/* 顶部导航与图例 */
.cal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  position: relative;
  z-index: 20;
}
.cal-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.cal-title-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-width: 140px;
}
.cal-title-wrap :deep(.custom-date-picker-trigger) {
  height: 32px;
  padding: 0 10px;
  font-weight: 600;
  font-size: var(--fs-md);
  background: var(--card);
}
.cal-title-wrap :deep(.custom-date-picker-trigger:hover) {
  background: var(--bg-2);
}
.today-btn {
  font-size: var(--fs-xs);
  padding: 4px 10px;
}

.cal-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.dot-due { background: var(--amber); }
.dot-end { background: var(--red); }

/* 日历卡片与网格 */
.cal-content {
  /* 单列（堆叠）为基座：日历在上、明细在下（≤1024px）。
     桌面端（≥1025px）在下方 @media 中切换为 flex row 并排：日历在左、明细在右。 */
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.cal-content > .card {
  /* .card 默认带下边距，栅格间距统一交给 cal-content 的 gap */
  margin-bottom: 0;
}
.cal-card {
  padding: 12px;
}
.day-details-card {
  min-width: 0;
  scroll-margin-top: 12px;
}
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
  width: 100%;
}
.cal-dow {
  text-align: center;
  color: var(--muted);
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: 4px 0 8px;
}

/* 单元格严格等宽等高 */
.cal-day {
  min-width: 0;
  height: 96px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px;
  background: var(--bg-2);
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-sizing: border-box;
  overflow: hidden;
  transition: border-color 0.15s ease, background 0.15s ease;
  cursor: pointer;
}
.cal-day:hover {
  border-color: rgba(var(--primary-rgb), 0.4);
}
.cal-day.other {
  opacity: 0.35;
  background: transparent;
  cursor: pointer;
}
.cal-day.other:hover {
  opacity: 0.7;
}
.cal-day.today {
  border-color: var(--primary);
  background: rgba(var(--primary-rgb), 0.05);
}
.cal-day.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary);
}

/* 月切换时格子按行错峰浮现：格子以 dateStr 为 key，切月即重建触发动画 */
@keyframes cal-day-in {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.cal-day {
  animation: cal-day-in 0.3s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: var(--d, 0ms);
}

/* 日期表头 */
.cal-day-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  line-height: 1;
}
.cal-day .num {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}
.cal-day.today .num {
  color: var(--primary);
  font-weight: 700;
}
.today-tag {
  font-size: 10px;
  background: var(--primary);
  color: #fff;
  padding: 1px 4px;
  border-radius: 3px;
  line-height: 1.1;
}

/* 事件文字条 */
.events-wrap {
  display: flex;
  flex-direction: column;
  gap: 3px;
  overflow: hidden;
  flex: 1;
}
.cal-event {
  font-size: 11px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 5px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 4px;
  min-width: 0;
  line-height: 1.2;
}
.cal-event.due {
  border-left: 3px solid var(--amber);
}
.cal-event.end {
  border-left: 3px solid var(--red);
}
.event-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  font-weight: 500;
}
.event-amt {
  flex-shrink: 0;
  color: var(--muted);
  font-size: 10px;
}
.more-badge {
  color: var(--muted);
  font-size: 10px;
  justify-content: center;
  background: transparent;
  border: 1px dashed var(--border);
  padding: 1px 0;
}

/* 移动端圆点显示 */
.mobile-dots {
  display: none;
}

/* 日期明细面板 */
.day-details-card {
  padding: 12px 16px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

/* 收起态基座：≤1024px 堆叠布局下收起即不占位（无动画） */
.day-details-card.details-collapsed {
  display: none;
}

/* 切换日期时明细内容淡入（容器以日期为 key 重建触发） */
.details-body {
  animation: details-body-in 0.18s ease;
}
@keyframes details-body-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.details-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.details-close {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s ease, background 0.15s ease;
}
.detail-close-icon {
  width: 14px;
  height: 14px;
}
.detail-cal-icon {
  width: 14px;
  height: 14px;
  margin-right: 4px;
  vertical-align: -2px;
  flex-shrink: 0;
}
.details-close:hover {
  color: var(--text);
  background: var(--bg-2);
}
.details-date {
  font-size: var(--fs-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}
.details-date > span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.details-count {
  font-size: var(--fs-xs);
  color: var(--muted);
  font-weight: normal;
  flex-shrink: 0;
  white-space: nowrap;
}
.details-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.detail-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.detail-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
}
.detail-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.detail-name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.detail-type-tag {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--bg-2);
  color: var(--muted);
  border-radius: 3px;
  flex-shrink: 0;
}
.detail-amount {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

/* 窄屏快捷跳转按钮：宽屏隐藏，避免影响桌面端右侧明细布局 */
.details-jump {
  display: none;
  position: fixed;
  right: 16px;
  bottom: 24px;
  z-index: 10;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--primary);
  border-radius: 999px;
  padding: 8px 12px;
  background: var(--primary);
  color: #fff;
  box-shadow: 0 6px 18px rgba(var(--primary-rgb), 0.28);
  cursor: pointer;
  font: inherit;
  font-size: var(--fs-xs);
  font-weight: 600;
  white-space: nowrap;
  animation: details-jump-float 1.8s ease-in-out infinite;
}
.details-jump:hover {
  background: var(--primary-2);
}
.details-jump-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  line-height: 1;
  animation: details-jump-arrow 1.1s ease-in-out infinite;
}
@keyframes details-jump-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}
@keyframes details-jump-arrow {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(3px); }
}

/* ---------- 桌面端：视口内一次展示全部 42 格（6 行 × 7 列） ---------- */
/* 桌面端（≥1025px）：flex row 并排 —— 日历在左、明细在右。
   Grid 轨道不可过渡，故用 flex + width 动画：明细栏 0↔340px 平滑展开/收起，
   日历随之连续重排，打开明细时格子不会瞬时变窄。 */
@media (min-width: 1025px) {
  .cal-page {
    flex: 1 1 auto;
    min-height: 0;
    height: 100%;
  }
  .cal-content {
    display: flex;
    flex-direction: row;
    flex: 1 1 auto;
    min-height: 0;
    align-items: stretch;
    gap: 0;
  }
  .cal-card {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    height: 100%;
    overflow: hidden;
  }
  .cal-grid {
    flex: 1 1 auto;
    min-height: 0;
    /* 首行周标题 auto，其余 6 行等分剩余高度，整体撑满卡片 */
    grid-template-rows: auto repeat(6, minmax(0, 1fr));
    align-content: stretch;
  }
  .cal-day {
    height: auto;
    min-height: 0;
    /* 随视口拉伸，同时保留内部文字条的可用高度 */
  }
  .day-details-card {
    flex: 0 0 auto;
    width: 340px;
    min-width: 0;
    max-height: 100%;
    overflow-y: auto;
    scrollbar-width: thin;
    box-shadow: none;
    margin-left: 12px;
    transition: width 0.28s cubic-bezier(0.16, 1, 0.3, 1),
      margin-left 0.28s cubic-bezier(0.16, 1, 0.3, 1),
      padding-inline 0.28s cubic-bezier(0.16, 1, 0.3, 1),
      opacity 0.2s ease;
  }
  .day-details-card.details-collapsed {
    display: block;
    width: 0;
    padding-inline: 0;
    margin-left: 0;
    border-inline-width: 0;
    opacity: 0;
    pointer-events: none;
    overflow: hidden;
  }
  .day-details-card::-webkit-scrollbar {
    width: 6px;
  }
}

/* ---------- 窄屏适配：空间不足时把明细移到日历下方（≤1024px 单列堆叠） ---------- */
@media (max-width: 1024px) {
  .cal-page {
    width: 100%;
    max-width: 760px;
    margin-inline: auto;
  }
  .cal-card,
  .day-details-card {
    width: 100%;
  }
  .details-jump {
    display: inline-flex;
  }
}

/* ---------- 移动端：页面居中、控件不溢出 ---------- */
@media (max-width: 860px) {
  .cal-page {
    max-width: 640px;
  }
  .cal-head {
    justify-content: center;
  }
  .cal-nav,
  .cal-legend {
    justify-content: center;
  }
}

@media (max-width: 768px) {
  .cal-card {
    padding: 8px;
  }
  .cal-grid {
    gap: 3px;
  }
  .cal-day {
    height: 54px;
    padding: 4px;
    align-items: center;
    justify-content: space-between;
  }
  .cal-day-header {
    width: 100%;
    justify-content: center;
    position: relative;
  }
  .today-tag {
    position: absolute;
    right: 0;
    top: -2px;
    font-size: 8px;
    padding: 0 2px;
  }
  .desktop-events {
    display: none !important;
  }
  .mobile-dots {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    margin-top: 2px;
    width: 100%;
    overflow: hidden;
  }
  .mob-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .mob-dot-more {
    font-size: 9px;
    color: var(--muted);
    line-height: 1;
  }
  .cal-title {
    font-size: 15px;
    min-width: 100px;
  }
  .cal-legend {
    display: none;
  }
}

@media (max-width: 600px) {
  .cal-page {
    max-width: 440px;
  }
  .cal-nav {
    width: 100%;
    gap: 6px;
  }
  .cal-nav > .btn-sm:not(.today-btn) {
    flex: 0 0 40px;
  }
  .cal-title {
    flex: 1 1 auto;
    min-width: 0;
    margin-inline: 0;
    white-space: nowrap;
  }
  .today-btn {
    flex: 0 0 auto;
    white-space: nowrap;
  }
  .cal-card {
    padding: 8px;
  }
  .cal-grid {
    gap: 3px;
  }
  .cal-day {
    height: auto;
    min-height: 48px;
    aspect-ratio: 0.9 / 1;
    padding: 4px;
  }
  .day-details-card {
    padding: 12px;
  }
  .details-date {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }
  .details-date > span:first-child {
    max-width: 100%;
  }
  .details-count {
    align-self: flex-start;
  }
  .detail-item {
    gap: 6px;
    padding: 8px;
  }
}

@media (max-width: 360px) {
  .cal-nav {
    gap: 4px;
  }
  .cal-title {
    font-size: 14px;
  }
  .today-btn {
    padding-inline: 8px;
  }
  .day-details-card {
    padding-inline: 10px;
  }
  .detail-item {
    padding-inline: 6px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .details-jump,
  .details-jump-arrow {
    animation: none;
  }
  /* 明细开合动画在减少动效模式下禁播 */
  .day-details-card,
  .details-body {
    transition: none !important;
    animation: none;
  }
  /* 格子入场动画在减少动效模式下禁用 */
  .cal-day {
    animation: none;
  }
}
</style>
