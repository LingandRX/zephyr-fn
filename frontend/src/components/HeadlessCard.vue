<script setup>
/**
 * HeadlessCard 卡片组件：
 * 用于内容分组和视觉隔离。
 * 支持标题、自定义内容。
 */
const props = defineProps({
  title: {
    type: String,
    default: '',
  },
});
</script>

<template>
  <div class="headless-card">
    <h3 v-if="title" class="card-title">{{ title }}</h3>
    <div class="card-content">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.headless-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
}

.card-title {
  margin: 0 0 var(--space-3);
  font-size: var(--fs-md);
  color: var(--text);
  font-weight: 600;
}

.card-content {
  /* 内容区域 */
}
</style>
