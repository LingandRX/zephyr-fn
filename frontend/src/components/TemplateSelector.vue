<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from "vue";
import { Dialog, DialogPanel, DialogTitle } from "@headlessui/vue";
import {
  subscriptionTemplates,
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
const listRef = ref(null);
const chipsScrollLeft = ref(0);
const chipsMaxScroll = ref(0);
// 弹窗打开时把焦点交给面板本身，避免首焦点落在「取消」上出现焦点框
const sheetRef = ref(null);

function onChipsWheel(e) {
  // 桌面端：将垂直滚轮转换为横向平滑滚动。
  // 注意：不能在模板上写 @wheel.prevent——那会无条件吞掉横向 delta，
  // 导致触控板双指横滑 / Shift+滚轮无法原生滚动。只拦纵向。
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

/** 把当前选中的分类胶囊滚进可见区域（居中，且不影响页面纵向滚动） */
function scrollActiveChipIntoView() {
  chipsRef.value
    ?.querySelector(".chip.is-active")
    ?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
}

// 内容/容器尺寸变化时重算左右渐隐状态（首次打开时 maxScroll 也能立即算对）
let chipsRO = null;
watch(chipsRef, (el) => {
  chipsRO?.disconnect();
  chipsRO = null;
  if (!el || typeof ResizeObserver === "undefined") return;
  chipsRO = new ResizeObserver(updateChipsScrollState);
  chipsRO.observe(el);
  updateChipsScrollState();
});
onBeforeUnmount(() => chipsRO?.disconnect());

// 每次打开：重算渐隐 + 让选中分类回到视野
watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return;
    await nextTick();
    updateChipsScrollState();
    scrollActiveChipIntoView();
  },
);

// 切换分类/搜索时，列表回到顶部（否则会停在上一个分类的滚动位置）
watch([activeCategory, searchQuery], () => {
  if (listRef.value) listRef.value.scrollTop = 0;
});

function selectCategory(id) {
  activeCategory.value = id;
  nextTick(scrollActiveChipIntoView);
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


/** 列表行图标：统一用名称首字符，与订阅列表头像保持一致 */
function initialOf(name) {
  const t = String(name ?? "").trim();
  return t ? [...t][0].toUpperCase() : "?";
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
  <Dialog
    :open="modelValue"
    :initial-focus="sheetRef"
    @close="close"
    class="template-dialog-root"
  >
    <div class="template-dialog-backdrop" aria-hidden="true" />

    <div class="template-dialog-container">
      <DialogPanel ref="sheetRef" class="template-sheet">
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
            @wheel="onChipsWheel"
          >
            <button
              type="button"
              class="chip"
              :class="{ 'is-active': activeCategory === 'all' }"
              @click="selectCategory('all')"
            >
              全部
            </button>
            <button
              type="button"
              class="chip"
              :class="{ 'is-active': activeCategory === 'popular' }"
              @click="selectCategory('popular')"
            >
              热门
            </button>
            <button
              v-for="cat in categories"
              :key="cat.id"
              type="button"
              class="chip"
              :class="{ 'is-active': activeCategory === cat.id }"
              @click="selectCategory(cat.id)"
            >
              {{ cat.label }}
            </button>
          </div>
        </div>

        <!-- 列表：拍平成单一连续列表（按数据顺序），避免多段圆角分组显得零碎 -->
        <div ref="listRef" class="sheet-list">
          <ul v-if="!isEmpty" class="ios-list">
            <li
              v-for="template in filteredTemplates"
              :key="template.id"
              class="ios-row-item"
            >
              <button type="button" class="ios-row" @click="selectTemplate(template)">
                <span class="ios-row-icon">{{ initialOf(template.name) }}</span>

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

          <!-- 空状态 -->
          <div v-else class="sheet-empty">
            <svg
              class="sheet-empty-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.6-3.6" stroke-linecap="round" />
            </svg>
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
 * 配色收敛：图标统一用名称首字符（与订阅列表头像一致），分类胶囊去 emoji，
 * 列表拍平为单一连续列表；iOS 令牌来自 styles/tokens.css（--ios-*）
 * ===================================================================== */

:global(.template-dialog-root) {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

:global(.template-dialog-backdrop) {
  position: fixed;
  inset: 0;
  /* Dialog 根节点是 Fragment，根类拿不到本组件的 scoped data-v，规则不生效；z-index 必须写在自己的元素上 */
  z-index: 9999;
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
  pointer-events: auto;
  width: 440px;
  max-width: 100%;
  height: 580px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  backdrop-filter: saturate(180%) blur(24px);
  border: 1px solid var(--ios-card-border);
  border-radius: 18px;
  box-shadow: var(--ios-shadow-panel);
  overflow: hidden;
  animation: ts-pop-in 0.34s cubic-bezier(0.32, 0.72, 0, 1);
}

/* 移动端抓手（桌面隐藏） */
.sheet-grabber {
  display: none;
  flex: none;
  width: 36px;
  height: 5px;
  margin: 8px auto 0;
  border-radius: var(--radius-full);
  background: var(--ios-separator);
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
  color: var(--text);
  text-align: center;
  white-space: nowrap;
}

.sheet-cancel {
  justify-self: start;
  padding: 0;
  border: none;
  background: none;
  color: var(--ios-blue);
  font-family: inherit;
  font-size: 17px;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.sheet-cancel:active {
  opacity: 0.5;
}

.sheet-cancel:focus {
  outline: none;
}

.sheet-cancel:focus-visible {
  outline: none;
  border-radius: 8px;
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
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
  background: var(--ios-fill);
  color: var(--ios-gray);
  transition: box-shadow 0.18s ease;
}

.sheet-search:focus-within {
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
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
  color: var(--text);
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
  color: var(--ios-gray);
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
  color: var(--ios-gray);
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
  border-bottom: 1px solid var(--ios-separator);
  scroll-behavior: smooth;
  --fade-width: 32px;
}

/* 左侧可滚动时显示渐变 */
.sheet-chips-wrap.has-left-fade {
  mask-image: linear-gradient(to right, transparent 0px, black var(--fade-width));
  -webkit-mask-image: linear-gradient(to right, transparent 0px, black var(--fade-width));
}

/* 右侧可滚动时显示渐变 */
.sheet-chips-wrap.has-right-fade {
  mask-image: linear-gradient(to left, transparent 0px, black var(--fade-width));
  -webkit-mask-image: linear-gradient(to left, transparent 0px, black var(--fade-width));
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
    background: var(--ios-separator);
    border-radius: 99px;
  }
  .sheet-chips-wrap::-webkit-scrollbar-track {
    background: transparent;
  }
}

/* ---------------- 分类胶囊（内容行） ---------------- */
.sheet-chips {
  display: flex;
  gap: 8px;
  padding: 12px 0 10px;
  user-select: none;
  -webkit-user-select: none;
}

.chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--ios-fill);
  color: var(--text);
  font-family: inherit;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.18s ease, color 0.18s ease, transform 0.12s ease;
}

.chip:active {
  transform: scale(0.96);
}

.chip.is-active {
  background: var(--ios-blue);
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

.ios-list {
  list-style: none;
  margin: 0;
  padding: 0;
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
  background: var(--ios-separator);
}

.ios-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 58px;
  padding: 10px 14px;
  border: none;
  border-radius: 12px;
  background: none;
  color: var(--text);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.ios-row:active {
  background: var(--ios-fill);
}

/* 图标统一为「名称首字符」圆角块，与订阅列表头像同一套视觉 */
.ios-row-icon {
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--ios-blue-soft);
  color: var(--ios-blue);
  font-size: 15px;
  font-weight: 700;
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
  color: var(--text);
  line-height: 1.3;
}

/* 「热门」标签：中性浅灰，不再抢视觉 */
.ios-badge {
  flex: none;
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--ios-fill);
  color: var(--ios-gray);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
}

.ios-row-sub {
  overflow: hidden;
  color: var(--ios-gray);
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
  color: var(--ios-blue);
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.ios-chevron {
  width: 16px;
  height: 16px;
  color: var(--ios-gray);
  opacity: 0.6;
}

/* ---------------- 空状态 ---------------- */
.sheet-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 64px 24px;
  color: var(--ios-gray);
}

.sheet-empty-icon {
  width: 40px;
  height: 40px;
  color: var(--ios-gray);
  opacity: 0.5;
}

.sheet-empty-title {
  margin: 8px 0 0;
  color: var(--text);
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
    border-radius: 18px 18px 0 0;
    animation: ts-sheet-up 0.4s cubic-bezier(0.32, 0.72, 0, 1);
  }

  .sheet-grabber {
    display: block;
  }

  .sheet-header {
    padding-top: 10px;
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
