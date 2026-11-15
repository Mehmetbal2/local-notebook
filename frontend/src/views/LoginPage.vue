<template>
  <div class="login-page">
    <div class="login-language">
      <LanguageSwitcher />
    </div>

    <div class="login-shell">
      <section class="login-intro" aria-hidden="true">
        <AppLogo size="lg" />
        <p class="login-tagline">{{ $t('ui.loginTagline') }}</p>
      </section>

      <main class="login-card">
        <div class="login-card-logo">
          <AppLogo :show-text="false" size="lg" />
        </div>
        <h1>{{ $t('ui.documentQaSystem') }}</h1>
        <p class="subtitle">{{ $t('ui.logInToContinue') }}</p>

        <form class="login-form" novalidate @submit.prevent="handleLogin">
          <div class="form-group">
            <label for="username">{{ $t('ui.username') }}</label>
            <input
              id="username"
              v-model="username"
              type="text"
              :placeholder="$t('ui.enterUsername')"
              :disabled="loading"
              :aria-invalid="Boolean(error)"
              autocomplete="username"
              autocapitalize="none"
              spellcheck="false"
              autofocus
            />
          </div>

          <div class="form-group">
            <label for="password">{{ $t('ui.password') }}</label>
            <div class="password-field">
              <input
                id="password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                :placeholder="$t('ui.enterPassword')"
                :disabled="loading"
                :aria-invalid="Boolean(error)"
                autocomplete="current-password"
              />
              <button
                class="password-toggle"
                type="button"
                :title="showPassword ? $t('ui.hidePassword') : $t('ui.showPassword')"
                :aria-label="showPassword ? $t('ui.hidePassword') : $t('ui.showPassword')"
                :aria-pressed="showPassword"
                @click="showPassword = !showPassword"
              >
                <svg v-if="showPassword" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
                  <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.804 11.804 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z" />
                </svg>
                <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
                  <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z" />
                </svg>
              </button>
            </div>
          </div>

          <div v-if="error" class="error-message" role="alert">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
            <span>{{ error }}</span>
          </div>

          <button type="submit" class="btn btn-filled login-btn" :disabled="loading || !username || !password">
            <span v-if="loading" class="spinner" aria-hidden="true"></span>
            {{ loading ? $t('ui.loggingIn') : $t('ui.logIn') }}
          </button>
        </form>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login, getCurrentUser } from '../services/api'
import { setTokens, setUser } from '../services/auth'
import { t } from '../i18n'
import AppLogo from '../components/common/AppLogo.vue'
import LanguageSwitcher from '../components/common/LanguageSwitcher.vue'

const router = useRouter()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const showPassword = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) return

  loading.value = true
  error.value = ''

  try {
    const response = await login(username.value, password.value)

    if (response.success) {
      setTokens(response.access_token, response.refresh_token)

      try {
        const userInfo = await getCurrentUser()
        if (userInfo.success && userInfo.user) {
          setUser({
            user_id: userInfo.user.user_id,
            username: userInfo.user.username,
            phone: userInfo.user.phone,
            role: userInfo.user.role || 'user',
            created_at: userInfo.user.created_at
          })
        }
      } catch {
        setUser({
          user_id: response.user_id,
          username: response.username,
          role: response.role || 'user',
          created_at: new Date().toISOString()
        })
      }

      router.push('/')
    } else {
      error.value = response.error || t('ui.loginFailed')
    }
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.response?.data?.error || t('ui.loginFailedCheckYourNetworkConnection')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  height: 100vh;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(900px 520px at 12% 8%, rgba(66, 133, 244, 0.16), transparent 62%),
    radial-gradient(760px 480px at 92% 96%, rgba(26, 163, 163, 0.14), transparent 60%),
    var(--bg-main);
}

.login-language {
  position: absolute;
  top: 16px;
  right: 20px;
}

.login-shell {
  display: flex;
  align-items: center;
  gap: 72px;
  width: 100%;
  max-width: 940px;
}

.login-intro {
  flex: 1;
  min-width: 0;
}

.login-tagline {
  margin-top: 28px;
  max-width: 420px;
  font-family: var(--font-display);
  font-size: clamp(26px, 3vw, 36px);
  font-weight: 500;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.login-card {
  width: 100%;
  max-width: 420px;
  flex-shrink: 0;
  padding: 40px;
  background: var(--bg-white);
  border-radius: 28px;
  box-shadow: var(--shadow-lg);
  animation: card-in var(--duration-slow) var(--ease-emphasized);
}

@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
}

.login-card-logo {
  display: none;
  margin-bottom: 20px;
}

.login-card h1 {
  font-size: 24px;
  font-weight: 500;
  line-height: 1.25;
}

.subtitle {
  margin-top: 6px;
  margin-bottom: 28px;
  color: var(--text-secondary);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-group input {
  width: 100%;
  height: 48px;
  padding: 0 16px;
  font-size: 15px;
  border-color: var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--bg-white);
}

.form-group input[aria-invalid='true'] {
  border-color: var(--error-color);
}

.form-group input:disabled {
  background: var(--bg-secondary);
  cursor: not-allowed;
}

.password-field {
  position: relative;
}

.password-field input {
  padding-right: 52px;
}

.password-toggle {
  position: absolute;
  top: 6px;
  right: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: transparent;
  color: var(--text-tertiary);
}

.password-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.error-message {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: var(--error-soft);
  border-radius: var(--radius-md);
  color: var(--error-color);
  font-size: 13px;
  line-height: 1.4;
}

.error-message svg {
  flex-shrink: 0;
}

.login-btn {
  height: 48px;
  margin-top: 6px;
  font-size: 15px;
}

.login-btn:disabled {
  background: var(--bg-tertiary);
  color: var(--text-disabled);
  opacity: 1;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 860px) {
  .login-intro {
    display: none;
  }

  .login-shell {
    justify-content: center;
  }

  .login-card-logo {
    display: block;
  }

  .login-card {
    padding: 32px 24px;
  }
}
</style>
