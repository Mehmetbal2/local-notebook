<template>
  <router-view />
  
  <Teleport to="body">
    <Transition name="toast-fade">
      <div v-if="globalToast.visible" class="global-toast" :class="globalToast.type" role="status" aria-live="polite">
        {{ globalToast.message }}
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const globalToast = ref({
  visible: false,
  message: '',
  type: 'warning' as 'success' | 'error' | 'warning' | 'info'
})

let toastTimer: number | null = null

function showToast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'warning') {
  if (toastTimer) {
    clearTimeout(toastTimer)
  }

  globalToast.value = {
    visible: true,
    message,
    type
  }

  toastTimer = window.setTimeout(() => {
    globalToast.value.visible = false
  }, 3000)
}

function handleGlobalToast(event: Event) {
  const customEvent = event as CustomEvent<{ message: string; type: 'success' | 'error' | 'warning' | 'info' }>
  showToast(customEvent.detail.message, customEvent.detail.type)
}

onMounted(() => {
  window.addEventListener('global-toast', handleGlobalToast)
})

onUnmounted(() => {
  window.removeEventListener('global-toast', handleGlobalToast)
  if (toastTimer) {
    clearTimeout(toastTimer)
  }
})
</script>

<style>
.global-toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: min(520px, calc(100vw - 32px));
  padding: 12px 20px 12px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-inverse);
  color: var(--text-on-inverse);
  font-size: 14px;
  line-height: 1.4;
  z-index: 10000;
  box-shadow: var(--shadow-lg);
  pointer-events: none;
}

.global-toast::before {
  content: '';
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #8ab4f8;
}

.global-toast.warning::before {
  background: #fdd663;
}

.global-toast.error::before {
  background: #f28b82;
}

.global-toast.success::before {
  background: #81c995;
}

.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity var(--duration-base) var(--ease-standard),
    transform var(--duration-slow) var(--ease-emphasized);
}

.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-16px);
}
</style>
