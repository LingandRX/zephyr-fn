<script setup>
import { ref, computed } from "vue";
import { Dialog, DialogPanel, DialogTitle } from "@headlessui/vue";
import {
  subscriptionTemplates,
  TEMPLATE_CATEGORIES,
  getPopularTemplates,
  getTemplatesByCategory,
  searchTemplates,
  getAllCategories,
} from "../data/subscriptionTemplates.js";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue", "select"]);

const searchQuery = ref("");
const activeCategory = ref("all");
const chipsRef = ref(null);
const chipsScrollLeft = ref(0);
const chipsMaxScroll = ref(0);

function onChipsWheel(e) {
  // 桌面端：将垂直滚轮转换为横向平滑滚动
  if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
    e.preventDefault();
    const el = chipsRef.value;
    if (el) el.scrollBy({ left: e.deltaY * 1.5, behavior: "smooth" });
  }
}

function updateChipsScrollState() {
  const el = chipsRef.value;
  if (!el) return;
  chipsScrollLeft.value = el.scrollLeft;
  chipsMaxScroll.value = el.scrollWidth - el.clientWidth;
}

const chipsShowLeftFade = computed(() => chipsScrollLeft.value > 4);
const chipsShowRightFade = computed(() => chipsScrollLeft.value < chipsMaxScroll.value - 4);

const categories = computed(() => getAllCategories());

const filteredTemplates = computed(() => {
  if (searchQuery.value) {
    return searchTemplates(searchQuery.value);
  }
  if (activeCategory.value === "all") {
    return subscriptionTemplates;
  }
  if (activeCategory.value === "popular") {
    return getPopularTemplates();
  }
  return getTemplatesByCategory(activeCategory.value);
});

const isEmpty = computed(() => filteredTemplates.value.length === 0);

const groupedTemplates = computed(() => {
  const templates = filteredTemplates.value;
  if (activeCategory.value === "popular" || searchQuery.value) {
    return [
      {
        key: "result",
        label: searchQuery.value ? "搜索结果" : "热门推荐",
        icon: searchQuery.value ? "" : "🔥",
        templates,
      },
    ];
  }

  const groups = {};
  templates.forEach((t) => {
    if (!groups[t.category]) {
      const cat = TEMPLATE_CATEGORIES[t.category];
      groups[t.category] = {
        key: t.category,
        label: cat ? cat.label : "其他",
        icon: cat ? cat.icon : "📱",
        templates: [],
      };
    }
    groups[t.category].templates.push(t);
  });

  return Object.values(groups);
});

/** iOS 系统色：用于列表行的图标底色 */
const CATEGORY_TINTS = {
  video: "#ff3b30",
  music: "#ff2d55",
  cloud: "#0a84ff",
  reading: "#ff9500",
  shopping: "#ffcc00",
  social: "#34c759",
  tools: "#5856d6",
  gaming: "#af52de",
  education: "#007aff",
  other: "#8e8e93",
};

function iconOf(category) {
  const cat = TEMPLATE_CATEGORIES[category];
  return cat ? cat.icon : "📱";
}

function tintOf(category) {
  const base = CATEGORY_TINTS[category] || CATEGORY_TINTS.other;
  return `${base}26`; // 约 15% 透明度
}

function formatAmount(template) {
  if (template.amount === 0) return "按需";
  const amount = (template.amount / 100).toFixed(2);
  const symbol = template.currency === "USD" ? "$" : "¥";
  const suffix =
    template.period_type === "month"
      ? "/月"
      : template.period_type === "year"
        ? "/年"
        : template.period_type === "quarter"
          ? "/季"
          : "";
  return `${symbol}${amount}${suffix}`;
}

function selectTemplate(template) {
  emit("select", template);
  close();
}

function close() {
  emit("update:modelValue", false);
  searchQuery.value = "";
  activeCategory.value = "all";
}
</script>

<template>
  <Dialog :open="modelValue" @close="close" class="template-dialog-root">
    <div class="template-dialog-backdrop" aria-hidden="true" />

    <div class="template-dialog-container">
      <DialogPanel class="template-sheet">
        <!-- 移动端抓手 -->
        <div class="sheet-grabber" aria-hidden="true" />

        <!-- 顶部导航：取消 + 标题 -->
        <header class="sheet-header">
          <button type="button" class="sheet-cancel" @click="close">取消</button>
          <DialogTitle as="h2" class="sheet-title">选择模板</DialogTitle>
          <span class="sheet-header-spacer" aria-hidden="true" />
        </header>

        <!-- 搜索框 -->
        <div class="sheet-search">
          <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle
              cx="11"
              cy="11"
              r="7"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            />
            <path
              d="M20 20l-3.6-3.6"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
          <input
            v-model="searchQuery"
            type="search"
            class="search-field"
            placeholder="搜索会员服务"
            autocomplete="off"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="search-clear"
            aria-label="清空搜索"
            @click="searchQuery = ''"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="9" fill="currentColor" />
              <path
                d="M9 9l6 6M15 9l-6 6"
                fill="none"
                stroke="#fff"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>

        <!-- 分类胶囊（横向滚动，桌面端鼠标滚轮也能横向滑动） -->
        <div
          ref="chipsRef"
          class="sheet-chips-wrap"
          :class="{ 'has-left-fade': chipsShowLeftFade, 'has-right-fade': chipsShowRightFade }"
          @scroll="updateChipsScrollState"
        >
          <div
            class="sheet-chips"
            @wheel.prevent="onChipsWheel"
          >
            <button
              type="button"
              class="chip"
              :class="{ 'is-active': activeCategory === 'all' }"
              @click="activeCategory = 'all'"
            >
              全部
            </button>
            <button
              type="button"
              class="chip"
              :class="{ 'is-active': activeCategory === 'popular' }"
              @click="activeCategory = 'popular'"
            >
              🔥 热门
            </button>
            <button
              v-for="cat in categories"
              :key="cat.id"
              type="button"
              class="chip"
              :class="{ 'is-active': activeCategory === cat.id }"
              @click="activeCategory = cat.id"
            >
              {{ cat.icon }} {{ cat.label }}
            </button>
          </div>
        </div>

        <!-- 分组列表 -->
        <div class="sheet-list">
          <section
            v-for="group in groupedTemplates"
            v-show="group.templates.length"
            :key="group.key"
            class="ios-section"
          >

            <ul class="ios-list">
              <li
                v-for="template in group.templates"
                :key="template.id"
                class="ios-row-item"
              >
                <button type="button" class="ios-row" @click="selectTemplate(template)">
                  <span
                    class="ios-row-icon"
                    :style="{ backgroundColor: tintOf(template.category) }"
                  >
                    {{ iconOf(template.category) }}
                  </span>

                  <span class="ios-row-body">
                    <span class="ios-row-title">
                      {{ template.name }}
                      <span v-if="template.popular" class="ios-badge">热门</span>
                    </span>
                    <span v-if="template.notes" class="ios-row-sub">
                      {{ template.notes }}
                    </span>
                  </span>

                  <span class="ios-row-trailing">
                    <span class="ios-row-price">{{ formatAmount(template) }}</span>
                    <svg class="ios-chevron" viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        d="M9 6l6 6-6 6"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </span>
                </button>
              </li>
            </ul>
          </section>

          <!-- 空状态 -->
          <div v-if="isEmpty" class="sheet-empty">
            <span class="sheet-empty-icon">🔍</span>
            <p class="sheet-empty-title">未找到匹配的模板</p>
            <p class="sheet-empty-hint">换个关键词试试</p>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

<style scoped>
/* =====================================================================
 * 订阅模板选择器 · iOS 分组列表风格
 * 结构：圆角 Sheet（移动端底部弹出） + 搜索框 + 分类胶囊 + 分组列表
 * 颜色沿用项目令牌，形状/间距/层级仿 iOS
 * ===================================================================== */

:global(.template-dialog-root) {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

:global(.template-dialog-backdrop) {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  -webkit-backdrop-filter: blur(3px);
  backdrop-filter: blur(3px);
  animation: ts-fade-in 0.2s ease-out;
}

:global(.template-dialog-container) {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  pointer-events: none;
}

/* ---------------- Sheet 容器 ---------------- */
.template-sheet {
  /* 局部主题变量：默认暗色，浅色在下方覆盖 */
  --ts-sheet: var(--card);
  --ts-row: var(--card-2);
  --ts-sep: rgba(255, 255, 255, 0.08);
  --ts-fill: rgba(120, 120, 128, 0.24);
  --ts-fill-strong: rgba(120, 120, 128, 0.42);
  --ts-label: var(--text);
  --ts-muted: var(--muted);
  --ts-chevron: #636366;
  /* iOS 系统蓝（暗色外观） */
  --ts-accent: #0a84ff;

  pointer-events: auto;
  width: 440px;
  max-width: 100%;
  height: 580px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  background: var(--ts-sheet);
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.36);
  overflow: hidden;
  animation: ts-pop-in 0.34s cubic-bezier(0.32, 0.72, 0, 1);
}

:global(:root[data-theme="light"]) .template-sheet {
  --ts-sheet: var(--card-2);
  --ts-row: var(--card);
  --ts-sep: rgba(60, 60, 67, 0.16);
  --ts-fill: rgba(118, 118, 128, 0.12);
  --ts-fill-strong: rgba(118, 118, 128, 0.26);
  --ts-chevron: #c7c7cc;
  /* iOS 系统蓝（浅色外观） */
  --ts-accent: #007aff;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.16);
}

/* 移动端抓手（桌面隐藏） */
.sheet-grabber {
  display: none;
  flex: none;
  width: 36px;
  height: 5px;
  margin: 8px auto 0;
  border-radius: var(--radius-full);
  background: var(--ts-fill-strong);
}

/* ---------------- 顶部导航 ---------------- */
.sheet-header {
  flex: none;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--space-2);
  padding: 14px 0 10px;
}

.sheet-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.2px;
  color: var(--ts-label);
  text-align: center;
  white-space: nowrap;
}

.sheet-cancel {
  justify-self: start;
  padding: 0;
  border: none;
  background: none;
  color: var(--ts-accent);
  font-family: inherit;
  font-size: 17px;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.sheet-cancel:active {
  opacity: 0.5;
}

.sheet-header-spacer {
  justify-self: end;
}

/* ---------------- 搜索框 ---------------- */
.sheet-search {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  margin: 0;
  padding: 0 8px 0 10px;
  border-radius: 10px;
  background: var(--ts-fill);
  color: var(--ts-muted);
}

.search-icon {
  flex: none;
  width: 16px;
  height: 16px;
}

.search-field {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--ts-label);
  font-family: inherit;
  font-size: 16px; /* 16px 避免 iOS Safari 聚焦缩放 */
  -webkit-appearance: none;
  appearance: none;
}

.search-field:focus {
  outline: none;
  border: none;
}

.search-field::placeholder {
  color: var(--ts-muted);
}

.search-field::-webkit-search-cancel-button {
  display: none;
}

.search-clear {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: none;
  color: var(--ts-muted);
  cursor: pointer;
}

.search-clear svg {
  width: 18px;
  height: 18px;
}

/* ---------------- 分类胶囊（外层滚动容器） ---------------- */
.sheet-chips-wrap {
  flex: none;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  border-bottom: 1px solid var(--ts-sep);
  scroll-behavior: smooth;
  /* 两侧渐变遮罩，提示还有更多内容 */
  --fade-width: 32px;
  mask-image: none;
  -webkit-mask-image: none;
}

/* 左侧可滚动时显示渐变 */
.sheet-chips-wrap.has-left-fade {
  mask-image: linear-gradient(
    to right,
    transparent 0px,
    black var(--fade-width)
  );
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0px,
    black var(--fade-width)
  );
}

/* 右侧可滚动时显示渐变 */
.sheet-chips-wrap.has-right-fade {
  mask-image: linear-gradient(
    to left,
    transparent 0px,
    black var(--fade-width)
  );
  -webkit-mask-image: linear-gradient(
    to left,
    transparent 0px,
    black var(--fade-width)
  );
}

/* 两侧都有渐变 */
.sheet-chips-wrap.has-left-fade.has-right-fade {
  mask-image: linear-gradient(
    to right,
    transparent 0px,
    black var(--fade-width),
    black calc(100% - var(--fade-width)),
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0px,
    black var(--fade-width),
    black calc(100% - var(--fade-width)),
    transparent 100%
  );
}

.sheet-chips-wrap::-webkit-scrollbar {
  display: none;
}

/* 桌面端：鼠标悬停时显示极细滚动条，提示可滚动 */
@media (hover: hover) and (pointer: fine) {
  .sheet-chips-wrap::-webkit-scrollbar {
    display: block;
    height: 3px;
  }
  .sheet-chips-wrap::-webkit-scrollbar-thumb {
    background: var(--ts-fill-strong);
    border-radius: 99px;
  }
  .sheet-chips-wrap::-webkit-scrollbar-track {
    background: transparent;
  }
  .sheet-chips-wrap:hover::-webkit-scrollbar-thumb {
    background: var(--ts-accent);
  }
}

/* ---------------- 分类胶囊（内容行） ---------------- */
.sheet-chips {
  display: flex;
  gap: 8px;
  padding: 12px 0 10px;
  /* 禁止文本选中，提升滚轮/拖拽体验 */
  user-select: none;
  -webkit-user-select: none;
}

.chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--ts-fill);
  color: var(--ts-label);
  font-family: inherit;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease, transform 0.12s ease;
}

.chip:active {
  transform: scale(0.96);
}

.chip.is-active {
  background: var(--ts-accent);
  color: #fff;
  font-weight: 600;
}

/* ---------------- 列表区 ---------------- */
.sheet-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 8px 0 20px;
  scrollbar-width: none;
}

.sheet-list::-webkit-scrollbar {
  display: none;
}

.ios-section {
  margin-bottom: 20px;
}


.ios-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-radius: var(--radius-md);
  background: var(--ts-row);
  overflow: hidden;
}

.ios-row-item {
  position: relative;
}

/* 分隔线：左侧与文字对齐（图标 36 + 间距 12 + 内边距 14） */
.ios-row-item + .ios-row-item::before {
  content: "";
  position: absolute;
  top: 0;
  left: 62px;
  right: 0;
  height: 1px;
  background: var(--ts-sep);
}

.ios-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 58px;
  padding: 10px 14px;
  border: none;
  background: none;
  color: var(--ts-label);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease;
}

.ios-row:active {
  background: var(--ts-fill);
}

.ios-row-icon {
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  font-size: 19px;
  line-height: 1;
}

.ios-row-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ios-row-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.1px;
  color: var(--ts-label);
  line-height: 1.3;
}

.ios-badge {
  flex: none;
  padding: 1px 6px;
  border-radius: 5px;
  background: rgba(255, 149, 0, 0.16);
  color: #ff9500;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
}

.ios-row-sub {
  overflow: hidden;
  color: var(--ts-muted);
  font-size: 13px;
  line-height: 1.4;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.ios-row-trailing {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ios-row-price {
  color: var(--ts-accent);
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.ios-chevron {
  width: 16px;
  height: 16px;
  color: var(--ts-chevron);
}

/* ---------------- 空状态 ---------------- */
.sheet-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 64px 24px;
  color: var(--ts-muted);
}

.sheet-empty-icon {
  font-size: 40px;
  line-height: 1;
}

.sheet-empty-title {
  margin: 8px 0 0;
  color: var(--ts-label);
  font-size: 15px;
  font-weight: 600;
}

.sheet-empty-hint {
  margin: 0;
  font-size: 13px;
}

/* ---------------- 动画 ---------------- */
@keyframes ts-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes ts-pop-in {
  from { opacity: 0; transform: scale(0.96) translateY(10px); }
  to { opacity: 1; transform: none; }
}

@keyframes ts-sheet-up {
  from { transform: translateY(100%); }
  to { transform: none; }
}

/* ---------------- 移动端：底部 Sheet ---------------- */
@media (max-width: 860px) {
  :global(.template-dialog-container) {
    align-items: flex-end;
    padding: 0;
  }

  .template-sheet {
    width: 100%;
    max-width: 100%;
    height: auto;
    max-height: 90vh;
    max-height: 90dvh;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    animation: ts-sheet-up 0.4s cubic-bezier(0.32, 0.72, 0, 1);
  }

  .sheet-grabber {
    display: block;
  }

  .sheet-header {
    padding-top: 10px;
  }

  .ios-row-item + .ios-row-item::before {
    left: 62px;
  }
}

@media (prefers-reduced-motion: reduce) {
  :global(.template-dialog-backdrop),
  .template-sheet {
    animation: none;
  }
  .chip,
  .ios-row {
    transition: none;
  }
}
</style>
