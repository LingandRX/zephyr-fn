<script setup>
// 日历视图：按月渲染扣费 / 服务到期事件
// 视觉：iOS 风格（毛玻璃卡片 / 圆形日期 / 彩色事件胶囊）
// 交互：Headless UI Dialog 承载窄屏「扣费明细」底部抽屉，Popover 承载窄屏图例
import { ref, computed, watch, onMounted, onActivated } from "vue";
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Popover,
  PopoverButton,
  PopoverPanel,
  TransitionRoot,
  TransitionChild,
} from "@headlessui/vue";
import { getCalendar } from "../services/api.js";
import { fmtCents } from "../utils/format.js";
import { toast } from "../utils/ui.js";
import HeadlessDatePicker from "../components/HeadlessDatePicker.vue";

const now = new Date();
const calYear = ref(now.getFullYear());
const calMonth = ref(now.getMonth() + 1);
const events = ref([]);
const selectedDateStr = ref(null);
// 窄屏明细底部抽屉（Headless UI Dialog）开合态
const sheetOpen = ref(false);
// 当月网格行数（5 或 6）：桌面端用它等分行高，6 行月份不再截断月末日期
const calRows = ref(5);

/** 本地日期 → YYYY-MM-DD。不能用 toISOString()：UTC 偏移会让「今天」错一天 */
function toDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// 区分事件类型辅助方法
function initialOf(name) {
  const s = String(name ?? "").trim();
  return s ? [...s][0].toUpperCase() : "?";
}

function getEventMeta(e) {
  if (!e) return { type: "due", label: "续费扣款", shortLabel: "扣费", dotClass: "dot-due", tagClass: "tag-due", eventClass: "due" };
  const t = e.event_type;
  if (t === "service_end" || t === "due_date") {
    return {
      type: "end",
      label: "服务到期",
      shortLabel: "到期",
      dotClass: "dot-end",
      tagClass: "tag-end",
      eventClass: "end",
    };
  }
  if (t === "new_subscription" || t === "first_payment") {
    return {
      type: "new",
      label: "首次扣费",
      shortLabel: "首付",
      dotClass: "dot-new",
      tagClass: "tag-new",
      eventClass: "new",
    };
  }
  return {
    type: "due",
    label: "续费扣款",
    shortLabel: "扣费",
    dotClass: "dot-due",
    tagClass: "tag-due",
    eventClass: "due",
  };
}

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

// 网格单元格（含跨月占位）
const grid = ref([]);

async function loadMonth() {
  const y = calYear.value;
  const m = calMonth.value;
  const prevY = m === 1 ? y - 1 : y;
  const prevM = m === 1 ? 12 : m - 1;
  const nextY = m === 12 ? y + 1 : y;
  const nextM = m === 12 ? 1 : m + 1;

  try {
    // 一次性取上/当/下三个月：跨月占位格也要显示事件
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

function makeCell(dateStr, day, other, todayStr, byDate) {
  const dayEvents = byDate[dateStr] || [];
  const showCountBadge = dayEvents.length > 2;
  return {
    day,
    dateStr,
    other,
    today: dateStr === todayStr,
    events: dayEvents,
    visibleEvents: showCountBadge ? [] : dayEvents.slice(0, 2),
    more: showCountBadge ? dayEvents.length : Math.max(0, dayEvents.length - 2),
  };
}

function buildGrid() {
  const year = calYear.value;
  const month = calMonth.value;
  const byDate = {};
  for (const e of events.value) (byDate[e.date] = byDate[e.date] || []).push(e);

  const todayStr = toDateStr(new Date());

  const first = new Date(year, month - 1, 1);
  const startDow = first.getDay(); // 0 = 周日，与表头「日一二三四五六」一致
  const daysInMonth = new Date(year, month, 0).getDate();

  // 行数按需 5 或 6 行（至少 5 行保持高度稳定）：
  // 固定 35 格会让 startDow + 天数 > 35 的月份丢掉月末日期（如 2026-08 丢 30/31 日）
  const rows = Math.max(5, Math.ceil((startDow + daysInMonth) / 7));
  calRows.value = rows;
  const totalCells = rows * 7;

  const cells = [];
  // 上月占位
  for (let i = 0; i < startDow; i++) {
    const d = new Date(year, month - 1, i - startDow + 1);
    cells.push(makeCell(toDateStr(d), d.getDate(), true, todayStr, byDate));
  }
  // 当月
  for (let day = 1; day <= daysInMonth; day++) {
    const ds = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    cells.push(makeCell(ds, day, false, todayStr, byDate));
  }
  // 下月占位
  const nextMonthYear = month === 12 ? year + 1 : year;
  const nextMonthNum = month === 12 ? 1 : month + 1;
  let nextDay = 1;
  while (cells.length < totalCells) {
    const ds = `${nextMonthYear}-${String(nextMonthNum).padStart(2, "0")}-${String(nextDay).padStart(2, "0")}`;
    cells.push(makeCell(ds, nextDay, true, todayStr, byDate));
    nextDay++;
  }
  grid.value = cells;

  // 切换月份时，如果之前未选中或者选中日期不在当月：
  // 保持与之前类似的默认行为；但若之前明细已在打开状态，则寻找当月第一个有事件的日期并选中，
  // 确保直接平滑更新内容而不经历 close->open 的动画断层。
  const monthPrefix = `${year}-${String(month).padStart(2, "0")}`;
  if (!selectedDateStr.value || !selectedDateStr.value.startsWith(monthPrefix)) {
    if (detailsOpen.value) {
      const firstEventCell = grid.value.find((c) => !c.other && c.events.length > 0);
      if (firstEventCell) {
        selectedDateStr.value = firstEventCell.dateStr;
      } else {
        selectedDateStr.value = todayStr.startsWith(monthPrefix) ? todayStr : null;
      }
    } else {
      selectedDateStr.value = todayStr.startsWith(monthPrefix) ? todayStr : null;
    }
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

/** 按币种汇总扣费金额（服务到期不计入） */
function computeTotal(events) {
  if (!events.length) return "";
  const map = {};
  for (const e of events) {
    if (e.event_type === "service_end") continue;
    const cur = e.currency || "CNY";
    map[cur] = (map[cur] || 0) + (e.amount || 0);
  }
  const entries = Object.entries(map);
  if (!entries.length) return "";
  return entries.map(([cur, sum]) => fmtCents(sum, cur)).join(" + ");
}

const selectedDayTotalFormatted = computed(() => computeTotal(selectedDayEvents.value));

const isOnlyServiceEnd = computed(() => {
  const events = selectedDayEvents.value;
  return events.length > 0 && events.every((e) => e.event_type === "service_end");
});

// 明细展开态：选中且有事件的日期（供 details-collapsed 类驱动桌面侧栏开合）
const detailsOpen = computed(() => !!selectedDateStr.value && selectedDayEvents.value.length > 0);

// 桌面侧栏的渲染快照：关闭时不清空，供 var(--dur-medium) 收起动画期间继续渲染原内容，
// 避免收起过程中出现「null / 空列表」一闪。
const detailsSnapshot = ref({ date: null, events: [], onlyServiceEnd: false, totalFormatted: "" });

watch([selectedDateStr, selectedDayEvents], ([date, events]) => {
  if (!date || !events.length) return;
  detailsSnapshot.value = {
    date,
    events,
    onlyServiceEnd: events.every((e) => e.event_type === "service_end"),
    totalFormatted: computeTotal(events),
  };
});

function openSheet() {
  sheetOpen.value = true;
}

function closeSheet() {
  sheetOpen.value = false;
}

// 关闭扣费明细（桌面侧栏）：清空选中日期即可（detailsSnapshot 保留，供收起动画渲染）
function closeDetails() {
  selectedDateStr.value = null;
  sheetOpen.value = false;
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
  selectedDateStr.value = toDateStr(n);
  loadMonth();
}

// keep-alive 下「切换回本页」不会重新 onMounted，需在 onActivated 重新拉取当月数据，
// 否则在其他页面新增订阅后切回时日历仍显示旧数据。
onMounted(loadMonth);
onActivated(loadMonth);
</script>

<template>
  <div class="page cal-page">
    <div class="cal-head">
      <div class="cal-nav">
        <button class="cal-nav-btn" type="button" title="上一月" aria-label="上一月" @click="prevMonth(-1)">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 5l-7 7 7 7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>

        <div class="cal-title-wrap">
          <HeadlessDatePicker
            v-model="calendarPickerDate"
            type="month"
            :clearable="true"
            :display-formatter="formatCalHeader"
            placeholder="选择月份"
            @clear="goToday"
          />
        </div>

        <button class="cal-nav-btn" type="button" title="下一月" aria-label="下一月" @click="prevMonth(1)">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M9 5l7 7-7 7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>

        <button class="cal-today-btn" type="button" @click="goToday">今天</button>

        <!-- 窄屏图例：用 Headless UI Popover 收纳，替代直接隐藏图例。
             注意：包裹层必须是真实元素。Headless UI Popover 根节点是 Fragment，
             父组件的 scoped data-v 不会继承到它渲染的 div 上；
             把 class 直接写在 <Popover> 上会失效（桌面端也会显示、面板也会锚错容器）。 -->
        <div class="cal-legend-popover">
          <Popover>
            <PopoverButton class="cal-legend-btn" title="图例" aria-label="事件类型图例">
              <!-- 图例图标：三个事件色点 + 文本线，与右上角内联图例配色一致 -->
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="4.5" cy="7" r="2" style="fill: var(--ios-blue)" />
                <circle cx="4.5" cy="12" r="2" style="fill: var(--ios-orange)" />
                <circle cx="4.5" cy="17" r="2" style="fill: var(--ios-red)" />
                <path d="M10 7h9.5M10 12h9.5M10 17h9.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
              </svg>
            </PopoverButton>
            <PopoverPanel
              transition
              enter="legend-panel-enter"
              enter-from="legend-panel-from"
              enter-to="legend-panel-to"
              leave="legend-panel-leave"
              leave-from="legend-panel-to"
              leave-to="legend-panel-from"
              class="cal-legend-panel"
            >
              <div class="legend-item"><i class="dot dot-new"></i>首次扣费</div>
              <div class="legend-item"><i class="dot dot-due"></i>续费扣费</div>
              <div class="legend-item"><i class="dot dot-end"></i>服务到期</div>
            </PopoverPanel>
          </Popover>
        </div>
      </div>

      <div class="cal-legend">
        <span class="legend-item"><i class="dot dot-new"></i>首次扣费</span>
        <span class="legend-item"><i class="dot dot-due"></i>续费扣费</span>
        <span class="legend-item"><i class="dot dot-end"></i>服务到期</span>
      </div>
    </div>

    <div class="cal-content">
      <div class="card cal-card">
        <div class="cal-grid" :style="{ '--cal-rows': calRows }">
          <div v-for="(d, i) in ['日', '一', '二', '三', '四', '五', '六']" :key="'dow-' + i" class="cal-dow">{{ d }}</div>
          <div
            v-for="(c, i) in grid"
            :key="c.dateStr"
            class="cal-day"
            role="button"
            tabindex="0"
            :aria-label="`${c.dateStr}${c.events.length ? '，' + c.events.length + ' 笔事件' : ''}`"
            :style="{ '--d': Math.floor(i / 7) * 18 + 'ms' }"
            :class="{
              other: c.other,
              today: c.today,
              selected: c.dateStr === selectedDateStr && !c.other,
              'has-events': c.events.length > 0
            }"
            @click="selectDay(c)"
            @keydown.enter="selectDay(c)"
            @keydown.space.prevent="selectDay(c)"
          >
            <div class="cal-day-header">
              <span class="cal-day-num">{{ c.day }}</span>
            </div>

            <!-- 桌面端/宽屏：事件胶囊 -->
            <div class="events-wrap desktop-events">
              <template v-if="c.visibleEvents.length">
                <div
                  v-for="(e, j) in c.visibleEvents"
                  :key="j"
                  class="cal-event"
                  :class="getEventMeta(e).eventClass"
                  :title="`${e.name} ${getEventMeta(e).label} ${e.amount_formatted}`"
                >
                  <span class="event-avatar">{{ initialOf(e.name) }}</span>
                  <span class="event-name">{{ e.name }}</span>
                  <span class="event-type-pill">{{ getEventMeta(e).shortLabel }}</span>
                  <span class="event-amt">{{ e.amount_formatted }}</span>
                </div>
                <div v-if="c.more" class="cal-event more-badge" :title="`还有 ${c.more} 项事件`">+{{ c.more }}</div>
              </template>
              <div v-else-if="c.events.length > 2" class="cal-event more-badge is-count" :title="`还有 ${c.events.length} 项事件`">
                {{ c.events.length }}
              </div>
            </div>

            <!-- 移动端：圆点 -->
            <div class="mobile-dots" v-if="c.events.length">
              <span
                v-for="(e, j) in c.events.slice(0, 3)"
                :key="j"
                class="mob-dot"
                :class="getEventMeta(e).dotClass"
              ></span>
              <span v-if="c.events.length > 3" class="mob-dot-more">+</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 桌面端明细侧栏：常驻元素 + details-collapsed 类控制收起态，宽度平滑开合 -->
      <div
        id="day-details"
        class="card day-details-card"
        :class="{ 'details-collapsed': !detailsOpen }"
      >
        <div :key="detailsSnapshot.date" class="details-body">
          <div class="details-head">
            <div class="details-date">
              <span class="details-date-label">
                <svg class="detail-cal-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <rect x="3" y="5" width="18" height="16" rx="3" stroke="currentColor" stroke-width="1.8" />
                  <path d="M8 3v4M16 3v4M3 10h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                </svg>
                {{ detailsSnapshot.date }} {{ detailsSnapshot.onlyServiceEnd ? '到期明细' : '扣费明细' }}
              </span>
              <span class="details-count">
                共 {{ detailsSnapshot.events.length }} 笔
                <template v-if="detailsSnapshot.totalFormatted"> (合计 {{ detailsSnapshot.totalFormatted }})</template>
              </span>
            </div>
            <button
              type="button"
              class="details-close"
              title="关闭扣费明细"
              aria-label="关闭扣费明细"
              @click="closeDetails"
            >
              <svg class="detail-close-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
              </svg>
            </button>
          </div>
          <div class="details-list">
            <div v-for="(e, idx) in detailsSnapshot.events" :key="idx" class="detail-item">
              <div class="detail-left">
                <span class="detail-avatar">{{ initialOf(e.name) }}</span>
                <div class="detail-info">
                  <div class="detail-title-row">
                    <span class="detail-name">{{ e.name }}</span>
                    <span class="detail-type-tag" :class="getEventMeta(e).tagClass">{{ getEventMeta(e).label }}</span>
                  </div>
                </div>
              </div>
              <div class="detail-right">
                <span class="detail-amount">{{ e.amount_formatted }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 窄屏明细底部抽屉（Headless UI Dialog + Transition） -->
    <TransitionRoot :show="sheetOpen" as="template">
      <Dialog as="div" class="cal-sheet-root" @close="closeSheet">
        <TransitionChild
          as="template"
          enter="cal-sheet-backdrop-enter"
          enter-from="cal-sheet-backdrop-from"
          enter-to="cal-sheet-backdrop-to"
          leave="cal-sheet-backdrop-leave"
          leave-from="cal-sheet-backdrop-to"
          leave-to="cal-sheet-backdrop-from"
        >
          <div class="cal-sheet-backdrop" aria-hidden="true" />
        </TransitionChild>

        <div class="cal-sheet-container">
          <TransitionChild
            as="template"
            enter="cal-sheet-panel-enter"
            enter-from="cal-sheet-panel-from"
            enter-to="cal-sheet-panel-to"
            leave="cal-sheet-panel-leave"
            leave-from="cal-sheet-panel-to"
            leave-to="cal-sheet-panel-from"
          >
            <DialogPanel class="cal-sheet-panel">
              <div class="cal-sheet-grabber" aria-hidden="true" />
              <div class="details-head">
                <DialogTitle as="h3" class="details-date-label">
                  <svg class="detail-cal-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <rect x="3" y="5" width="18" height="16" rx="3" stroke="currentColor" stroke-width="1.8" />
                    <path d="M8 3v4M16 3v4M3 10h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                  </svg>
                  {{ selectedDateStr }} {{ isOnlyServiceEnd ? '到期明细' : '扣费明细' }}
                </DialogTitle>
                <button
                  type="button"
                  class="details-close"
                  title="关闭"
                  aria-label="关闭扣费明细"
                  @click="closeSheet"
                >
                  <svg class="detail-close-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                  </svg>
                </button>
              </div>
              <p class="cal-sheet-sub">
                共 {{ selectedDayEvents.length }} 笔<template v-if="selectedDayTotalFormatted"> · 合计 {{ selectedDayTotalFormatted }}</template>
              </p>
              <div :key="selectedDateStr" class="details-body">
                <div class="details-list">
                  <div v-for="(e, idx) in selectedDayEvents" :key="idx" class="detail-item">
                    <div class="detail-left">
                      <span class="detail-avatar">{{ initialOf(e.name) }}</span>
                      <div class="detail-info">
                        <div class="detail-title-row">
                          <span class="detail-name">{{ e.name }}</span>
                          <span class="detail-type-tag" :class="getEventMeta(e).tagClass">{{ getEventMeta(e).label }}</span>
                        </div>
                      </div>
                    </div>
                    <div class="detail-right">
                      <span class="detail-amount">{{ e.amount_formatted }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- 窄屏：明细位于抽屉中，用浮动按钮提示并唤起 -->
    <button
      v-if="selectedDateStr && selectedDayEvents.length"
      class="details-jump"
      type="button"
      aria-label="查看扣费明细"
      @click="openSheet"
    >
      <span>查看扣费明细</span>
      <span class="details-jump-count">{{ selectedDayEvents.length }}</span>
    </button>
  </div>
</template>

<style scoped>
/* =====================================================================
 * 日历页 · iOS 风格
 * 毛玻璃卡片 / SF 排版 / 圆形日期 / 彩色事件胶囊 / 底部抽屉
 * ===================================================================== */

/* iOS 系统色板
 * 注意：令牌必须挂在组件根元素 .cal-page 上，不能写进 scoped 的 `:root`。
 * scoped 会把 `:root` 编译成 `[data-v-xxx]:root`，而 <html> 拿不到 data-v 属性，
 * 整个变量块会失效（卡片背景、边框、日期圆形全部变透明）。 */
.cal-page {
  --ios-blue: #007aff;
  --ios-blue-soft: rgba(0, 122, 255, 0.12);
  --ios-green: #34c759;
  --ios-orange: #ff9500;
  --ios-orange-soft: rgba(255, 149, 0, 0.14);
  --ios-red: #ff3b30;
  --ios-red-soft: rgba(255, 59, 48, 0.12);
  --ios-gray: #8e8e93;
  --ios-fill: rgba(120, 120, 128, 0.08);
  --ios-separator: rgba(60, 60, 67, 0.12);
  --ios-card-bg: rgba(255, 255, 255, 0.72);
  --ios-card-border: rgba(255, 255, 255, 0.5);

  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

:root[data-theme="dark"] .cal-page {
  --ios-fill: rgba(120, 120, 128, 0.24);
  --ios-separator: rgba(255, 255, 255, 0.1);
  --ios-card-bg: rgba(28, 28, 30, 0.72);
  --ios-card-border: rgba(255, 255, 255, 0.08);
}

/* ---------------- 顶部导航与图例 ---------------- */
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
.cal-nav-btn {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--ios-fill);
  color: var(--ios-blue);
  cursor: pointer;
  outline: none;
  transition: background-color var(--dur-quick) ease, transform var(--dur-quick) ease;
}
.cal-nav-btn:hover {
  background: var(--ios-separator);
}
.cal-nav-btn:active {
  transform: scale(0.92);
}
.cal-nav-btn:focus-visible {
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}
.cal-nav-btn svg {
  width: 16px;
  height: 16px;
}
.cal-title-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-width: 150px;
}
.cal-title-wrap :deep(.custom-date-picker-trigger) {
  height: 34px;
  padding: 0 12px;
  font-weight: 600;
  font-size: var(--fs-md);
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}
.cal-title-wrap :deep(.custom-date-picker-trigger:hover) {
  background: var(--ios-fill);
}
.cal-today-btn {
  height: 32px;
  padding: 0 14px;
  flex-shrink: 0;
  border: none;
  border-radius: 999px;
  background: var(--ios-blue-soft);
  color: var(--ios-blue);
  font: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--dur-quick) ease, transform var(--dur-quick) ease;
}
.cal-today-btn:hover {
  background: rgba(0, 122, 255, 0.2);
}
.cal-today-btn:active {
  transform: scale(0.95);
}

.cal-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: var(--fs-xs);
  color: var(--ios-gray);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.dot-new { background: var(--ios-blue); }
.dot-due { background: var(--ios-orange); }
.dot-end { background: var(--ios-red); }

/* 窄屏图例 Popover（桌面端隐藏，直接显示内联图例） */
.cal-legend-popover {
  display: none;
  position: relative;
}
/* 注意：Headless UI 的 PopoverButton 根节点是 Fragment（button + focus guard），
   父组件的 scoped data-v 不会继承到它渲染的 <button> 上，
   因此必须用 :global() 才能命中（与 Sidebar.vue 处理 Dialog 类名同理）。 */
:global(.cal-legend-btn) {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--ios-fill);
  color: var(--ios-gray);
  cursor: pointer;
  outline: none;
  transition: background-color var(--dur-quick) ease, color var(--dur-quick) ease, transform var(--dur-quick) ease;
}
:global(.cal-legend-btn:hover) {
  background: var(--ios-separator);
  color: var(--text);
}
:global(.cal-legend-btn:active) {
  transform: scale(0.92);
}
:global(.cal-legend-btn:focus-visible) {
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}
:global(.cal-legend-btn svg) {
  width: 18px;
  height: 18px;
  display: block;
}
.cal-legend-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--ios-card-border);
  border-radius: 14px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.18);
  color: var(--ios-gray);
  font-size: var(--fs-xs);
  white-space: nowrap;
}

/* ---------------- 卡片与网格 ---------------- */
.cal-content {
  /* 基座：单列堆叠（日历在上、明细在抽屉中）。≥1025px 切换为并排。 */
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.cal-content > .card {
  margin-bottom: 0;
}
.cal-card,
.day-details-card {
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 16px;
}
.cal-card {
  padding: 14px;
}
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  grid-template-rows: auto repeat(var(--cal-rows, 5), minmax(96px, 1fr));
  gap: 4px;
  width: 100%;
  min-height: 480px;
}
.cal-dow {
  text-align: center;
  color: var(--ios-gray);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 2px 0 8px;
}

/* 单元格：无边框，靠圆角底色区分状态 */
.cal-day {
  min-width: 0;
  min-height: 96px;
  height: auto;
  padding: 6px;
  border-radius: 12px;
  background: transparent;
  border: 1px solid transparent;
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-sizing: border-box;
  overflow: hidden;
  cursor: pointer;
  outline: none;
  transition: background var(--dur-quick) ease, box-shadow var(--dur-quick) ease, transform var(--dur-quick) ease;
}
.cal-day:hover {
  background: var(--ios-fill);
}
.cal-day:active {
  transform: scale(0.985);
}
.cal-day:focus-visible {
  box-shadow: 0 0 0 2px var(--ios-blue);
}
.cal-day.other {
  opacity: 0.32;
}
.cal-day.other:hover {
  opacity: 0.6;
}
.cal-day.today {
  background: var(--ios-red-soft);
}
.cal-day.selected {
  background: var(--ios-blue-soft);
  box-shadow: inset 0 0 0 1.5px var(--ios-blue);
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
  animation: cal-day-in var(--dur-slow) var(--ease-decelerate) both;
  animation-delay: var(--d, 0ms);
}

/* 日期数字：iOS 圆形 */
.cal-day-header {
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.cal-day-num {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  font-variant-numeric: tabular-nums;
  transition: background var(--dur-quick) ease, color var(--dur-quick) ease;
}
.cal-day.today .cal-day-num {
  color: var(--ios-red);
  font-weight: 700;
}
.cal-day.selected .cal-day-num {
  background: var(--ios-blue);
  color: #fff;
}
.cal-day.selected.today .cal-day-num {
  background: var(--ios-red);
  color: #fff;
}

/* 事件胶囊 */
.events-wrap {
  display: flex;
  flex-direction: column;
  gap: 3px;
  overflow: hidden;
  flex: 1 1 auto;
  min-height: 0;
  max-height: 108px;
}
.cal-event {
  font-size: 11px;
  border-radius: 7px;
  padding: 3px 6px;
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 100%;
  line-height: 1.25;
  background: var(--ios-fill);
  color: var(--text);
}
.cal-event.new { background: var(--ios-blue-soft); }
.cal-event.due { background: var(--ios-orange-soft); }
.cal-event.end { background: var(--ios-red-soft); }
.event-avatar {
  width: 16px;
  height: 16px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.6);
  font-size: 9px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  line-height: 1;
}
:root[data-theme="dark"] .event-avatar {
  background: rgba(255, 255, 255, 0.14);
}
.cal-event.new .event-avatar { color: var(--ios-blue); }
.cal-event.due .event-avatar { color: var(--ios-orange); }
.cal-event.end .event-avatar { color: var(--ios-red); }
.event-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  font-weight: 600;
}
.event-type-pill {
  font-size: 9px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 4px;
  font-weight: 600;
  flex-shrink: 0;
  white-space: nowrap;
}
.cal-event.new .event-type-pill {
  color: var(--ios-blue);
  background: rgba(0, 122, 255, 0.16);
}
.cal-event.due .event-type-pill {
  color: var(--ios-orange);
  background: rgba(255, 149, 0, 0.18);
}
.cal-event.end .event-type-pill {
  color: var(--ios-red);
  background: rgba(255, 59, 48, 0.16);
}
.event-amt {
  flex-shrink: 0;
  color: var(--ios-gray);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.more-badge {
  justify-content: center;
  color: var(--ios-gray);
  font-size: 10px;
  background: transparent;
  border: 1px dashed var(--ios-separator);
  white-space: nowrap;
}
.more-badge.is-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  width: 18px;
  height: 18px;
  padding: 0;
  border-radius: 10px;
  border: 1px solid rgba(0, 122, 255, 0.18);
  background: rgba(0, 122, 255, 0.08);
  color: var(--ios-blue);
  font-weight: 600;
  font-size: 8px;
  letter-spacing: 0.02em;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
  margin-inline: auto;
}

@media (max-width: 980px) {
  .event-type-pill,
  .event-amt {
    display: none;
  }

  .cal-event {
    grid-template-columns: 16px minmax(0, 1fr);
  }
}

/* 移动端圆点（≤768px 才显示） */
.mobile-dots {
  display: none;
}

/* ---------------- 明细（桌面侧栏 / 窄屏抽屉共用） ---------------- */
.day-details-card {
  /* 窄屏不用内联卡片，改用底部抽屉 */
  display: none;
  min-width: 0;
  padding: 14px 16px;
  scroll-margin-top: 12px;
}
.details-body {
  animation: details-body-in var(--dur-quick) ease;
}
@keyframes details-body-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}
.details-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ios-separator);
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
.details-date-label {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
  font: inherit;
  font-weight: 600;
}
.detail-cal-icon {
  width: 15px;
  height: 15px;
  margin-right: 5px;
  flex-shrink: 0;
}
.details-count {
  font-size: var(--fs-xs);
  color: var(--ios-gray);
  font-weight: normal;
  flex-shrink: 0;
  white-space: nowrap;
}
.details-close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: var(--ios-fill);
  color: var(--ios-gray);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color var(--dur-fast) ease, background var(--dur-fast) ease;
}
.detail-close-icon {
  width: 14px;
  height: 14px;
}
.details-close:hover {
  color: var(--text);
  background: var(--ios-separator);
}
.details-close:focus {
  outline: none;
}
.details-close:focus-visible {
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
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
  padding: 10px 12px;
  background: var(--ios-fill);
  border-radius: 12px;
}
.detail-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 auto;
  min-width: 0;
}
.detail-avatar {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--ios-card-bg);
  color: var(--ios-blue);
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.detail-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1 1 auto;
}
.detail-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
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
  padding: 2px 6px;
  background: var(--ios-fill);
  color: var(--ios-gray);
  border-radius: 5px;
  flex-shrink: 0;
  font-weight: 600;
}
.detail-type-tag.tag-new {
  background: rgba(0, 122, 255, 0.16);
  color: var(--ios-blue);
}
.detail-type-tag.tag-due {
  background: rgba(255, 149, 0, 0.18);
  color: var(--ios-orange);
}
.detail-type-tag.tag-end {
  background: rgba(255, 59, 48, 0.16);
  color: var(--ios-red);
}
.detail-amount {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

/* ---------------- 窄屏底部抽屉（Headless UI Dialog） ---------------- */
.cal-sheet-root {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  overflow: hidden;
}
.cal-sheet-backdrop {
  position: fixed;
  inset: 0;
  /* Dialog 根节点是 Fragment，根类拿不到本组件的 scoped data-v，规则不生效；z-index 必须写在自己的元素上 */
  z-index: var(--z-modal);
  background: rgba(0, 0, 0, 0.4);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}
.cal-sheet-container {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 12px;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
  pointer-events: none;
}
.cal-sheet-panel {
  pointer-events: auto;
  width: 100%;
  max-width: 560px;
  max-height: 78vh;
  overflow-y: auto;
  padding: 8px 16px 18px;
  border: 1px solid var(--ios-card-border);
  border-radius: 20px;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  backdrop-filter: saturate(180%) blur(24px);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.28);
  scrollbar-width: thin;
}
.cal-sheet-grabber {
  width: 36px;
  height: 5px;
  border-radius: 999px;
  background: var(--ios-separator);
  margin: 4px auto 12px;
}
.cal-sheet-sub {
  margin: 0 0 10px;
  font-size: var(--fs-xs);
  color: var(--ios-gray);
}
.cal-sheet-panel::-webkit-scrollbar {
  width: 6px;
}
.cal-sheet-panel::-webkit-scrollbar-thumb {
  border-radius: 99px;
  background: var(--ios-separator);
}

/* Headless UI 过渡动画类 */
.cal-sheet-backdrop-enter { transition: opacity var(--dur-base) ease-out; }
.cal-sheet-backdrop-from { opacity: 0; }
.cal-sheet-backdrop-to { opacity: 1; }
.cal-sheet-backdrop-leave { transition: opacity var(--dur-quick) ease-in; }

.cal-sheet-panel-enter {
  transition: transform var(--dur-slow) var(--ease-decelerate), opacity var(--dur-base) ease;
}
.cal-sheet-panel-from { transform: translateY(100%); opacity: 0.6; }
.cal-sheet-panel-to { transform: translateY(0); opacity: 1; }
.cal-sheet-panel-leave {
  transition: transform var(--dur-base) var(--ease-accelerate), opacity var(--dur-quick) ease;
}

.legend-panel-enter {
  transition: opacity var(--dur-quick) ease, transform var(--dur-quick) var(--ease-spring);
}
.legend-panel-from { opacity: 0; transform: translateY(-6px) scale(0.96); }
.legend-panel-to { opacity: 1; transform: none; }
.legend-panel-leave { transition: opacity var(--dur-fast) ease-in; }

/* ---------------- 窄屏浮动唤起按钮 ---------------- */
.details-jump {
  display: none;
  position: fixed;
  right: 16px;
  bottom: 24px;
  z-index: 10;
  align-items: center;
  gap: 8px;
  border: none;
  border-radius: 999px;
  padding: 10px 16px;
  background: var(--ios-blue);
  color: #fff;
  box-shadow: 0 8px 24px rgba(0, 122, 255, 0.36);
  cursor: pointer;
  font: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  white-space: nowrap;
  animation: details-jump-float var(--dur-loop-float) ease-in-out infinite;
}
.details-jump:active {
  transform: scale(0.96);
}
.details-jump-count {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
@keyframes details-jump-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

/* ---------- 桌面端（≥1025px）：日历在左、明细侧栏在右 ---------- */
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
    /* 首行周标题 auto，其余 5/6 行至少保留 96px，保证当前窗口下能完整放置两条事件摘要 */
    grid-template-rows: auto repeat(var(--cal-rows, 5), minmax(96px, 1fr));
    align-content: stretch;
  }
  .cal-day {
    height: auto;
    min-height: 96px;
  }
  .day-details-card {
    display: block;
    flex: 0 0 auto;
    width: 340px;
    min-width: 0;
    max-height: 100%;
    overflow-y: auto;
    scrollbar-width: thin;
    box-shadow: none;
    margin-left: 12px;
    transition: width var(--dur-medium) var(--ease-decelerate),
      margin-left var(--dur-medium) var(--ease-decelerate),
      padding-inline var(--dur-medium) var(--ease-decelerate),
      opacity var(--dur-base) ease;
  }
  .day-details-card.details-collapsed {
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
  .day-details-card::-webkit-scrollbar-thumb {
    border-radius: 99px;
    background: var(--ios-separator);
  }
  /* 桌面端不使用底部抽屉与浮动按钮 */
  .cal-sheet-root {
    display: none !important;
  }
  .details-jump {
    display: none;
  }
}

/* ---------- 窄屏（≤1024px）：单列，明细走底部抽屉 ---------- */
@media (max-width: 1024px) {
  .cal-page {
    width: 100%;
    max-width: 760px;
    margin-inline: auto;
  }
  .cal-card {
    width: 100%;
  }
  .details-jump {
    display: inline-flex;
  }
}

/* ---------- 平板/手机 ---------- */
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
    padding: 10px;
  }
  .cal-grid {
    gap: 2px;
  }
  .cal-day {
    height: 56px;
    padding: 4px;
  }
  .cal-day-num {
    width: 24px;
    height: 24px;
    font-size: 12px;
  }
  .desktop-events {
    display: none !important;
  }
  .mobile-dots {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    width: 100%;
    overflow: hidden;
  }
  .mob-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .mob-dot.dot-new { background: var(--ios-blue); }
  .mob-dot.dot-due { background: var(--ios-orange); }
  .mob-dot.dot-end { background: var(--ios-red); }
  .mob-dot-more {
    font-size: 9px;
    color: var(--ios-gray);
    line-height: 1;
  }
  /* 图例改用 Popover */
  .cal-legend {
    display: none;
  }
  .cal-legend-popover {
    display: inline-flex;
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
  .cal-title-wrap {
    flex: 1 1 auto;
    min-width: 0;
  }
  .cal-today-btn {
    padding: 0 12px;
  }
  .cal-day {
    height: auto;
    min-height: 48px;
    aspect-ratio: 0.92 / 1;
    padding: 3px;
  }
  .cal-day-num {
    width: 22px;
    height: 22px;
    font-size: 11px;
  }
  .details-jump {
    right: 12px;
    bottom: 18px;
  }
  .cal-sheet-container {
    padding: 0;
    padding-bottom: env(safe-area-inset-bottom);
  }
  .cal-sheet-panel {
    max-width: none;
    border-radius: 20px 20px 0 0;
    padding: 8px 14px calc(16px + env(safe-area-inset-bottom));
  }
  .detail-item {
    gap: 6px;
    padding: 9px 10px;
  }
}

@media (max-width: 360px) {
  .cal-nav {
    gap: 4px;
  }
  .cal-today-btn {
    padding-inline: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .details-jump {
    animation: none;
  }
  .cal-day {
    animation: none;
  }
  .day-details-card,
  .details-body,
  .cal-sheet-backdrop,
  .cal-sheet-panel,
  .cal-legend-panel {
    transition: none !important;
    animation: none;
  }
}
</style>
