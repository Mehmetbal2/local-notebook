<template>
  <div class="admin-page">
    <header class="admin-header">
      <div class="header-left">
        <button class="icon-text-btn" @click="router.push('/')">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
          </svg>
          {{ $t('ui.back') }}
        </button>
        <h1>{{ $t('ui.userManagement') }}</h1>
      </div>
      <AppHeaderActions current="admin" />
    </header>

    <main class="admin-main">
      <div class="toolbar">
        <div class="toolbar-summary">
          <span>{{ $t('ui.totalUsersCount', { count: total }) }}</span>
          <span>{{ $t('ui.adminUsersCount', { count: adminCount }) }}</span>
        </div>
        <button class="primary-btn" @click="openCreateModal">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M15 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm-9-2V7H4v3H1v2h3v3h2v-3h3v-2H6zm9 4c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
          </svg>
          {{ $t('ui.provisionUser') }}
        </button>
      </div>

      <div v-if="loading" class="state-row">{{ $t('ui.loading') }}</div>
      <div v-else-if="users.length === 0" class="state-row">{{ $t('ui.noUsers') }}</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ $t('ui.username') }}</th>
              <th>{{ $t('ui.role') }}</th>
              <th>{{ $t('ui.createdAt') }}</th>
              <th>{{ $t('ui.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.user_id">
              <td>
                <div class="username-cell">
                  <span>{{ user.username }}</span>
                  <small>{{ user.user_id }}</small>
                </div>
              </td>
              <td>
                <span class="role-badge" :class="user.role">{{ user.role === 'admin' ? $t('ui.admin') : $t('ui.regularUser') }}</span>
              </td>
              <td>{{ formatDateTime(user.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button class="icon-btn" :title="$t('ui.resetPassword')" @click="openResetModal(user)">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                      <path d="M12 17a2 2 0 0 0 2-2c0-.74-.4-1.38-1-1.72V11h2V9h-2V7h-2v2H9v2h2v2.28c-.6.34-1 .98-1 1.72a2 2 0 0 0 2 2zm6-8h-1V7A5 5 0 0 0 7 7v2H6c-1.1 0-2 .9-2 2v9c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-9c0-1.1-.9-2-2-2zM9 7a3 3 0 0 1 6 0v2H9V7z" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section class="stats-section">
        <div class="stats-header">
          <div>
            <h2>{{ $t('ui.userStats') }}</h2>
            <p>{{ $t('ui.userStatsHint') }}</p>
          </div>
          <div class="period-switch" role="group" :aria-label="$t('ui.userStats')">
            <button
              v-for="days in PERIODS"
              :key="days"
              :class="{ active: statsDays === days }"
              :aria-pressed="statsDays === days"
              @click="setStatsDays(days)"
            >
              {{ $t('ui.userStatsDays', { count: days }) }}
            </button>
          </div>
        </div>

        <div v-if="stats" class="stat-cards" :class="{ dim: statsLoading }">
          <div class="stat-card">
            <span>{{ $t('ui.userStatsProjects') }}</span>
            <strong>{{ formatNumber(stats.totals.projects) }}</strong>
            <small>{{ $t('ui.userStatsSourcesSub', { count: formatNumber(stats.totals.files) }) }}</small>
          </div>
          <div class="stat-card">
            <span>{{ $t('ui.userStatsStorage') }}</span>
            <strong>{{ formatBytes(stats.totals.storage_bytes) }}</strong>
            <small>{{ $t('ui.userStatsReadySub', { ready: formatNumber(stats.totals.ready_files), total: formatNumber(stats.totals.files) }) }}</small>
          </div>
          <div class="stat-card">
            <span>{{ $t('ui.userStatsMessages') }}</span>
            <strong>{{ formatNumber(stats.totals.messages) }}</strong>
            <small>{{ $t('ui.userStatsSessionsSub', { count: formatNumber(stats.totals.sessions) }) }}</small>
          </div>
          <div class="stat-card">
            <span>{{ $t('ui.userStatsLlmCard') }} · {{ $t('ui.userStatsDays', { count: stats.period_days }) }}</span>
            <strong>{{ formatNumber(stats.totals.tokens) }}</strong>
            <small>{{ $t('ui.userStatsCallsSub', { count: formatNumber(stats.totals.llm_calls), active: stats.totals.active_users }) }}</small>
          </div>
        </div>

        <div v-if="statsLoading && !stats" class="state-row">{{ $t('ui.loading') }}</div>
        <div v-else-if="stats" class="table-wrap stats-table" :class="{ dim: statsLoading }">
          <table>
            <thead>
              <tr>
                <th>{{ $t('ui.username') }}</th>
                <th class="num">{{ $t('ui.userStatsProjects') }}</th>
                <th class="num">{{ $t('ui.userStatsSources') }}</th>
                <th class="num">{{ $t('ui.userStatsStorage') }}</th>
                <th class="num">{{ $t('ui.userStatsMessages') }}</th>
                <th class="num">{{ $t('ui.userStatsOutputs') }}</th>
                <th class="num">{{ $t('ui.userStatsCalls') }}</th>
                <th>{{ $t('ui.userStatsShare') }}</th>
                <th>{{ $t('ui.userStatsLastActive') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in stats.rows" :key="row.user_id || 'unassigned'" :class="{ muted: !row.user_id }">
                <td>
                  <div class="stat-user">
                    <span class="avatar" :class="row.role">{{ initial(row) }}</span>
                    <span>{{ row.user_id ? row.username : $t('ui.userStatsUnassigned') }}</span>
                  </div>
                </td>
                <td class="num">{{ formatNumber(row.projects) }}</td>
                <td class="num">
                  {{ formatNumber(row.files) }}
                  <small v-if="row.files && row.ready_files !== row.files" class="sub">
                    {{ $t('ui.userStatsReadyOf', { ready: row.ready_files, total: row.files }) }}
                  </small>
                </td>
                <td class="num">{{ formatBytes(row.storage_bytes) }}</td>
                <td class="num">{{ formatNumber(row.messages) }}</td>
                <td class="num">{{ formatNumber(row.outputs) }}</td>
                <td class="num">{{ formatNumber(row.llm_calls) }}</td>
                <td>
                  <div class="share" :title="`${formatNumber(row.tokens)} ${$t('ui.userStatsTokens')}`">
                    <div class="share-bar"><span :style="{ width: `${tokenShare(row)}%` }" /></div>
                    <span class="share-value">{{ formatNumber(row.tokens) }}</span>
                  </div>
                </td>
                <td :title="row.last_active_at ? formatDateTime(row.last_active_at) : ''">
                  {{ row.last_active_at ? relativeTime(row.last_active_at) : $t('ui.userStatsNoActivity') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>

    <div v-if="showCreate" class="modal-overlay" @click.self="closeCreateModal">
      <form class="modal" @submit.prevent="submitCreate">
        <h2>{{ $t('ui.provisionUser') }}</h2>
        <label>
          {{ $t('ui.username') }}
          <input v-model="createForm.username" type="text" autocomplete="off" />
        </label>
        <label>
          {{ $t('ui.initialPassword') }}
          <input v-model="createForm.password" type="password" autocomplete="new-password" />
        </label>
        <p v-if="formError" class="form-error">{{ formError }}</p>
        <div class="modal-actions">
          <button type="button" class="plain-btn" @click="closeCreateModal">{{ $t('ui.cancel') }}</button>
          <button type="submit" class="primary-btn" :disabled="submitting">
            {{ submitting ? $t('ui.creating') : $t('ui.create') }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="resetTarget" class="modal-overlay" @click.self="closeResetModal">
      <form class="modal" @submit.prevent="submitReset">
        <h2>{{ $t('ui.resetPassword') }}</h2>
        <p class="modal-desc">{{ resetTarget.username }}</p>
        <label>
          {{ $t('ui.newPassword') }}
          <input v-model="resetPassword" type="password" autocomplete="new-password" />
        </label>
        <p v-if="formError" class="form-error">{{ formError }}</p>
        <div class="modal-actions">
          <button type="button" class="plain-btn" @click="closeResetModal">{{ $t('ui.cancel') }}</button>
          <button type="submit" class="primary-btn" :disabled="submitting">
            {{ submitting ? $t('ui.saving') : $t('ui.save') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createAdminUser,
  getAdminUsers,
  getAdminUserStats,
  resetAdminUserPassword,
  type AdminUser,
  type AdminUserStatsResponse,
  type AdminUserStatsRow,
} from '../services/api'
import AppHeaderActions from '../components/common/AppHeaderActions.vue'
import { locale, t } from '../i18n'
import { parseServerDate } from '../utils/format'

const router = useRouter()

const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(true)
const submitting = ref(false)
const showCreate = ref(false)
const resetTarget = ref<AdminUser | null>(null)
const resetPassword = ref('')
const formError = ref('')

const createForm = reactive({
  username: '',
  password: '',
})

const adminCount = computed(() => users.value.filter(user => user.role === 'admin').length)

function toast(message: string, type: 'success' | 'error' = 'success') {
  window.dispatchEvent(new CustomEvent('global-toast', { detail: { message, type } }))
}

function errorMessage(error: any): string {
  return error?.response?.data?.detail || error?.message || t('ui.operationFailed')
}

function formatDateTime(value: string): string {
  return parseServerDate(value).toLocaleString(locale.value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadUsers() {
  try {
    loading.value = true
    const response = await getAdminUsers()
    users.value = response.users
    total.value = response.total
  } catch (error) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  formError.value = ''
  createForm.username = ''
  createForm.password = ''
  showCreate.value = true
}

function closeCreateModal() {
  showCreate.value = false
}

async function submitCreate() {
  const username = createForm.username.trim()
  if (username.length < 2) {
    formError.value = t('ui.usernameMinLength')
    return
  }
  if (createForm.password.length < 6) {
    formError.value = t('ui.passwordMinLength')
    return
  }

  try {
    submitting.value = true
    const created = await createAdminUser({
      username,
      password: createForm.password,
    })
    users.value = [created, ...users.value]
    total.value += 1
    showCreate.value = false
    toast(t('ui.userProvisioned'))
  } catch (error) {
    formError.value = errorMessage(error)
  } finally {
    submitting.value = false
  }
}

function openResetModal(user: AdminUser) {
  resetTarget.value = user
  resetPassword.value = ''
  formError.value = ''
}

function closeResetModal() {
  resetTarget.value = null
}

async function submitReset() {
  if (!resetTarget.value) return
  if (resetPassword.value.length < 6) {
    formError.value = t('ui.passwordMinLength')
    return
  }

  try {
    submitting.value = true
    await resetAdminUserPassword(resetTarget.value.user_id, resetPassword.value)
    closeResetModal()
    toast(t('ui.passwordReset'))
  } catch (error) {
    formError.value = errorMessage(error)
  } finally {
    submitting.value = false
  }
}

const PERIODS = [7, 30, 90] as const
const stats = ref<AdminUserStatsResponse | null>(null)
const statsLoading = ref(false)
const statsDays = ref<number>(30)

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getAdminUserStats(statsDays.value)
  } catch (error) {
    toast(errorMessage(error), 'error')
  } finally {
    statsLoading.value = false
  }
}

function setStatsDays(days: number) {
  if (statsDays.value === days) return
  statsDays.value = days
  void loadStats()
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat(locale.value).format(value || 0)
}

function formatBytes(value: number): string {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 || size >= 10 ? 0 : 1)} ${units[unit]}`
}

function relativeTime(value: string): string {
  const seconds = Math.round((parseServerDate(value).getTime() - Date.now()) / 1000)
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000], ['month', 2592000], ['week', 604800],
    ['day', 86400], ['hour', 3600], ['minute', 60],
  ]
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit)
  }
  return rtf.format(0, 'minute')
}

function tokenShare(row: AdminUserStatsRow): number {
  const total = stats.value?.totals.tokens || 0
  return total ? Math.max(row.tokens ? 2 : 0, Math.round((row.tokens / total) * 100)) : 0
}

function initial(row: AdminUserStatsRow): string {
  return row.user_id ? (row.username.trim()[0] || '?').toLocaleUpperCase(locale.value) : '–'
}

onMounted(() => {
  void loadUsers()
  void loadStats()
})
</script>

<style scoped>
.admin-page {
  height: 100vh;
  overflow-y: auto;
  background: var(--bg-main);
  color: var(--text-primary);
}

.admin-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 24px;
  background: var(--bg-main);
  position: sticky;
  top: 0;
  z-index: 20;
}

.header-left,
.header-right,
.toolbar,
.toolbar-summary,
.row-actions,
.admin-badge,
.icon-text-btn,
.primary-btn {
  display: flex;
  align-items: center;
}

.header-left,
.header-right,
.toolbar-summary,
.row-actions {
  gap: 12px;
}

h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
}

.admin-main {
  max-width: 1160px;
  margin: 0 auto;
  padding: 24px;
}

.toolbar {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.toolbar-summary {
  flex-wrap: wrap;
  color: var(--text-tertiary);
  font-size: 13px;
}

.toolbar-summary span {
  padding: 4px 10px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 999px;
}

.icon-text-btn,
.primary-btn,
.plain-btn,
.icon-btn {
  border: 1px solid var(--border-strong);
  background: #fff;
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.icon-text-btn,
.primary-btn {
  gap: 7px;
  height: 36px;
  padding: 0 12px;
}

.primary-btn {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: #fff;
}

.plain-btn {
  height: 36px;
  padding: 0 14px;
}

.icon-btn {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.icon-text-btn:hover,
.plain-btn:hover,
.icon-btn:hover {
  background: var(--bg-hover);
}

.primary-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

button:disabled,
select:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.admin-badge {
  gap: 6px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.state-row {
  padding: 48px 0;
  text-align: center;
  color: var(--text-tertiary);
}

.table-wrap {
  overflow-x: auto;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}

th,
td {
  padding: 13px 16px;
  border-bottom: 1px solid #eef0f3;
  text-align: left;
  font-size: 14px;
  vertical-align: middle;
}

th {
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 650;
  background: #fafafa;
}

tr:last-child td {
  border-bottom: 0;
}

.username-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.username-cell small {
  color: var(--text-disabled);
  font-size: 11px;
}

.modal input,
.role-badge {
  height: 36px;
}

.modal input {
  height: 36px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
  padding: 0 10px;
  font-size: 14px;
}

.role-badge {
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 13px;
  background: #eef2ff;
  color: #3730a3;
}

.role-badge.user {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.modal-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.36);
  z-index: 20;
}

.modal {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: var(--radius-xl);
  padding: 22px;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.24);
}

.modal h2 {
  margin: 0 0 18px;
  font-size: 18px;
}

.modal label {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-bottom: 14px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.modal input {
  width: 100%;
}

.modal-desc {
  margin: -8px 0 16px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.form-error {
  margin: 0 0 14px;
  padding: 10px 12px;
  background: var(--error-soft);
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #b91c1c;
  font-size: 13px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

.stats-section {
  margin-top: 32px;
}

.stats-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.stats-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
}

.stats-header p {
  margin: 5px 0 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.period-switch {
  display: inline-flex;
  padding: 3px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.period-switch button {
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.period-switch button.active {
  background: var(--primary-soft);
  color: var(--on-primary-soft);
  font-weight: 600;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 10px;
}

.stat-card span {
  color: var(--text-tertiary);
  font-size: 12px;
}

.stat-card strong {
  font-size: 22px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.stat-card small {
  color: var(--text-secondary);
  font-size: 12px;
}

.dim {
  opacity: 0.6;
  transition: opacity 0.15s;
}

.stats-table table {
  min-width: 980px;
}

.stats-table td,
.stats-table th {
  white-space: nowrap;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.sub {
  display: block;
  color: var(--text-tertiary);
  font-size: 11px;
}

.stat-user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 650;
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.avatar.admin {
  background: #eef2ff;
  color: #3730a3;
}

tr.muted td {
  color: var(--text-tertiary);
}

.share {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 150px;
}

.share-bar {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: #eef0f3;
  overflow: hidden;
}

.share-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--primary-color);
}

.share-value {
  min-width: 64px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 13px;
}

@media (max-width: 900px) {
  .stat-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .admin-header {
    padding: 0 14px;
  }

  .admin-main {
    padding: 16px;
  }

  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .primary-btn {
    justify-content: center;
  }
}
</style>
