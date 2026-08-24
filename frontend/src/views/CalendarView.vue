<script setup>
// 日历视图：按月渲染扣费 / 服务到期事件
import { ref, computed, watch, nextTick, onMounted, onActivated, onBeforeUnmount } from "vue";
import { getCalendar } from "../api.js";
import { toast } from "../ui.js";

const now = new Date();
const calYear = ref(now.getFullYear());
const calMonth = ref(now.getMonth() + 1);
const events = ref([]);
const selectedDateStr = ref(null);
const detailsCardRef = ref(null);
const detailsVisible = ref(false);
const detailsVisibilityReady = ref(false);
let detailsObserver = null;

// ===== 年月选择器状态 =====
const showYearMonthPicker = ref(false);
const pickerYear = ref(calYear.value);
const yearWheelRef = ref(null);
const months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

// 生成前后各 30 年的年份列表供滚轮选择
const yearRange = computed(() => {
  const current = now.getFullYear();
  const start = current - 30;
  const end = current + 30;
  const list = [];
  for (let y = start; y <= end; y++) list.push(y);
  return list;
});

// 6 行 7 列 = 42 格
const grid = ref([]);

async function loadMonth() {
  try {
    events.value = await getCalendar(calYear.value, calMonth.value);
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
    cells.push({
      day: d.getDate(),
      dateStr: ds,
      other: true,
      events: byDate[ds] || [],
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
    cells.push({
      day: i,
      dateStr: ds,
      other: true,
      events: byDate[ds] || [],
    });
  }

  grid.value = cells;

  // 默认选中今天或当月第一个有事件的日期
  if (!selectedDateStr.value || !selectedDateStr.value.startsWith(`${year}-${String(month).padStart(2, "0")}`)) {
    selectedDateStr.value = todayStr.startsWith(`${year}-${String(month).padStart(2, "0")}`) ? todayStr : null;
  }
}

function selectDay(cell) {
  if (cell.other) return;
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
  loadMonth();
}

function goToday() {
  const n = new Date();
  calYear.value = n.getFullYear();
  calMonth.value = n.getMonth() + 1;
  loadMonth();
}

// ===== 年月选择器方法 =====
const ITEM_WIDTH = 68; // 每个年份项的宽度

function toggleYearMonthPicker() {
  if (!showYearMonthPicker.value) {
    pickerYear.value = calYear.value;
    showYearMonthPicker.value = true;
    scrollToCurrentYear();
  } else {
    showYearMonthPicker.value = false;
  }
}

function scrollToCurrentYear(smooth = false) {
  nextTick(() => {
    const el = yearWheelRef.value;
    if (!el) return;
    const index = yearRange.value.indexOf(pickerYear.value);
    if (index !== -1) {
      // 瞬间精确定位，不带任何动画或滚动过渡
      const scrollLeft = index * ITEM_WIDTH;
      if (smooth) {
        el.scrollTo({ left: scrollLeft, behavior: "smooth" });
      } else {
        // 关闭平滑滚动属性，瞬间赋值后恢复
        const oldBehavior = el.style.scrollBehavior;
        el.style.scrollBehavior = "auto";
        el.scrollLeft = scrollLeft;
        el.style.scrollBehavior = oldBehavior;
      }
    }
  });
}

function selectYear(y) {
  pickerYear.value = y;
  scrollToCurrentYear(true);
}

let scrollTimer = null;
function onYearWheelScroll(e) {
  // 防抖检测当前最居中的年份
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => {
    const el = yearWheelRef.value;
    if (!el) return;
    const containerRect = el.getBoundingClientRect();
    const centerX = containerRect.left + containerRect.width / 2;
    
    const items = el.querySelectorAll('.wheel-item');
    let closestYear = pickerYear.value;
    let minDistance = Infinity;

    items.forEach(item => {
      const rect = item.getBoundingClientRect();
      const itemCenterX = rect.left + rect.width / 2;
      const distance = Math.abs(centerX - itemCenterX);
      if (distance < minDistance) {
        minDistance = distance;
        closestYear = parseInt(item.getAttribute('data-year'), 10);
      }
    });

    if (closestYear && closestYear !== pickerYear.value) {
      pickerYear.value = closestYear;
    }
  }, 50);
}

function closeYearMonthPicker() {
  showYearMonthPicker.value = false;
}

function pickerYearDelta(delta) {
  pickerYear.value += delta;
  scrollToCurrentYear(true);
}

function selectMonth(month) {
  calYear.value = pickerYear.value;
  calMonth.value = month;
  showYearMonthPicker.value = false;
  loadMonth();
}

function pickerGoToday() {
  const n = new Date();
  pickerYear.value = n.getFullYear();
  calYear.value = n.getFullYear();
  calMonth.value = n.getMonth() + 1;
  showYearMonthPicker.value = false;
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
        <button class="btn btn-sm" @click="prevMonth(-1)">‹</button>
        <div class="cal-title-wrap">
          <button
            class="cal-title-btn"
            type="button"
            :class="{ active: showYearMonthPicker }"
            @click="toggleYearMonthPicker"
          >
            <span>{{ calYear }} 年 {{ calMonth }} 月</span>
            <span class="picker-arrow" :class="{ open: showYearMonthPicker }">▾</span>
          </button>

          <!-- 年月选择器弹窗 (基于遮罩与气泡定位) -->
          <div v-if="showYearMonthPicker" class="picker-backdrop" @click="closeYearMonthPicker"></div>
          <Transition name="picker-pop">
            <div v-if="showYearMonthPicker" class="year-month-picker" role="dialog" aria-label="选择年份和月份">
              <!-- iOS 风格横向滚轮年份选择器 -->
              <div class="picker-wheel-wrap">
                <button
                  class="picker-nav-btn prev-btn"
                  type="button"
                  title="上一年"
                  @click="pickerYearDelta(-1)"
                >
                  ‹
                </button>
                <div
                  ref="yearWheelRef"
                  class="picker-year-wheel"
                  @scroll="onYearWheelScroll"
                >
                  <div class="wheel-spacer"></div>
                  <div
                    v-for="y in yearRange"
                    :key="y"
                    class="wheel-item"
                    :data-year="y"
                    :class="{ active: y === pickerYear }"
                    @click="selectYear(y)"
                  >
                    {{ y }}
                  </div>
                  <div class="wheel-spacer"></div>
                </div>
                <button
                  class="picker-nav-btn next-btn"
                  type="button"
                  title="下一年"
                  @click="pickerYearDelta(1)"
                >
                  ›
                </button>
              </div>

              <!-- 月份网格 (4列x3行) -->
              <div class="picker-grid">
                <button
                  v-for="(m, idx) in months"
                  :key="m"
                  type="button"
                  class="picker-month-btn"
                  :class="{
                    'is-selected': pickerYear === calYear && m === calMonth,
                    'is-current-month': pickerYear === now.getFullYear() && m === (now.getMonth() + 1)
                  }"
                  @click="selectMonth(m)"
                >
                  <span class="m-text">{{ monthNames[idx] }}</span>
                  <span
                    v-if="pickerYear === now.getFullYear() && m === (now.getMonth() + 1)"
                    class="current-month-badge"
                    title="本月"
                  >今</span>
                </button>
              </div>

              <!-- 底部操作栏（已去除emoji/icon） -->
              <div class="picker-footer">
                <button
                  class="picker-quick-btn"
                  type="button"
                  @click="pickerGoToday"
                >
                  回到本月 ({{ now.getFullYear() }}年{{ now.getMonth() + 1 }}月)
                </button>
              </div>
            </div>
          </Transition>
        </div>
        <button class="btn btn-sm" @click="prevMonth(1)">›</button>
        <button class="btn btn-sm btn-ghost today-btn" @click="goToday">今天</button>
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
            :key="i"
            class="cal-day"
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
            <div class="mobile-dots" v-if="!c.other && c.events && c.events.length">
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

      <!-- 选中日期明细：桌面端显示在日历右侧，窄屏显示在日历下方 -->
      <div
        v-if="selectedDateStr && selectedDayEvents.length"
        id="day-details"
        ref="detailsCardRef"
        class="card day-details-card"
      >
        <div class="details-head">
          <div class="details-date">
            <span>📅 {{ selectedDateStr }} 扣费明细</span>
            <span class="details-count">共 {{ selectedDayEvents.length }} 笔 (合计 ¥{{ (selectedDayTotal / 100).toFixed(2) }})</span>
          </div>
          <button
            type="button"
            class="details-close"
            title="关闭扣费明细"
            aria-label="关闭扣费明细"
            @click="closeDetails"
          >✕</button>
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
}
.cal-title-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: 0 2px;
  font-size: var(--fs-md);
  font-weight: 600;
  min-width: 130px;
  text-align: center;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--text);
  font: inherit;
  user-select: none;
}
.cal-title-btn:hover,
.cal-title-btn.active {
  background: var(--bg-2);
  border-color: var(--primary);
  color: var(--primary);
}
.picker-arrow {
  font-size: 10px;
  color: var(--muted);
  transition: transform 0.2s ease;
}
.picker-arrow.open {
  transform: rotate(180deg);
  color: var(--primary);
}
.today-btn {
  font-size: var(--fs-xs);
  padding: 4px 10px;
}

/* 遮罩层 */
.picker-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;
  background: rgba(0, 0, 0, 0.04);
  backdrop-filter: blur(0.5px);
}

/* 年月选择器现代化气泡卡片 */
.year-month-picker {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 16px 36px -6px rgba(0, 0, 0, 0.16), 0 6px 16px -4px rgba(0, 0, 0, 0.08);
  padding: 12px 14px;
  z-index: 100;
  width: 280px;
  box-sizing: border-box;
  transform-origin: top left;
}

/* 移动端适配：年月选择器 */
@media (max-width: 860px) {
  .year-month-picker {
    /* 在移动端居中显示，避免溢出 */
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(280px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    overflow-y: auto;
    transform-origin: center center;
  }
  
  /* 调整弹出动画 */
  .picker-pop-enter-from,
  .picker-pop-leave-to {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.92);
  }
  
  /* 月份按钮增大触摸区域 */
  .picker-month-btn {
    padding: 12px 0;
    min-height: 44px; /* iOS 推荐最小触摸目标 */
  }
  
  /* 年份滚轮触摸优化 */
  .picker-year-wheel {
    -webkit-overflow-scrolling: touch;
    scroll-padding: 0 calc(50% - 34px);
  }
  
  .wheel-item {
    min-height: 44px;
    -webkit-tap-highlight-color: transparent;
  }
  
  /* 导航按钮增大触摸区域 */
  .picker-nav-btn {
    width: 32px;
    height: 32px;
  }
  
  /* 底部按钮增大触摸区域 */
  .picker-quick-btn {
    padding: 10px 12px;
    min-height: 44px;
  }
}

@media (max-width: 360px) {
  .year-month-picker {
    padding: 10px 12px;
    border-radius: 12px;
  }
  
  .picker-grid {
    gap: 4px;
  }
  
  .picker-month-btn {
    font-size: 11px;
    padding: 10px 0;
  }
}

/* iOS 风格年份滚轮容器 */
.picker-wheel-wrap {
  position: relative;
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding: 4px 0 10px;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
}

.picker-year-wheel {
  position: relative;
  display: flex;
  align-items: center;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  -ms-overflow-style: none;
  width: 100%;
  padding: 4px 0;
  z-index: 2;
  mask-image: linear-gradient(to right, transparent 0%, black 20%, black 80%, transparent 100%);
  -webkit-mask-image: linear-gradient(to right, transparent 0%, black 20%, black 80%, transparent 100%);
}
.picker-year-wheel::-webkit-scrollbar {
  display: none;
}

.wheel-spacer {
  flex: 0 0 calc(50% - 34px);
  pointer-events: none;
}

.wheel-item {
  flex: 0 0 68px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 500;
  color: var(--muted);
  scroll-snap-align: center;
  cursor: pointer;
  user-select: none;
  border-radius: 6px;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.wheel-item:hover:not(.active) {
  color: var(--text);
  background: var(--bg-2);
}

/* 选中的年份自带高亮背景边框与加粗字号，完美绑定 */
.wheel-item.active {
  color: var(--primary);
  font-size: 16px;
  font-weight: 700;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.3);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
}

.picker-nav-btn {
  position: relative;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--card);
  color: var(--muted);
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(0,0,0,0.05);
}

.picker-nav-btn:hover {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  transform: scale(1.08);
}

/* 月份 4x3 网格 */
.picker-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  margin-bottom: 10px;
}

.picker-month-btn {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 9px 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--bg-2);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  transition: all 0.15s ease;
  user-select: none;
}

.picker-month-btn:hover:not(.is-selected) {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.3);
  color: var(--primary);
}

/* 选中当前查看的月份 */
.picker-month-btn.is-selected {
  background: var(--primary);
  color: #ffffff !important;
  font-weight: 600;
  border-color: var(--primary);
  box-shadow: 0 4px 10px rgba(99, 102, 241, 0.35);
}

/* 真实当月的高亮/角标 */
.picker-month-btn.is-current-month:not(.is-selected) {
  border-color: var(--amber);
  color: var(--amber);
  background: rgba(245, 158, 11, 0.06);
  font-weight: 600;
}

.current-month-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  font-size: 9px;
  line-height: 1;
  padding: 1px 3px;
  border-radius: 4px;
  background: var(--amber);
  color: #fff;
  font-weight: 600;
  transform: scale(0.85);
}

.picker-month-btn.is-selected .current-month-badge {
  background: rgba(255, 255, 255, 0.3);
  color: #fff;
}

/* 底部快速回到今天 */
.picker-footer {
  display: flex;
  justify-content: stretch;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.picker-quick-btn {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-2);
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.picker-quick-btn:hover {
  background: var(--card);
  border-color: var(--primary);
  color: var(--primary);
}

/* 弹出动画 */
.picker-pop-enter-active,
.picker-pop-leave-active {
  transition: opacity 0.16s ease, transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}
.picker-pop-enter-from,
.picker-pop-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
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
  /* 单列：日历占满整宽。桌面端（≥1025px）选中日期后明细以浮层叠在右上（方案A），
     超宽屏（≥1200px）再恢复「日历 + 明细」并排第二列（方案C）。 */
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
  border-color: rgba(99, 102, 241, 0.4);
}
.cal-day.other {
  opacity: 0.3;
  background: transparent;
  cursor: default;
}
.cal-day.today {
  border-color: var(--primary);
  background: rgba(99, 102, 241, 0.05);
}
.cal-day.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary);
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
  box-shadow: 0 6px 18px rgba(79, 70, 229, 0.28);
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
@media (min-width: 1025px) {
  .cal-page {
    flex: 1 1 auto;
    min-height: 0;
    height: 100%;
  }
  .cal-content {
    flex: 1 1 auto;
    min-height: 0;
    align-items: stretch;
    /* 桌面端明细默认以浮层叠在日历右上（方案A）；超宽屏恢复并排（方案C） */
    position: relative;
  }
  .cal-card {
    display: flex;
    flex-direction: column;
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
  /* 方案A：明细浮层叠在日历右上角，日历保持整宽，7 列格子不被挤压 */
  .day-details-card {
    position: absolute;
    right: 0;
    top: 0;
    width: min(380px, 42%);
    max-height: 100%;
    overflow-y: auto;
    /* 明细过长时内部滚动，避免把日历挤出视口 */
    scrollbar-width: thin;
    z-index: 15;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.24);
  }
  .day-details-card::-webkit-scrollbar {
    width: 6px;
  }
}

/* 方案C：主区足够宽时恢复「日历 + 明细」并排，明细不再浮层 */
@media (min-width: 1200px) {
  .cal-content {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
    gap: 12px;
    align-items: stretch;
    position: static;
  }
  .day-details-card {
    position: static;
    width: auto;
    align-self: stretch;
    max-height: 100%;
    overflow-y: auto;
    scrollbar-width: thin;
    box-shadow: none;
  }
  /* 无选中明细时日历独占整行，避免右侧空白轨 */
  .cal-content:not(:has(.day-details-card)) {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* ---------- 窄屏适配：空间不足时把明细移到日历下方 ---------- */
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
}
</style>
