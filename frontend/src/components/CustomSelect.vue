<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";

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
});

const emit = defineEmits(["update:modelValue", "change", "clear"]);

const isOpen = ref(false);
const selectRef = ref(null);

const normalizedOptions = computed(() => {
  return props.options.map((opt) => {
    if (typeof opt === "object" && opt !== null) {
      return {
        label: opt.label !== undefined ? opt.label : opt.name || String(opt.value ?? ""),
        value: opt.value !== undefined ? opt.value : opt.id,
      };
    }
    return { label: String(opt), value: opt };
  });
});

const selectedOption = computed(() => {
  return normalizedOptions.value.find((opt) => opt.value === props.modelValue);
});

const hasValue = computed(() => {
  return props.modelValue !== "" && props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== props.clearValue;
});

const canClear = computed(() => {
  return props.clearable && !props.disabled && hasValue.value;
});

const displayLabel = computed(() => {
  if (selectedOption.value) {
    return selectedOption.value.label;
  }
  return props.placeholder;
});

function toggleDropdown() {
  if (props.disabled) return;
  isOpen.value = !isOpen.value;
}

function closeDropdown() {
  isOpen.value = false;
}

function selectOption(opt, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  emit("update:modelValue", opt.value);
  emit("change", opt.value);
  closeDropdown();
}

function handleClear(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  if (props.disabled) return;
  emit("update:modelValue", props.clearValue);
  emit("change", props.clearValue);
  emit("clear");
  closeDropdown();
}

function handleKeydown(e) {
  if (props.disabled) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    toggleDropdown();
  } else if (e.key === "Escape") {
    closeDropdown();
  }
}

function handleClickOutside(event) {
  if (selectRef.value && !selectRef.value.contains(event.target)) {
    closeDropdown();
  }
}

onMounted(() => {
  if (typeof document !== "undefined") {
    document.addEventListener("pointerdown", handleClickOutside);
  }
});

onBeforeUnmount(() => {
  if (typeof document !== "undefined") {
    document.removeEventListener("pointerdown", handleClickOutside);
  }
});
</script>

<template>
  <div
    ref="selectRef"
    class="custom-select"
    :class="{ 'is-open': isOpen, 'is-disabled': disabled, 'can-clear': canClear }"
    @keydown="handleKeydown"
  >
    <div
      class="custom-select-trigger"
      :class="{ 'is-disabled': disabled }"
      :tabindex="disabled ? -1 : 0"
      :aria-expanded="isOpen"
      role="combobox"
      @click="toggleDropdown"
    >
      <span class="custom-select-label" :class="{ 'is-placeholder': !selectedOption && placeholder }">
        {{ displayLabel }}
      </span>
      <div class="custom-select-actions" @click.stop>
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
          <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M556.8 512L832 236.8c12.8-12.8 12.8-32 0-44.8-12.8-12.8-32-12.8-44.8 0L512 467.2l-275.2-277.333333c-12.8-12.8-32-12.8-44.8 0-12.8 12.8-12.8 32 0 44.8l275.2 277.333333-277.333333 275.2c-12.8 12.8-12.8 32 0 44.8 6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333L512 556.8 787.2 832c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466666-8.533333c12.8-12.8 12.8-32 0-44.8L556.8 512z"/>
          </svg>
        </button>
        <span class="custom-select-arrow" aria-hidden="true" @click.stop="toggleDropdown">
          <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
            <path d="M512 704a32 32 0 0 1-22.6-9.4l-320-320a32 32 0 1 1 45.2-45.2L512 602.8l275.4-275.4a32 32 0 1 1 45.2 45.2l-320 320A32 32 0 0 1 512 704z" />
          </svg>
        </span>
      </div>
    </div>

    <transition name="dropdown-fade">
      <div v-if="isOpen" class="custom-select-dropdown" @click.stop>
        <ul class="custom-select-options">
          <li
            v-for="opt in normalizedOptions"
            :key="opt.value"
            class="custom-select-option"
            :class="{ 'is-selected': opt.value === modelValue }"
            @pointerdown.stop
            @mousedown.stop
            @click.stop="selectOption(opt, $event)"
          >
            <span class="option-label">{{ opt.label }}</span>
            <span v-if="opt.value === modelValue" class="option-check" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 1024 1024" fill="currentColor">
                <path d="M384 768a32 32 0 0 1-22.6-9.4L137.4 534.6a32 32 0 1 1 45.2-45.2L384 690.8l457.4-457.4a32 32 0 1 1 45.2 45.2l-480 480A32 32 0 0 1 384 768z" />
              </svg>
            </span>
          </li>
        </ul>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.custom-select {
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  user-select: none;
  font-size: var(--fs-sm);
}

.custom-select.is-open {
  z-index: 50;
}

.custom-select-trigger {
  width: 100%;
  height: 38px;
  box-sizing: border-box;
  padding: 0 8px 0 12px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: var(--fs-sm);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  text-align: left;
}

.custom-select-trigger:focus-visible,
.custom-select.is-open .custom-select-trigger {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(var(--primary-rgb), 0.2);
}

.custom-select-label {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-select-label.is-placeholder {
  color: var(--muted);
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
  color: var(--muted);
  transition: transform 0.2s ease, opacity 0.15s ease, color 0.15s ease;
  cursor: pointer;
}

.custom-select.is-open .custom-select-arrow {
  transform: rotate(180deg);
  color: var(--primary);
}

.custom-select-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 50%;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
  outline: none;
}

.custom-select-clear-btn:hover {
  color: var(--text);
  background-color: var(--card);
}

.custom-select-trigger.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.custom-select-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  width: 100%;
  min-width: 100%;
  max-height: 240px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-modal);
  z-index: var(--z-notice);
  box-sizing: border-box;
}

/* 细长自定义滚动条 (WebKit) */
.custom-select-dropdown::-webkit-scrollbar {
  width: 4px;
}

.custom-select-dropdown::-webkit-scrollbar-track {
  background: transparent;
}

.custom-select-dropdown::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
  transition: background-color 0.15s ease;
}

.custom-select-dropdown::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}

.custom-select-options {
  list-style: none;
  margin: 0;
  padding: 4px;
}

.custom-select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 4px;
  color: var(--text);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.custom-select-option:hover {
  background-color: var(--card-2);
}

.custom-select-option.is-selected {
  color: var(--primary);
  font-weight: 600;
  background-color: rgba(var(--primary-rgb), 0.1);
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
  color: var(--primary);
  flex-shrink: 0;
}

/* 动效 */
.dropdown-fade-enter-active,
.dropdown-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dropdown-fade-enter-from,
.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
