<script setup>
// 统计视图：大盘指标卡片 + 近 12 个月趋势（CSS 柱状图带交互 Tooltip）+ 分类支出占比
import { ref, computed, onMounted, onActivated } from "vue";
import { getStatistics } from "../services/api.js";
import { fmtCents } from "../utils/format.js";
import { toast } from "../utils/ui.js";


const stats = ref(null);
const loading = ref(true);

const bigCards = computed(() => {
  const s = stats.value;
  if (!s) return [];
  const cur = s.currency;
  return [
    {
      label: "本月预估支出",
      value: fmtCents(s.monthly_expense, cur),
      sub: "按月平摊估算",
    },
    {
      label: "本月实际到期",
      value: fmtCents(s.monthly_actual_expense, cur),
      sub: "当月实际需付",
    },
    {
      label: "年平摊支出",
      value: fmtCents(s.yearly_expense, cur),
      sub: "年度总预算估算",
    },
    {
      label: "未来 30 天",
      value: fmtCents(s.upcoming_30_days, cur),
      sub: "即将扣费金额",
    },
  ];
});

const trend = computed(() => {
  const s = stats.value;
  if (!s || !s.monthly_trend) return { unit: "", bars: [], maxAmount: 0 };
  const rawBars = s.monthly_trend;
  const max = Math.max(...rawBars.map((m) => m.amount), 1);
  const nowMonth = new Date().toISOString().slice(0, 7);
  const CHART_HEIGHT = 200;

  return {
    unit: s.currency ? `(单位: ${s.currency})` : "",
    maxAmount: max,
    bars: rawBars.map((m) => {
      const isCurrentMonth = m.month === nowMonth;
      const isZero = !m.amount || m.amount === 0;
      const pct = isZero ? 0 : m.amount / max;
      return {
        month: m.month,
        shortMonth: `${parseInt(m.month.slice(5), 10)}月`,
        amount: m.amount,
        formattedAmount: fmtCents(m.amount, s.currency),
        barHeight: isZero ? 4 : Math.max(8, pct * CHART_HEIGHT),
        isCurrentMonth,
        isZero,
      };
    }),
  };
});

const catRows = computed(() => {
  const s = stats.value;
  if (!s || !s.category_stats) return [];
  const cur = s.currency;
  // 按月支出金额从大到小降序排列
  return [...s.category_stats]
    .sort((a, b) => (b.amount || 0) - (a.amount || 0))
    .map((c) => ({
      ...c,
      monthlyFmt: fmtCents(c.amount, cur),
      yearlyFmt: fmtCents(c.yearly_amount, cur),
      pct: Math.min(Math.max(Number(c.percentage) || 0, 0), 100),
    }));
});

async function load() {
  loading.value = true;
  try {
    stats.value = await getStatistics();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
// keep-alive 下切回本页不会重新 onMounted，需在 onActivated 重新拉取，
// 否则在其他页面新增订阅后切回时统计仍显示旧数据。
onActivated(load);
</script>

<template>
  <div class="page stats-view">
    <!-- 1. 骨架屏加载态 -->
    <div v-if="loading" class="stats-grid skeleton-grid">
      <div v-for="i in 4" :key="i" class="stat-card skeleton-card">
        <div class="skeleton-line sm"></div>
        <div class="skeleton-line lg"></div>
        <div class="skeleton-line xs"></div>
      </div>
    </div>

    <!-- 2. KPI 指标卡片 -->
    <div v-else-if="stats" class="stats-grid">
      <div v-for="c in bigCards" :key="c.label" class="stat-card">
        <div class="label">{{ c.label }}</div>
        <div class="value">{{ c.value }}</div>
        <div class="sub">{{ c.sub }}</div>
      </div>
    </div>

    <!-- 3. 主内容区（趋势图 + 分类统计） -->
    <div class="grid-2">
      <!-- 近 12 个月支出趋势 -->
      <div class="card chart-card">
        <div class="card-head">
          <h3>
            近 12 个月支出趋势
            <span class="muted">{{ trend.unit }}</span>
          </h3>
        </div>

        <div v-if="loading" class="chart-skeleton">
          <div v-for="i in 12" :key="i" class="skeleton-bar"></div>
        </div>

        <div v-else-if="trend.bars.length" class="trend-chart-container">
          <div class="trend-chart">
            <div
              v-for="(b, i) in trend.bars"
              :key="i"
              class="trend-col"
              :class="{ 'is-current': b.isCurrentMonth, 'is-zero': b.isZero }"
            >
              <div class="trend-tooltip-anchor">
                <div
                  class="trend-bar"
                  :style="{ height: b.barHeight + 'px' }"
                  tabindex="0"
                >
                  <div class="trend-tooltip">
                    <div class="tooltip-month">{{ b.month }}</div>
                    <div class="tooltip-val">{{ b.formattedAmount }}</div>
                  </div>
                </div>
              </div>
              <div class="trend-month" :title="b.month">{{ b.shortMonth }}</div>
            </div>
          </div>
        </div>

        <div v-else class="empty">暂无支出趋势数据</div>
      </div>

      <!-- 分类统计 -->
      <div class="card cat-card">
        <div class="card-head">
          <h3>分类支出统计</h3>
        </div>

        <div v-if="loading" class="cat-skeleton">
          <div v-for="i in 4" :key="i" class="cat-skeleton-row">
            <div class="skeleton-line md"></div>
            <div class="skeleton-line lg"></div>
          </div>
        </div>

        <!-- 桌面端完整表格 -->
        <div v-else-if="catRows.length" class="desktop-cat-table">
          <table class="table">
            <thead>
              <tr>
                <th style="width: 25%">分类</th>
                <th style="width: 25%">月支出</th>
                <th style="width: 25%">年支出</th>
                <th style="width: 25%">占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in catRows" :key="i">
                <td class="cat-name-cell">
                  <span class="cat-dot"></span>
                  <span class="cat-name">{{ c.category_name }}</span>
                </td>
                <td class="amount-cell">{{ c.monthlyFmt }}</td>
                <td class="amount-cell muted-cell">{{ c.yearlyFmt }}</td>
                <td>
                  <div class="pct-bar-wrap">
                    <div class="pct-bar-bg">
                      <div class="pct-bar-fill" :style="{ width: c.pct + '%' }"></div>
                    </div>
                    <span class="pct-text">{{ c.percentage }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 移动端卡片列表（无横向滚动条，体验更顺畅） -->
        <div v-if="catRows.length && !loading" class="mobile-cat-list">
          <div v-for="(c, i) in catRows" :key="i" class="mobile-cat-item">
            <div class="mobile-cat-header">
              <div class="mobile-cat-name">
                <span class="cat-dot"></span>
                <span>{{ c.category_name }}</span>
              </div>
              <div class="mobile-cat-amounts">
                <span class="mobile-monthly">{{ c.monthlyFmt }}/月</span>
                <span class="mobile-yearly muted">({{ c.yearlyFmt }}/年)</span>
              </div>
            </div>
            <div class="pct-bar-wrap">
              <div class="pct-bar-bg">
                <div class="pct-bar-fill" :style="{ width: c.pct + '%' }"></div>
              </div>
              <span class="pct-text">{{ c.percentage }}%</span>
            </div>
          </div>
        </div>

        <div v-else-if="!loading && !catRows.length" class="empty">暂无分类统计数据</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* =====================================================================
 * 统计页 · iOS 风格
 * 圆角毛玻璃卡片 / SF 风格排版 / 柔和渐变柱状图 / 悬浮气泡
 * ===================================================================== */

/* iOS 系统色板 */
:root {
  --ios-blue: #007aff;
  --ios-blue-soft: rgba(0, 122, 255, 0.12);
  --ios-green: #34c759;
  --ios-orange: #ff9500;
  --ios-red: #ff3b30;
  --ios-purple: #af52de;
  --ios-teal: #5ac8fa;
  --ios-pink: #ff2d55;
  --ios-indigo: #5856d6;
  --ios-gray: #8e8e93;
  --ios-separator: rgba(60, 60, 67, 0.12);
  --ios-card-bg: rgba(255, 255, 255, 0.72);
  --ios-card-border: rgba(255, 255, 255, 0.5);
}

:root[data-theme="dark"] {
  --ios-separator: rgba(255, 255, 255, 0.08);
  --ios-card-bg: rgba(28, 28, 30, 0.72);
  --ios-card-border: rgba(255, 255, 255, 0.08);
}

.stats-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---------------- 顶部 KPI 卡片 ---------------- */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.stat-card {
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 16px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.25s ease;
  position: relative;
  overflow: hidden;
}

/* 卡片顶部装饰渐变条 */
.stat-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--grad-a), var(--grad-b));
  border-radius: 16px 16px 0 0;
  opacity: 0.8;
}

.stat-card:nth-child(1)::before { background: linear-gradient(90deg, #34c759, #30d158); }
.stat-card:nth-child(2)::before { background: linear-gradient(90deg, #007aff, #5ac8fa); }
.stat-card:nth-child(3)::before { background: linear-gradient(90deg, #ff9500, #ffb340); }
.stat-card:nth-child(4)::before { background: linear-gradient(90deg, #af52de, #da7cfc); }

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

:root[data-theme="dark"] .stat-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
}

.stat-card .label {
  color: var(--ios-gray);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.stat-card .value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  margin: 10px 0 6px;
  letter-spacing: -0.6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}

.stat-card .sub {
  color: var(--ios-gray);
  font-size: 12px;
  font-weight: 400;
}

/* ---------------- 栅格布局 ---------------- */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: stretch;
}

.card {
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 16px;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-head h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-head .muted {
  font-size: 12px;
  font-weight: 400;
  color: var(--ios-gray);
}

/* ---------------- 趋势柱状图 ---------------- */
.chart-card {
  min-height: 300px;
}

.trend-chart-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding-top: 16px;
}

.trend-chart {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 6px;
  height: 200px;
  width: 100%;
  border-bottom: 1px solid var(--ios-separator);
  position: relative;
}

.trend-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  position: relative;
}

.trend-tooltip-anchor {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: flex-end;
  flex: 1 1 auto;
  min-height: 0;
}

.trend-bar {
  width: 100%;
  max-width: 28px;
  background: linear-gradient(180deg, var(--ios-teal), var(--ios-blue));
  border-radius: 8px 8px 2px 2px;
  position: relative;
  cursor: pointer;
  transition: background 0.25s ease, box-shadow 0.25s ease, transform 0.2s ease;
  outline: none;
  flex-shrink: 0;
}

.trend-bar:hover,
.trend-bar:focus-visible {
  background: linear-gradient(180deg, #5ac8fa, var(--ios-blue));
  box-shadow: 0 4px 16px rgba(0, 122, 255, 0.3);
  transform: scaleY(1.05);
  transform-origin: bottom;
}

/* 当月 */
.trend-col.is-current .trend-bar {
  background: linear-gradient(180deg, #5ac8fa, #007aff);
  box-shadow: 0 4px 20px rgba(0, 122, 255, 0.35);
}

.trend-col.is-current .trend-bar:hover {
  box-shadow: 0 6px 24px rgba(0, 122, 255, 0.45);
}

/* 零支出 */
.trend-col.is-zero .trend-bar {
  background: var(--ios-gray);
  opacity: 0.25;
}

.trend-col.is-zero .trend-month {
  opacity: 0.5;
}

/* iOS 毛玻璃 Tooltip 气泡 */
.trend-tooltip {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%) translateY(6px) scale(0.92);
  background: rgba(30, 30, 30, 0.88);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  padding: 8px 12px;
  font-size: 12px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease, transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), visibility 0.2s;
  z-index: 10;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.24);
  text-align: center;
  min-width: 80px;
}

.trend-tooltip::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border-width: 5px;
  border-style: solid;
  border-color: rgba(30, 30, 30, 0.88) transparent transparent transparent;
}

.trend-bar:hover .trend-tooltip,
.trend-bar:focus-visible .trend-tooltip {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0) scale(1);
}

.tooltip-month {
  color: rgba(255, 255, 255, 0.55);
  font-size: 11px;
  margin-bottom: 3px;
  font-weight: 500;
}

.tooltip-val {
  font-weight: 700;
  color: #fff;
  font-size: 15px;
  letter-spacing: -0.3px;
}

.trend-month {
  font-size: 12px;
  color: var(--ios-gray);
  margin-top: 8px;
  white-space: nowrap;
  text-align: center;
  font-weight: 500;
  transition: color 0.2s ease;
}

.trend-col.is-current .trend-month {
  color: var(--ios-blue);
  font-weight: 600;
}

.trend-col:hover .trend-month {
  color: var(--text);
}

/* ---------------- 分类统计 ---------------- */
.cat-card {
  min-height: 300px;
}

.desktop-cat-table {
  width: 100%;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.desktop-cat-table::-webkit-scrollbar {
  height: 4px;
}
.desktop-cat-table::-webkit-scrollbar-thumb {
  border-radius: 99px;
  background: var(--ios-separator);
}
.desktop-cat-table::-webkit-scrollbar-track {
  background: transparent;
}

.desktop-cat-table .table {
  min-width: 0;
}

.desktop-cat-table .table thead th {
  font-size: 12px;
  font-weight: 600;
  color: var(--ios-gray);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ios-separator);
}

.desktop-cat-table .table tbody tr {
  transition: background 0.15s ease;
}

.desktop-cat-table .table tbody tr:hover {
  background: rgba(var(--primary-rgb, 0, 122, 255), 0.04);
}

.desktop-cat-table .table tbody td {
  padding: 12px 0;
  border-bottom: 1px solid var(--ios-separator);
}

.cat-name {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.cat-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 500;
}

.cat-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ios-blue);
  flex-shrink: 0;
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.amount-cell {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 14px;
}

.muted-cell {
  color: var(--ios-gray);
  font-size: 12px;
  font-weight: 400;
}

.pct-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.pct-bar-bg {
  flex: 1;
  height: 8px;
  background: rgba(120, 120, 128, 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.pct-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--ios-blue), var(--ios-teal));
  border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.pct-text {
  font-size: 13px;
  color: var(--ios-gray);
  min-width: 40px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.mobile-cat-list {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.mobile-cat-item {
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--ios-card-border);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mobile-cat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
}

.mobile-cat-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.mobile-cat-amounts {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.mobile-monthly {
  font-weight: 600;
  color: var(--text);
}

.mobile-yearly {
  font-size: 12px;
  color: var(--ios-gray);
}

/* ---------------- 骨架屏动画 ---------------- */
@keyframes ios-shimmer {
  0% { opacity: 0.4; }
  50% { opacity: 0.8; }
  100% { opacity: 0.4; }
}

.skeleton-line {
  background: var(--card-2);
  border-radius: 8px;
  animation: ios-shimmer 1.8s infinite ease-in-out;
}

.skeleton-line.sm { height: 12px; width: 50%; margin-bottom: 8px; }
.skeleton-line.md { height: 16px; width: 70%; }
.skeleton-line.lg { height: 28px; width: 80%; margin-bottom: 6px; }
.skeleton-line.xs { height: 10px; width: 40%; }

.chart-skeleton {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 6px;
  height: 200px;
  padding-top: 16px;
}

.skeleton-bar {
  width: 100%;
  max-width: 28px;
  justify-self: center;
  align-self: end;
  background: var(--card-2);
  border-radius: 8px 8px 2px 2px;
  height: 60%;
  animation: ios-shimmer 1.8s infinite ease-in-out;
}
.skeleton-bar:nth-child(2n) { height: 85%; animation-delay: 0.2s; }
.skeleton-bar:nth-child(3n) { height: 40%; animation-delay: 0.4s; }

.cat-skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 10px;
}

.cat-skeleton-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* ---------------- 响应式断点适配 ---------------- */

@media (max-width: 860px) {
  .grid-2 {
    grid-template-columns: minmax(0, 1fr);
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .stats-view {
    gap: 14px;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 10px;
  }

  .stat-card {
    padding: 14px 16px;
    border-radius: 14px;
  }

  .stat-card .value {
    font-size: 22px;
    margin: 6px 0 4px;
  }

  .stat-card .label {
    font-size: 12px;
  }

  .stat-card .sub {
    font-size: 11px;
  }

  .card {
    padding: 16px;
    border-radius: 14px;
  }

  .card-head h3 {
    font-size: 16px;
  }

  .trend-chart {
    gap: 4px;
    height: 160px;
  }

  .trend-bar {
    max-width: 18px;
    border-radius: 6px 6px 2px 2px;
  }

  .desktop-cat-table {
    display: none;
  }

  .mobile-cat-list {
    display: flex;
  }
}
</style>
