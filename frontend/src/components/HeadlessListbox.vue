<script setup>
import { computed } from "vue";
import {
  Listbox,
  ListboxButton,
  ListboxOptions,
  ListboxOption,
} from "@headlessui/vue";

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean, null],
    default: "",
  },
  options: {
    type: Array,
    default: () => [],
  },
  placeholder: {
    type: String,
    default: "请选择",
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  clearable: {
    type: Boolean,
    default: true,
  },
  clearValue: {
    type: [String, Number, Boolean, null],
    default: "",
  },
  emptyText: {
    type: String,
    default: "暂无选项",
  },
});

const emit = defineEmits(["update:modelValue", "change", "clear"]);

// 标准化选项格式，兼容对象数组和简单数组
const normalizedOptions = computed(() => {
  return props.options.map((opt) => {
    if (typeof opt === "object" && opt !== null) {
      return {
        label:
          opt.label !== undefined
            ? opt.label
            : opt.name || String(opt.value ?? ""),
        value: opt.value !== undefined ? opt.value : opt.id,
      };
    }
    return { label: String(opt), value: opt };
  });
});

// 当前选中的选项
const selectedOption = computed(() => {
  return normalizedOptions.value.find((opt) => opt.value === props.modelValue);
});

// 是否有选中值
const hasValue = computed(() => {
  return (
    props.modelValue !== "" &&
    props.modelValue !== null &&
    props.modelValue !== undefined &&
    props.modelValue !== props.clearValue
  );
});

// 是否可清除
const canClear = computed(() => {
  return props.clearable && !props.disabled && hasValue.value;
});

// 显示的标签文本
const displayLabel = computed(() => {
  if (selectedOption.value) {
    return selectedOption.value.label;
  }
  return props.placeholder;
});

// 处理值变化
function handleChange(value) {
  if (props.disabled) return;
  emit("update:modelValue", value);
  emit("change", value);
}

// 处理清除
function handleClear(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  emit("update:modelValue", props.clearValue);
  emit("change", props.clearValue);
  emit("clear");
}
</script>

<template>
  <div
    class="custom-select"
    :class="{ 'is-disabled': disabled, 'can-clear': canClear }"
  >
    <Listbox
      :model-value="modelValue"
      @update:model-value="handleChange"
      :disabled="disabled"
      as="div"
      class="listbox-wrapper"
    >
      <ListboxButton
        class="custom-select-trigger"
        :class="{ 'is-disabled': disabled }"
      >
        <span
          class="custom-select-label"
          :class="{ 'is-placeholder': !selectedOption && placeholder }"
        >
          {{ displayLabel }}
        </span>
        <div class="custom-select-actions">
          <button
            v-if="canClear"
            type="button"
            class="custom-select-clear-btn"
            title="清除"
            aria-label="清除选中项"
            @pointerdown.stop
            @touchstart.stop
            @click.stop.prevent="handleClear"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 1024 1024"
              fill="currentColor"
            >
              <path
                d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"
              />
            </svg>
          </button>
          <span class="custom-select-arrow" aria-hidden="true">
            <svg
              width="12"
              height="12"
              viewBox="0 0 1024 1024"
              fill="currentColor"
            >
              <path
                d="M512 704a32 32 0 0 1-22.6-9.4l-320-320a32 32 0 1 1 45.2-45.2L512 602.8l275.4-275.4a32 32 0 1 1 45.2 45.2l-320 320A32 32 0 0 1 512 704z"
              />
            </svg>
          </span>
        </div>
      </ListboxButton>

      <ListboxOptions class="custom-select-dropdown">
        <template v-if="normalizedOptions.length > 0">
          <ListboxOption
            v-for="opt in normalizedOptions"
            :key="opt.value"
            :value="opt.value"
            v-slot="{ active, selected }"
            as="template"
          >
            <li
              class="custom-select-option"
              :class="{ 'is-active': active, 'is-selected': selected }"
            >
              <span class="option-label">{{ opt.label }}</span>
              <span v-if="selected" class="option-check" aria-hidden="true">
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 1024 1024"
                  fill="currentColor"
                >
                  <path
                    d="M384 768a32 32 0 0 1-22.6-9.4L137.4 534.6a32 32 0 1 1 45.2-45.2L384 690.8l457.4-457.4a32 32 0 1 1 45.2 45.2l-480 480A32 32 0 0 1 384 768z"
                  />
                </svg>
              </span>
            </li>
          </ListboxOption>
        </template>
        <li v-else class="custom-select-empty" aria-disabled="true">
          <span>{{ emptyText }}</span>
        </li>
      </ListboxOptions>
    </Listbox>
  </div>
</template>

<style scoped>
/* =====================================================================
 * HeadlessListbox · iOS 风格（分组列表下拉）
 * iOS 令牌来自 styles/tokens.css（--ios-*，已全局可用）
 * ===================================================================== */

.custom-select {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

.listbox-wrapper {
  position: relative;
  width: 100%;
}

.custom-select:has([data-headlessui-state*="open"]),
.listbox-wrapper[data-headlessui-state*="open"] {
  z-index: 50;
}

/* ---------------- 触发器（iOS 表单字段） ---------------- */
.custom-select-trigger {
  width: 100%;
  height: 38px;
  box-sizing: border-box;
  padding: 0 8px 0 12px;
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text);
  font-size: var(--fs-sm);
  font-family: inherit;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  cursor: pointer;
  outline: none;
  transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
  text-align: left;
}

.custom-select-trigger:hover {
  background: var(--ios-separator);
}

.custom-select-trigger:focus-visible,
.custom-select:has([data-headlessui-state*="open"]) .custom-select-trigger,
.listbox-wrapper[data-headlessui-state*="open"] .custom-select-trigger {
  background: var(--ios-card-bg);
  border-color: var(--ios-blue);
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.custom-select-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-select-label.is-placeholder {
  color: var(--ios-gray);
}

.custom-select-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-shrink: 0;
}

.custom-select-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--ios-gray);
  transition: transform 0.2s ease, color 0.18s ease;
  cursor: pointer;
}

.custom-select:has([data-headlessui-state*="open"]) .custom-select-arrow,
.listbox-wrapper[data-headlessui-state*="open"] .custom-select-arrow {
  transform: rotate(180deg);
  color: var(--ios-blue);
}

.custom-select-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: var(--ios-separator);
  color: var(--ios-gray);
  cursor: pointer;
  outline: none;
  transition: color 0.18s ease, background-color 0.18s ease;
}

.custom-select-clear-btn:hover {
  color: var(--text);
  background: var(--ios-fill);
}

.custom-select-trigger.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---------------- 下拉面板（iOS 分组列表） ---------------- */
.custom-select-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  width: 100%;
  min-width: 100%;
  max-height: 264px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--ios-separator) transparent;
  box-sizing: border-box;
  margin: 0;
  padding: 6px;
  list-style: none;
  outline: none;
  z-index: var(--z-notice);
  background: var(--ios-card-bg);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  backdrop-filter: saturate(180%) blur(24px);
  border: 1px solid var(--ios-card-border);
  border-radius: 14px;
  box-shadow: var(--ios-shadow-panel);
  animation: csl-dropdown-in 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes csl-dropdown-in {
  from {
    opacity: 0;
    transform: translateY(-6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

/* 细滚动条 */
.custom-select-dropdown::-webkit-scrollbar {
  width: 4px;
}
.custom-select-dropdown::-webkit-scrollbar-track {
  background: transparent;
}
.custom-select-dropdown::-webkit-scrollbar-thumb {
  background: var(--ios-separator);
  border-radius: 4px;
}

.custom-select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 38px;
  padding: 8px 12px;
  border-radius: 10px;
  color: var(--text);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.custom-select-option.is-active {
  background: var(--ios-fill);
}

.custom-select-option.is-selected {
  color: var(--ios-blue);
  font-weight: 600;
}

.custom-select-option.is-selected.is-active {
  background: var(--ios-blue-soft);
}

.custom-select-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px 10px;
  color: var(--ios-gray);
  font-size: var(--fs-xs);
  user-select: none;
  cursor: default;
}

.option-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.option-check {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  color: var(--ios-blue);
  flex-shrink: 0;
}

@media (prefers-reduced-motion: reduce) {
  .custom-select-dropdown {
    animation: none;
  }
}
</style>
