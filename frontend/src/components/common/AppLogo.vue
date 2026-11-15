<template>
  <span class="app-logo" :class="`app-logo--${size}`">
    <svg class="app-logo-mark" viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="11" fill="var(--primary-color)" />
      <path
        d="M11 12.2c0-.9.9-1.5 1.7-1.2l6.2 2.3c.7.3 1.1.9 1.1 1.6v13.9c0 .9-.9 1.5-1.7 1.2l-6.2-2.3a1.7 1.7 0 0 1-1.1-1.6V12.2z"
        fill="#fff"
      />
      <path
        d="M29 12.2c0-.9-.9-1.5-1.7-1.2l-6.200 2.300c-.7.3-1.100.9-1.100 1.600v13.900c0 .9.9 1.5 1.7 1.200l6.200-2.300c.7-.3 1.100-.9 1.100-1.600V12.200z"
        fill="#fff"
        opacity="0.62"
      />
    </svg>
    <span v-if="showText" class="app-logo-text">Local Notebook</span>
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'sm' | 'md' | 'lg'
  showText?: boolean
}>(), {
  size: 'md',
  showText: true
})
</script>

<style scoped>
.app-logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  user-select: none;
}

.app-logo-mark {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.app-logo-text {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.01em;
  white-space: nowrap;
}

.app-logo--sm .app-logo-mark {
  width: 28px;
  height: 28px;
}

.app-logo--sm .app-logo-text {
  font-size: 17px;
}

.app-logo--lg .app-logo-mark {
  width: 48px;
  height: 48px;
}

.app-logo--lg .app-logo-text {
  font-size: 26px;
}
</style>
