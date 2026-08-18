<script setup>
// 日历视图：按月渲染扣费 / 服务到期事件（移植自 vanilla app.js renderCalendar）
import { ref, onMounted } from "vue";
import { getCalendar } from "../api.js";
import { toast } from "../ui.js";

const now = new Date();
const calYear = ref(now.getFullYear());
const calMonth = ref(now.getMonth() + 1);
const events = ref([]);

// 6 行 7 列 = 42 格，保证布局稳定
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
  const prevDays = new Date(year, month - 1, 0).getDate();

  const cells = [];
  for (let i = 0; i < startDow; i++) {
    const d = new Date(year, month - 1, -startDow + i + 1);
    cells.push({ day: d.getDate(), other: true });
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const ds = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    cells.push({
      day,
      today: ds === todayStr,
      events: (byDate[ds] || []).slice(0, 3),
      more: byDate[ds]?.length > 3 ? byDate[ds].length - 3 : 0,
    });
  }
  for (let i = 1; cells.length < 42; i++) cells.push({ day: i, other: true });

  grid.value = cells;
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

onMounted(loadMonth);
</script>

<template>
  <div class="page">
    <div class="cal-head">
      <button class="btn" @click="prevMonth(-1)">‹</button>
      <h2>{{ calYear }} 年 {{ calMonth }} 月</h2>
      <button class="btn" @click="prevMonth(1)">›</button>
      <button class="btn btn-ghost" @click="goToday">今天</button>
    </div>
    <div class="card">
      <div class="cal-grid">
        <div v-for="(d, i) in ['日', '一', '二', '三', '四', '五', '六']" :key="'dow-' + i" class="cal-dow">{{ d }}</div>
        <div
          v-for="(c, i) in grid" :key="i"
          class="cal-day" :class="{ other: c.other, today: c.today }"
        >
          <div class="num">{{ c.day }}</div>
          <template v-if="c.events">
            <div
              v-for="(e, j) in c.events" :key="j"
              class="cal-event" :class="e.event_type === 'service_end' ? 'end' : 'due'"
              :title="`${e.name} ${e.amount_formatted}`"
            >{{ e.name }} {{ e.amount_formatted }}</div>
            <div v-if="c.more" class="cal-event muted">+{{ c.more }}</div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cal-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.cal-head h2 { margin: 0 auto 0 0; font-size: 18px; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.cal-dow { text-align: center; color: var(--muted); font-size: var(--fs-xs); padding: 6px 0; }
.cal-day {
  min-height: 76px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 6px; background: var(--bg-2); position: relative;
}
.cal-day.other { opacity: 0.35; }
.cal-day.today { border-color: var(--primary); }
.cal-day .num { font-size: var(--fs-xs); color: var(--muted); }
.cal-event {
  font-size: 11px; background: var(--card-2); border-radius: 4px; padding: 1px 5px;
  margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cal-event.due { border-left: 2px solid var(--amber); }
.cal-event.end { border-left: 2px solid var(--red); }
.cal-event.muted { opacity: 0.7; border-left-color: var(--border); }
</style>