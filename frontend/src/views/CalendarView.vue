<script setup>
// 日历视图：按月渲染扣费 / 服务到期事件
import { ref, computed, onMounted } from "vue";
import { getCalendar } from "../api.js";
import { toast } from "../ui.js";

const now = new Date();
const calYear = ref(now.getFullYear());
const calMonth = ref(now.getMonth() + 1);
const events = ref([]);
const selectedDateStr = ref(null);

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

onMounted(loadMonth);
</script>

<template>
  <div class="page cal-page">
    <div class="cal-head">
      <div class="cal-nav">
        <button class="btn btn-sm" @click="prevMonth(-1)">‹</button>
        <h2 class="cal-title">{{ calYear }} 年 {{ calMonth }} 月</h2>
        <button class="btn btn-sm" @click="prevMonth(1)">›</button>
        <button class="btn btn-sm btn-ghost today-btn" @click="goToday">今天</button>
      </div>
      <div class="cal-legend">
        <span class="legend-item"><i class="dot dot-due"></i>扣费</span>
        <span class="legend-item"><i class="dot dot-end"></i>服务到期</span>
      </div>
    </div>

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

    <!-- 选中日期明细抽屉/卡片 (特别适合移动端和桌面端即时扫读) -->
    <div v-if="selectedDateStr && selectedDayEvents.length" class="card day-details-card">
      <div class="details-head">
        <div class="details-date">
          <span>📅 {{ selectedDateStr }} 扣费明细</span>
          <span class="details-count">共 {{ selectedDayEvents.length }} 笔</span>
        </div>
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
</template>

<style scoped>
.cal-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 顶部导航与图例 */
.cal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.cal-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cal-title {
  margin: 0 4px;
  font-size: var(--fs-md);
  font-weight: 600;
  min-width: 120px;
  text-align: center;
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
.cal-card {
  padding: 12px;
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
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.details-date {
  font-size: var(--fs-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.details-count {
  font-size: var(--fs-xs);
  color: var(--muted);
  font-weight: normal;
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

/* ---------- 移动端与窄屏适配 (< 768px) ---------- */
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
</style>