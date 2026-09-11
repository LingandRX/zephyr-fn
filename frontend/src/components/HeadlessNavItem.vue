<script setup>
/**
 * HeadlessNavItem 导航项组件：
 * 支持图标、激活状态、折叠模式。
 * 使用 CSS 变量确保与设计系统一致。
 */
const props = defineProps({
  icon: {
    type: String,
    default: '',
  },
  label: {
    type: String,
    required: true,
  },
  active: {
    type: Boolean,
    default: false,
  },
  collapsed: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['click']);
</script>

<template>
  <button
    type="button"
    class="headless-nav-item"
    :class="{ active, collapsed }"
    @click="emit('click')"
  >
    <span v-if="icon" class="nav-icon" aria-hidden="true">
      <svg class="nav-item-icon" viewBox="0 0 1024 1024" fill="currentColor">
        <path :d="icon" />
      </svg>
    </span>
    <span class="nav-label">{{ label }}</span>
  </button>
</template>

<style scoped>
.headless-nav-item {
  width: 100%;
  height: 40px;
  padding: 0 10px;
  border: none;
  background: transparent;
  color: var(--muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--fs-md);
  font-family: inherit;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: background var(--dur-fast) ease, color var(--dur-fast) ease;
  position: relative;
  white-space: nowrap;
  overflow: hidden;
  text-align: left;
}

.headless-nav-item:hover {
  background: var(--card);
  color: var(--text);
}

.headless-nav-item.active {
  background: rgba(var(--primary-rgb), 0.15);
  color: #fff;
  font-weight: 500;
}

.headless-nav-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--primary);
}

.headless-nav-item:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

/* 折叠模式 */
.headless-nav-item.collapsed {
  padding: 0;
  justify-content: center;
  gap: 0;
}

.headless-nav-item.collapsed .nav-label {
  opacity: 0;
  width: 0;
  pointer-events: none;
  position: absolute;
}

/* 图标 */
.nav-icon {
  width: 20px;
  font-size: 16px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-item-icon {
  width: 20px;
  height: 20px;
}

/* 标签 */
.nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
