<script setup>
// 统计视图：大盘卡片 + 近 12 个月趋势（纯 CSS 柱状图）+ 分类统计
// 移植自 vanilla app.js renderStatistics
import { ref, computed, onMounted } from "vue";
import { getStatistics } from "../api.js";
import { fmtCents } from "../format.js";
import { toast } from "../ui.js";

const stats = ref(null);

const bigCards = computed(() => {
  const s = stats.value;
  if (!s) return [];
  const cur = s.currency;
  return [
    { label: "本月支出", value: fmtCents(s.monthly_expense, cur) },
    { label: "本月实际到期", value: fmtCents(s.monthly_actual_expense, cur) },
    { label: "年支出", value: fmtCents(s.yearly_expense, cur) },
    { label: "未来 30 天", value: fmtCents(s.upcoming_30_days, cur) },
  ];
});

const trend = computed(() => {
  const s = stats.value;
  if (!s) return { unit: "", bars: [] };
  const max = Math.max(...s.monthly_trend.map((m) => m.amount), 1);
  return {
    unit: `(单位: ${s.currency})`,
    bars: s.monthly_trend.map((m) => ({
      month: m.month,
      label: `${m.month.slice(5)}月`,
      height: Math.max(2, (m.amount / max) * 100),
      title: `${m.month} ${fmtCents(m.amount, s.currency)}`,
    })),
  };
});

const catRows = computed(() => {
  const s = stats.value;
  if (!s) return [];
  const cur = s.currency;
  return s.category_stats.map((c) => ({
    ...c,
    amount: fmtCents(c.amount, cur),
    yearly: fmtCents(c.yearly_amount, cur),
  }));
});

async function load() {
  try {
    stats.value = await getStatistics();
  } catch (err) {
    toast(err.message, "err");
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <div v-if="stats" class="stats-grid">
      <div v-for="c in bigCards" :key="c.label" class="stat-card">
        <div class="label">{{ c.label }}</div>
        <div class="value">{{ c.value }}</div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>近 12 个月趋势 <span class="muted">{{ trend.unit }}</span></h3>
        <div class="trend-chart" v-if="trend.bars.length">
          <div v-for="(b, i) in trend.bars" :key="i" class="trend-col">
            <div class="trend-bar-wrap">
              <div class="trend-bar" :style="{ height: b.height + '%' }" :title="b.title"></div>
            </div>
            <div class="trend-month">{{ b.label }}</div>
          </div>
        </div>
        <div v-else class="empty">暂无数据</div>
      </div>

      <div class="card">
        <h3>分类统计</h3>
        <div class="table-scroll">
          <table class="table">
            <thead>
              <tr><th>分类</th><th>月支出</th><th>年支出</th><th>占比</th></tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in catRows" :key="i">
                <td>{{ c.category_name }}</td>
                <td>{{ c.amount }}</td>
                <td>{{ c.yearly }}</td>
                <td>{{ c.percentage }}%</td>
              </tr>
              <tr v-if="!catRows.length"><td colspan="4" class="muted">暂无数据</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); }
.trend-chart { display: flex; align-items: flex-end; gap: 6px; height: 160px; padding-top: var(--space-2); }
.trend-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: var(--space-1); min-width: 0; }
.trend-bar-wrap { width: 100%; height: 130px; display: flex; align-items: flex-end; }
.trend-bar {
  width: 100%; background: linear-gradient(180deg, var(--primary), #8b5cf6);
  border-radius: 4px 4px 0 0; min-height: 2px;
}
.trend-month { font-size: 10px; color: var(--muted); transform: rotate(-30deg); white-space: nowrap; }

/* 响应式降级（全局断点约定见 tokens.css） */
@media (max-width: 860px) {
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
}
</style>