<template>
  <div ref="rootRef" class="language-switcher">
    <button
      class="language-trigger"
      type="button"
      :title="t('locale.language')"
      :aria-label="t('locale.language')"
      aria-haspopup="listbox"
      :aria-expanded="open"
      @click="open = !open"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
        <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z" />
      </svg>
      <span class="language-code">{{ currentOption.code }}</span>
    </button>

    <Transition name="language-menu">
      <ul v-if="open" class="language-menu" role="listbox" :aria-label="t('locale.language')">
        <li v-for="option in options" :key="option.value" role="none">
          <button
            class="language-option"
            :class="{ active: locale === option.value }"
            type="button"
            role="option"
            :aria-selected="locale === option.value"
            @click="choose(option.value)"
          >
            <span>{{ t(option.labelKey) }}</span>
            <svg v-if="locale === option.value" viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
            </svg>
          </button>
        </li>
      </ul>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { locale, t, setLocale, type Locale } from '../../i18n'
import { useEscapeClose } from '../../composables/useEscapeClose'

const options: { value: Locale; code: string; labelKey: string }[] = [
  { value: 'tr', code: 'TR', labelKey: 'locale.turkish' },
  { value: 'en', code: 'EN', labelKey: 'locale.english' },
  { value: 'zh-CN', code: '中文', labelKey: 'locale.chinese' },
]

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const currentOption = computed(() => options.find((option) => option.value === locale.value) ?? options[0]!)

function choose(value: Locale) {
  setLocale(value)
  open.value = false
}

function handleDocumentClick(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    open.value = false
  }
}

useEscapeClose(() => open.value, () => { open.value = false })

onMounted(() => document.addEventListener('click', handleDocumentClick))
onUnmounted(() => document.removeEventListener('click', handleDocumentClick))
</script>

<style scoped>
.language-switcher {
  position: relative;
  flex-shrink: 0;
}

.language-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px 0 10px;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.language-trigger:hover,
.language-trigger[aria-expanded='true'] {
  background: var(--bg-active);
  color: var(--text-primary);
}

.language-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 200;
  min-width: 170px;
  padding: 8px;
  list-style: none;
  background: var(--bg-white);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  transform-origin: top right;
}

.language-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  text-align: left;
}

.language-option:hover {
  background: var(--bg-hover);
}

.language-option.active {
  color: var(--primary-color);
  font-weight: 500;
}

.language-menu-enter-active,
.language-menu-leave-active {
  transition: opacity var(--duration-fast) var(--ease-standard),
    transform var(--duration-base) var(--ease-emphasized);
}

.language-menu-enter-from,
.language-menu-leave-to {
  opacity: 0;
  transform: scale(0.94) translateY(-4px);
}
</style>
