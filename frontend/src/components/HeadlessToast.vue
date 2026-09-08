<script setup>
/**
 * HeadlessToast 通知组件：
 * 使用 Headless UI Transition 实现动画效果。
 * 支持 success/error 类型、自动关闭、手动关闭。
 */
import { Transition } from '@headlessui/vue';
import { ref, watch, onMounted } from 'vue';

const props = defineProps({
  show: {
    type: Boolean,
    default: false,
  },
  type: {
    type: String,
    default: 'info',
    validator: (v) => ['info', 'success', 'error'].includes(v),
  },
  message: {
    type: String,
    required: true,
  },
  duration: {
    type: Number,
    default: 3000,
  },
});

const emit = defineEmits(['close']);

let timer = null;

function startTimer() {
  if (props.duration > 0) {
    timer = setTimeout(() => {
      emit('close');
    }, props.duration);
  }
}

function stopTimer() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    startTimer();
  } else {
    stopTimer();
  }
});

onMounted(() => {
  if (props.show) {
    startTimer();
  }
});
</script>

<template>
  <Transition
    enter-active-class="toast-enter-active"
    enter-from-class="toast-enter-from"
    enter-to-class="toast-enter-to"
    leave-active-class="toast-leave-active"
    leave-from-class="toast-leave-from"
    leave-to-class="toast-leave-to"
  >
    <div
      v-if="show"
      class="headless-toast"
      :class="`toast-${type}`"
      role="alert"
      aria-live="polite"
    >
      <div class="toast-icon" aria-hidden="true">
        <svg v-if="type === 'success'" viewBox="0 0 24 24" fill="none">
          <path d="M5 12.5l4.2 4.2L19 2.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else-if="type === 'error'" viewBox="0 0 24 24" fill="none">
          <path d="M12 8v5M12 16h.01M10.3 3.2l-7.2 14.4A1.8 1.8 0 0 0 4.7 20h14.6a1.8 1.8 0 0 0 1.6-2.4L13.7 3.2a1.8 1.8 0 0 0-3.4 0z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.8" />
          <path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        </svg>
      </div>
      <span class="toast-message">{{ message }}</span>
      <button class="toast-close" @click="emit('close')" aria-label="关闭通知">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.headless-toast {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  max-width: 360px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-left: 4px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: var(--shadow-toast);
}

.toast-success {
  border-left-color: var(--green);
}

.toast-error {
  border-left-color: var(--red);
}

.toast-info {
  border-left-color: var(--blue);
}

.toast-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.toast-success .toast-icon {
  color: var(--green);
}

.toast-error .toast-icon {
  color: var(--red);
}

.toast-info .toast-icon {
  color: var(--blue);
}

.toast-message {
  flex: 1;
  font-size: var(--fs-sm);
  color: var(--text);
}

.toast-close {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s ease;
}

.toast-close:hover {
  color: var(--text);
}

.toast-close svg {
  width: 14px;
  height: 14px;
}

/* 动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-enter-to {
  opacity: 1;
  transform: translateX(0);
}

.toast-leave-from {
  opacity: 1;
  transform: translateX(0);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
