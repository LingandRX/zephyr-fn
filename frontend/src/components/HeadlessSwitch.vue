<script setup>
/**
 * HeadlessSwitch 开关组件：
 * iOS 风格的开关，支持 label、description、disabled 属性。
 * 使用原生 button 实现，确保样式正确应用。
 */
const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  label: {
    type: String,
    default: "",
  },
  description: {
    type: String,
    default: "",
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue"]);

function toggle() {
  if (props.disabled) return;
  emit("update:modelValue", !props.modelValue);
}
</script>

<template>
  <div class="switch-wrapper" :class="{ disabled }">
    <button
      type="button"
      class="switch-button"
      :class="{ 'switch-on': modelValue }"
      role="switch"
      :aria-checked="modelValue"
      :disabled="disabled"
      @click="toggle"
    >
      <span class="switch-thumb" />
    </button>
    <label v-if="label" class="switch-label" @click="toggle">
      {{ label }}
      <span v-if="description" class="switch-description">{{ description }}</span>
    </label>
  </div>
</template>

<style scoped>
.switch-wrapper {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.switch-wrapper.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 开关按钮 */
.switch-button {
  position: relative;
  width: 44px;
  height: 26px;
  background-color: var(--border);
  border-radius: 13px;
  border: none;
  padding: 0;
  cursor: pointer;
  transition: background-color 0.2s ease;
  flex-shrink: 0;
}

.switch-button:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.switch-button:disabled {
  cursor: not-allowed;
}

/* 开启状态 */
.switch-on {
  background-color: var(--primary);
}

/* 滑块 */
.switch-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

/* 开启状态：滑块向右移动 */
.switch-on .switch-thumb {
  transform: translateX(18px);
}

/* 标签 */
.switch-label {
  color: var(--text);
  font-size: var(--fs-sm);
  cursor: pointer;
  user-select: none;
}

.switch-description {
  display: block;
  color: var(--muted);
  font-size: var(--fs-xs);
  margin-top: 2px;
}
</style>
