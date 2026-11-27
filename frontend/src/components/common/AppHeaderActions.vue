<template>
  <div class="header-actions">
    <LanguageSwitcher />

    <button
      v-if="canAdmin && current !== 'admin'"
      class="icon-btn"
      type="button"
      :title="$t('ui.userManagement')"
      :aria-label="$t('ui.userManagement')"
      @click="router.push('/admin')"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
        <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zM8 11c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5C15 14.17 10.33 13 8 13zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
      </svg>
    </button>

    <button
      v-if="canAdmin && current !== 'settings'"
      class="icon-btn"
      type="button"
      :title="$t('ui.settings')"
      :aria-label="$t('ui.settings')"
      @click="router.push('/settings')"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
        <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87a.49.49 0 0 0 .12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.01-1.58zM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2z" />
      </svg>
    </button>

    <div ref="menuRef" class="account">
      <button
        class="account-avatar"
        type="button"
        :title="displayUsername"
        :aria-label="displayUsername"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        @click="menuOpen = !menuOpen"
      >
        {{ initial }}
      </button>

      <Transition name="account-menu">
        <div v-if="menuOpen" class="account-menu" role="menu">
          <div class="account-summary">
            <span class="account-avatar account-avatar--lg" aria-hidden="true">{{ initial }}</span>
            <span class="account-name">{{ displayUsername }}</span>
          </div>
          <button class="account-item" type="button" role="menuitem" @click="logout">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M10.09 15.59 11.5 17l5-5-5-5-1.41 1.41L12.67 11H3v2h9.67l-2.58 2.59zM19 3h-8v2h8v14h-8v2h8c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z" />
            </svg>
            {{ $t('ui.logOut') }}
          </button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import LanguageSwitcher from './LanguageSwitcher.vue'
import { clearTokens, getDisplayUsername, isAdmin } from '../../services/auth'
import { logoutSession } from '../../services/api'
import { useEscapeClose } from '../../composables/useEscapeClose'
import { t } from '../../i18n'

defineProps<{
  /** Page the header is shown on; its own shortcut button is hidden. */
  current?: 'home' | 'project' | 'settings' | 'admin'
}>()

const router = useRouter()
const menuOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)

const canAdmin = computed(() => isAdmin())
const displayUsername = computed(() => getDisplayUsername() || t('ui.defaultUser'))
const initial = computed(() => displayUsername.value.trim().charAt(0).toUpperCase() || '?')

async function logout() {
  menuOpen.value = false
  await logoutSession()
  clearTokens()
  router.push('/login')
}

function handleDocumentClick(event: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(event.target as Node)) {
    menuOpen.value = false
  }
}

useEscapeClose(() => menuOpen.value, () => { menuOpen.value = false })

onMounted(() => document.addEventListener('click', handleDocumentClick))
onUnmounted(() => document.removeEventListener('click', handleDocumentClick))
</script>

<style scoped>
.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.account {
  position: relative;
  margin-left: 6px;
}

.account-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--primary-color);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 0 0 2px var(--bg-white);
}

button.account-avatar:hover {
  box-shadow: 0 0 0 2px var(--bg-white), 0 0 0 4px var(--bg-active);
}

.account-avatar--lg {
  width: 40px;
  height: 40px;
  font-size: 16px;
  box-shadow: none;
}

.account-menu {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 200;
  min-width: 220px;
  padding: 8px;
  background: var(--bg-white);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  transform-origin: top right;
}

.account-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px 12px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--border-light);
}

.account-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  text-align: left;
}

.account-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.account-menu-enter-active,
.account-menu-leave-active {
  transition: opacity var(--duration-fast) var(--ease-standard),
    transform var(--duration-base) var(--ease-emphasized);
}

.account-menu-enter-from,
.account-menu-leave-to {
  opacity: 0;
  transform: scale(0.94) translateY(-4px);
}
</style>
