<script setup>
/**
 * HeadlessButton 通用按钮组件：
 * 支持多种变体（default/primary/ghost/danger）、尺寸（sm/md/lg）、禁用状态、块级显示。
 * 使用 CSS 变量确保与设计系统一致。
 */
const props = defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'primary', 'ghost', 'danger'].includes(v),
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v),
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  block: {
    type: Boolean,
    default: false,
  },
  type: {
    type: String,
    default: 'button',
  },
});

const emit = defineEmits(['click']);
</script>

<template>
  <button
    :type="type"
    class="headless-btn"
    :class="[
      `btn-${variant}`,
      `btn-${size}`,
      { 'btn-block': block, 'btn-disabled': disabled }
    ]"
    :disabled="disabled"
    @click="emit('click', $event)"
  >
    <slot />
  </button>
</template>

<style scoped>
.headless-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
  background: transparent;
  color: inherit;
  padding: 0;
}

.headless-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* 尺寸变体 */
.btn-sm {
  height: 32px;
  padding: 0 12px;
  font-size: var(--fs-xs);
}

.btn-md {
  height: 38px;
  padding: 0 16px;
  font-size: var(--fs-sm);
}

.btn-lg {
  height: 44px;
  padding: 0 20px;
  font-size: var(--fs-md);
}

/* 颜色变体 */
.btn-default {
  background: var(--card-2);
  color: var(--text);
}

.btn-default:hover:not(:disabled) {
  border-color: var(--primary);
}

.btn-primary {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-2);
}

.btn-ghost {
  background: transparent;
  border-color: transparent;
  color: var(--text);
}

.btn-ghost:hover:not(:disabled) {
  background: var(--card);
}

.btn-danger {
  background: var(--red);
  border-color: var(--red);
  color: #fff;
}

.btn-danger:hover:not(:disabled) {
  filter: brightness(0.9);
}

/* 状态 */
.btn-block {
  width: 100%;
}

.btn-disabled,
.headless-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
