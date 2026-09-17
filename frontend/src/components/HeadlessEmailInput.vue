<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: "",
  },
  placeholder: {
    type: String,
    default: "",
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  type: {
    type: String,
    default: "text",
  },
  autocomplete: {
    type: String,
    default: "off",
  },
  spellcheck: {
    type: Boolean,
    default: false,
  },
  suffixes: {
    type: Array,
    default: () => [
      "qq.com",
      "163.com",
      "126.com",
      "gmail.com",
      "outlook.com",
      "exmail.qq.com",
      "aliyun.com",
      "sina.com",
      "139.com",
      "foxmail.com",
      "icloud.com",
      "hotmail.com",
    ],
  },
});

const emit = defineEmits([
  "update:modelValue",
  "input",
  "change",
  "blur",
  "focus",
  "select",
]);

const wrapperRef = ref(null);
const inputRef = ref(null);
const isOpen = ref(false);
const activeIndex = ref(0);

// 计算当前匹配的邮箱后缀建议
const filteredSuggestions = computed(() => {
  const val = String(props.modelValue || "");
  const atIndex = val.indexOf("@");
  if (atIndex === -1) return [];

  const prefix = val.slice(0, atIndex);
  const query = val.slice(atIndex + 1).toLowerCase();

  // 若存在多个 @，不予联想
  if (query.includes("@")) return [];

  return props.suffixes
    .filter((suffix) => suffix.toLowerCase().startsWith(query))
    .map((suffix) => ({
      prefix,
      suffix,
      full: `${prefix}@${suffix}`,
    }));
});

function updateDropdownState(val) {
  const text = String(val || "");
  const atIndex = text.indexOf("@");
  if (atIndex === -1) {
    isOpen.value = false;
    return;
  }
  const query = text.slice(atIndex + 1).toLowerCase();
  if (query.includes("@")) {
    isOpen.value = false;
    return;
  }
  const matches = props.suffixes.filter((s) =>
    s.toLowerCase().startsWith(query)
  );
  // 若用户已精准完整输入完毕该后缀，自动收起下拉
  if (matches.length === 1 && matches[0].toLowerCase() === query) {
    isOpen.value = false;
    return;
  }
  isOpen.value = matches.length > 0;
  activeIndex.value = 0;
}

function handleInput(e) {
  const val = e.target.value;
  emit("update:modelValue", val);
  emit("input", e);
  updateDropdownState(val);
}

function handleFocus(e) {
  emit("focus", e);
}

function handleBlur(e) {
  emit("blur", e);
}

function selectSuggestion(item) {
  const fullVal = item.full;
  emit("update:modelValue", fullVal);
  emit("change", fullVal);
  emit("select", fullVal);
  isOpen.value = false;
  activeIndex.value = 0;
  inputRef.value?.focus();
}

function handleKeydown(e) {
  if (!isOpen.value || filteredSuggestions.value.length === 0) {
    return;
  }

  if (e.key === "ArrowDown") {
    e.preventDefault();
    activeIndex.value =
      (activeIndex.value + 1) % filteredSuggestions.value.length;
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    activeIndex.value =
      (activeIndex.value - 1 + filteredSuggestions.value.length) %
      filteredSuggestions.value.length;
  } else if (e.key === "Enter") {
    if (
      activeIndex.value >= 0 &&
      activeIndex.value < filteredSuggestions.value.length
    ) {
      e.preventDefault();
      selectSuggestion(filteredSuggestions.value[activeIndex.value]);
    }
  } else if (e.key === "Tab") {
    if (
      activeIndex.value >= 0 &&
      activeIndex.value < filteredSuggestions.value.length
    ) {
      selectSuggestion(filteredSuggestions.value[activeIndex.value]);
    }
  } else if (e.key === "Escape") {
    e.preventDefault();
    isOpen.value = false;
  }
}

function handleDocClick(e) {
  if (wrapperRef.value && !wrapperRef.value.contains(e.target)) {
    isOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", handleDocClick);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocClick);
});

defineExpose({
  inputRef,
  focus: () => inputRef.value?.focus(),
  blur: () => inputRef.value?.blur(),
});
</script>

<template>
  <div
    ref="wrapperRef"
    class="email-input-wrapper"
    :class="{ 'is-open': isOpen, 'is-disabled': disabled }"
  >
    <input
      ref="inputRef"
      :value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :autocomplete="autocomplete"
      :spellcheck="spellcheck"
      class="email-input-control"
      @input="handleInput"
      @focus="handleFocus"
      @blur="handleBlur"
      @keydown="handleKeydown"
    />

    <Transition name="email-dropdown-fade">
      <ul
        v-if="isOpen && filteredSuggestions.length > 0"
        class="email-suggestions-dropdown"
        role="listbox"
      >
        <li
          v-for="(item, idx) in filteredSuggestions"
          :key="item.suffix"
          :class="{ 'is-active': idx === activeIndex }"
          class="email-suggestion-item"
          role="option"
          :aria-selected="idx === activeIndex"
          @pointerdown.prevent
          @click="selectSuggestion(item)"
          @mouseenter="activeIndex = idx"
        >
          <span class="email-prefix">{{ item.prefix }}</span>
          <span class="email-suffix">@{{ item.suffix }}</span>
        </li>
      </ul>
    </Transition>
  </div>
</template>

<style scoped>
/* =====================================================================
 * HeadlessEmailInput · iOS 风格邮箱智能联想输入框
 * iOS 令牌来自 styles/tokens.css（--ios-*）
 * ===================================================================== */

.email-input-wrapper {
  position: relative;
  width: 100%;
}

.email-input-wrapper.is-open {
  position: relative;
  z-index: 50;
}

.email-input-control {
  box-sizing: border-box;
  width: 100%;
  height: 38px;
  padding: 0 12px;
  background: var(--ios-fill);
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text);
  font-family: inherit;
  font-size: var(--fs-sm);
  transition: background-color var(--dur-quick) ease, border-color var(--dur-quick) ease, box-shadow var(--dur-quick) ease;
}

.email-input-control:focus {
  outline: none;
  background: var(--ios-card-bg);
  border-color: var(--ios-blue);
  box-shadow: 0 0 0 3px var(--ios-blue-soft);
}

.email-input-control::placeholder {
  color: var(--ios-gray);
}

.email-input-control:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---------------- 联想建议下拉面板 ---------------- */
.email-suggestions-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  width: 100%;
  min-width: 100%;
  max-height: 220px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--ios-separator) transparent;
  box-sizing: border-box;
  margin: 0;
  padding: 6px;
  list-style: none;
  outline: none;
  z-index: var(--z-popover, 60);
  background: var(--bg-2, #ffffff);
  border: 1px solid var(--ios-card-border);
  border-radius: 14px;
  box-shadow: var(--ios-shadow-panel);
}

/* 细滚动条 */
.email-suggestions-dropdown::-webkit-scrollbar {
  width: 4px;
}
.email-suggestions-dropdown::-webkit-scrollbar-track {
  background: transparent;
}
.email-suggestions-dropdown::-webkit-scrollbar-thumb {
  background: var(--ios-separator);
  border-radius: 4px;
}

.email-suggestion-item {
  display: flex;
  align-items: center;
  min-height: 36px;
  padding: 6px 12px;
  border-radius: 8px;
  color: var(--text);
  font-size: var(--fs-sm);
  cursor: pointer;
  user-select: none;
  transition: background-color var(--dur-instant) ease;
}

.email-suggestion-item.is-active {
  background: var(--ios-fill);
}

.email-prefix {
  font-weight: 500;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.email-suffix {
  color: var(--ios-blue);
  font-weight: 500;
  margin-left: 1px;
}

/* ---------------- 下拉动画 ---------------- */
.email-dropdown-fade-enter-active,
.email-dropdown-fade-leave-active {
  transition: opacity var(--dur-quick) ease, transform var(--dur-quick) var(--ease-decelerate);
}

.email-dropdown-fade-enter-from,
.email-dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}

@media (max-width: 640px) {
  .email-input-control {
    height: 44px;
    font-size: 16px;
  }
  .email-suggestion-item {
    min-height: 40px;
    font-size: 15px;
  }
}
</style>
