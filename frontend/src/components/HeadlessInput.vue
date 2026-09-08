<script setup>
/**
 * HeadlessInput 通用输入框组件：
 * 支持 v-model 双向绑定、类型、占位符、禁用状态、错误提示。
 * 使用 CSS 变量确保与设计系统一致。
 */
const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: '',
  },
  type: {
    type: String,
    default: 'text',
  },
  placeholder: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  label: {
    type: String,
    default: '',
  },
  min: {
    type: [String, Number],
    default: undefined,
  },
  max: {
    type: [String, Number],
    default: undefined,
  },
  step: {
    type: [String, Number],
    default: undefined,
  },
  autocomplete: {
    type: String,
    default: undefined,
  },
});

const emit = defineEmits(['update:modelValue', 'focus', 'blur']);
</script>

<template>
  <div class="headless-input-wrapper" :class="{ 'has-error': error }">
    <label v-if="label" class="input-label">{{ label }}</label>
    <input
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :min="min"
      :max="max"
      :step="step"
      :autocomplete="autocomplete"
      class="headless-input"
      @input="emit('update:modelValue', $event.target.value)"
      @focus="emit('focus', $event)"
      @blur="emit('blur', $event)"
    />
    <span v-if="error" class="input-error">{{ error }}</span>
  </div>
</template>

<style scoped>
.headless-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.input-label {
  color: var(--muted);
  font-size: var(--fs-xs);
}

.headless-input {
  background: var(--bg-2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) 10px;
  font-size: var(--fs-sm);
  font-family: inherit;
  transition: border-color 0.15s ease;
  width: 100%;
  box-sizing: border-box;
}

.headless-input:focus {
  outline: none;
  border-color: var(--primary);
}

.headless-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.headless-input::placeholder {
  color: var(--muted);
}

.has-error .headless-input {
  border-color: var(--red);
}

.input-error {
  color: var(--red);
  font-size: var(--fs-xs);
}
</style>
