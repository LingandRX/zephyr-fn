<script setup>
// 统计视图：大盘指标卡片 + 近 12 个月趋势（CSS 柱状图带交互 Tooltip）+ 分类支出占比
import { ref, computed, onMounted, onActivated } from "vue";
import { getStatistics } from "../api.js";
import { fmtCents } from "../format.js";
import { toast } from "../ui.js";

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

  return {
    unit: s.currency ? `(单位: ${s.currency})` : "",
    maxAmount: max,
    bars: rawBars.map((m) => {
      const isCurrentMonth = m.month === nowMonth;
      const isZero = !m.amount || m.amount === 0;
      return {
        month: m.month,
        shortMonth: `${parseInt(m.month.slice(5), 10)}月`,
        amount: m.amount,
        formattedAmount: fmtCents(m.amount, s.currency),
        height: isZero ? 2 : Math.max(6, (m.amount / max) * 100),
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
              <div class="trend-bar-wrap">
                <div
                  class="trend-bar"
                  :style="{ height: b.height + '%' }"
                  tabindex="0"
                >
                  <!-- 交互式浮动气泡 Tooltip -->
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
.stats-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* ---------------- 顶部 KPI 卡片 ---------------- */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
  margin-bottom: 0;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: transform 0.18s ease, border-color 0.18s ease;
}

.stat-card:hover {
  border-color: rgba(var(--primary-rgb), 0.4);
}

.stat-card .label {
  color: var(--muted);
  font-size: var(--fs-xs);
  font-weight: 500;
}

.stat-card .value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 8px 0 4px;
  letter-spacing: -0.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat-card .sub {
  color: var(--muted);
  font-size: 11px;
}

/* ---------------- 栅格布局 ---------------- */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  align-items: stretch;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 18px 20px;
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.card-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.card-head .muted {
  font-size: var(--fs-xs);
  font-weight: 400;
}

/* ---------------- 趋势柱状图 ---------------- */
.chart-card {
  min-height: 280px;
}

.trend-chart-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding-top: 24px;
}

.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 180px;
  width: 100%;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.1);
  padding-bottom: 2px;
}

:root[data-theme="light"] .trend-chart {
  border-bottom-color: rgba(0, 0, 0, 0.08);
}

.trend-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
  height: 100%;
  justify-content: flex-end;
  position: relative;
}

.trend-bar-wrap {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  position: relative;
}

.trend-bar {
  width: 100%;
  max-width: 28px;
  background: linear-gradient(180deg, var(--grad-a), var(--grad-b));
  border-radius: 4px 4px 0 0;
  position: relative;
  cursor: pointer;
  transition: height 0.35s cubic-bezier(0.4, 0, 0.2, 1), background 0.2s ease, opacity 0.2s ease;
  outline: none;
}

.trend-bar:hover,
.trend-bar:focus {
  background: linear-gradient(180deg, var(--grad-a), var(--primary));
  filter: brightness(1.1);
}

/* 当月与零支出特殊样式 */
.trend-col.is-current .trend-bar {
  background: linear-gradient(180deg, #38bdf8, #2563eb);
  box-shadow: 0 0 10px rgba(56, 189, 248, 0.35);
}

.trend-col.is-zero .trend-bar {
  background: var(--border);
  opacity: 0.6;
}

/* CSS 悬浮 Tooltip 气泡 */
.trend-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) translateY(4px);
  background: #0b1120;
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  text-align: center;
}

:root[data-theme="light"] .trend-tooltip {
  background: #1e293b;
}

.trend-tooltip::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border-width: 4px;
  border-style: solid;
  border-color: #0b1120 transparent transparent transparent;
}

:root[data-theme="light"] .trend-tooltip::after {
  border-color: #1e293b transparent transparent transparent;
}

.trend-bar:hover .trend-tooltip,
.trend-bar:focus .trend-tooltip {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0);
}

.tooltip-month {
  color: #94a3b8;
  font-size: 10px;
  margin-bottom: 2px;
}

.tooltip-val {
  font-weight: 700;
  color: #38bdf8;
}

.trend-month {
  font-size: 11px;
  color: var(--muted);
  margin-top: 6px;
  white-space: nowrap;
  text-align: center;
}

.trend-col.is-current .trend-month {
  color: var(--text);
  font-weight: 600;
}

/* ---------------- 分类统计 ---------------- */
.cat-card {
  min-height: 280px;
}

.desktop-cat-table {
  width: 100%;
  overflow-x: auto;
  /* 极窄窗口万一溢出时，用细杆自定义滚动条代替浏览器默认滚动条 */
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.desktop-cat-table::-webkit-scrollbar {
  height: 6px;
}
.desktop-cat-table::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--border);
}
.desktop-cat-table::-webkit-scrollbar-track {
  background: transparent;
}
/* 分类表仅 4 列且各占 25%，去掉全局 .table 的 640px 最小宽，
   避免列宽不足时被撑出横向滚动条（桌面端双列布局下每列通常 < 640px） */
.desktop-cat-table .table {
  min-width: 0;
}
/* 长分类名省略号，防止 25% 列被内容撑开 */
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
  gap: 8px;
  font-weight: 500;
}

.cat-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}

.amount-cell {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.muted-cell {
  color: var(--muted);
  font-size: var(--fs-xs);
}

.pct-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.pct-bar-bg {
  flex: 1;
  height: 6px;
  background: var(--bg-2);
  border-radius: 3px;
  overflow: hidden;
}

.pct-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--grad-a), var(--grad-b));
  border-radius: 3px;
  transition: width 0.4s ease;
}

.pct-text {
  font-size: 11px;
  color: var(--muted);
  min-width: 32px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.mobile-cat-list {
  display: none;
  flex-direction: column;
  gap: 12px;
}

.mobile-cat-item {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mobile-cat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--fs-sm);
}

.mobile-cat-name {
  display: flex;
  align-items: center;
  gap: 6px;
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
  font-size: 11px;
}

/* ---------------- 骨架屏动画 ---------------- */
@keyframes shimmer {
  0% { opacity: 0.5; }
  50% { opacity: 0.9; }
  100% { opacity: 0.5; }
}

.skeleton-line {
  background: var(--card-2);
  border-radius: 4px;
  animation: shimmer 1.5s infinite ease-in-out;
}

.skeleton-line.sm { height: 12px; width: 50%; margin-bottom: 8px; }
.skeleton-line.md { height: 16px; width: 70%; }
.skeleton-line.lg { height: 24px; width: 80%; margin-bottom: 6px; }
.skeleton-line.xs { height: 10px; width: 40%; }

.chart-skeleton {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 180px;
  padding-top: 24px;
}

.skeleton-bar {
  flex: 1;
  background: var(--card-2);
  border-radius: 4px 4px 0 0;
  height: 60%;
  animation: shimmer 1.5s infinite ease-in-out;
}
.skeleton-bar:nth-child(2n) { height: 85%; animation-delay: 0.2s; }
.skeleton-bar:nth-child(3n) { height: 40%; animation-delay: 0.4s; }

.cat-skeleton {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 10px;
}

.cat-skeleton-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* ---------------- 响应式断点适配 ---------------- */

/* 平板 / 小屏桌面 (<= 860px) */
@media (max-width: 860px) {
  .grid-2 {
    grid-template-columns: minmax(0, 1fr);
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 手机端 (<= 600px) */
@media (max-width: 600px) {
  .stats-view {
    gap: var(--space-3);
  }
  
  /* 2x2 紧凑 KPI 网格，消除 4 单行占满屏幕问题 */
  .stats-grid {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 8px;
  }
  
  .stat-card {
    padding: 12px;
    border-radius: 10px;
  }

  .stat-card .value {
    font-size: 17px;
    margin: 4px 0 2px;
  }

  .stat-card .label {
    font-size: 11px;
  }

  .stat-card .sub {
    font-size: 10px;
  }

  .card {
    padding: 14px;
    border-radius: 10px;
  }

  .trend-chart {
    gap: 4px;
    height: 150px;
  }

  .trend-bar {
    border-radius: 2px 2px 0 0;
  }

  .trend-month {
    font-size: 10px;
    margin-top: 4px;
  }

  /* 隐藏桌面端宽表格，使用专为手机设计的卡片式列表 */
  .desktop-cat-table {
    display: none;
  }

  .mobile-cat-list {
    display: flex;
  }
}
</style>
