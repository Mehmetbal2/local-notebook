<template>
  <div class="system-status">
    <!-- Model usage -->
    <section class="status-block">
      <div class="block-header">
        <div>
          <h3>{{ $t('ui.modelUsage') }}</h3>
          <p>{{ $t('ui.usageGroupedByDateUserModel') }}</p>
        </div>
        <div class="usage-filters">
          <input v-model="usageFilters.start_date" type="date" />
          <input v-model="usageFilters.end_date" type="date" />
          <select v-model="usageFilters.user_id">
            <option value="">{{ $t('ui.allUsers') }}</option>
            <option v-for="user in users" :key="user.user_id" :value="user.user_id">
              {{ user.username }}
            </option>
          </select>
          <button class="plain-btn" :disabled="usageLoading" @click="loadUsage">{{ $t('ui.refresh') }}</button>
        </div>
      </div>

      <div class="chips">
        <span>{{ $t('ui.usageCallsCount', { count: formatNumber(usageTotals.call_count) }) }}</span>
        <span>{{ $t('ui.usageTotalTokensCount', { count: formatNumber(usageTotals.total_tokens) }) }}</span>
        <span>{{ $t('ui.usageInputCount', { count: formatNumber(usageTotals.input_uncached_tokens) }) }}</span>
        <span>{{ $t('ui.usageCacheReadCount', { count: formatNumber(usageTotals.input_cache_read_tokens) }) }}</span>
        <span>{{ $t('ui.usageCacheWriteCount', { count: formatNumber(usageTotals.input_cache_write_tokens) }) }}</span>
        <span>{{ $t('ui.usageOutputCount', { count: formatNumber(usageTotals.output_tokens) }) }}</span>
      </div>

      <div v-if="usageLoading" class="state-row">{{ $t('ui.loadingUsage') }}</div>
      <div v-else-if="usageRows.length === 0" class="state-row">{{ $t('ui.noUsageRecords') }}</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ $t('ui.date') }}</th>
              <th>{{ $t('ui.defaultUser') }}</th>
              <th>{{ $t('ui.model') }}</th>
              <th class="num">{{ $t('ui.count') }}</th>
              <th class="num">{{ $t('ui.uncachedInput') }}</th>
              <th class="num">{{ $t('ui.cacheRead') }}</th>
              <th class="num">{{ $t('ui.cacheWrite') }}</th>
              <th class="num">{{ $t('ui.outputTokens') }}</th>
              <th class="num">{{ $t('ui.total') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in usageRows" :key="`${row.usage_date}-${row.user_id}-${row.model}`">
              <td>{{ row.usage_date }}</td>
              <td>{{ row.username }}</td>
              <td><span class="model-name" :title="row.model">{{ row.model }}</span></td>
              <td class="num">{{ formatNumber(row.call_count) }}</td>
              <td class="num">{{ formatNumber(row.input_uncached_tokens) }}</td>
              <td class="num">{{ formatNumber(row.input_cache_read_tokens) }}</td>
              <td class="num">{{ formatNumber(row.input_cache_write_tokens) }}</td>
              <td class="num">{{ formatNumber(row.output_tokens) }}</td>
              <td class="num strong">{{ formatNumber(row.total_tokens) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Backup and restore -->
    <section class="status-block">
      <div class="block-header">
        <div>
          <h3>{{ $t('ui.backupSection') }}</h3>
          <p>{{ $t('ui.backupSectionHint') }}</p>
        </div>
      </div>
      <div class="tools-row">
        <label class="check-row">
          <input v-model="includeUploads" type="checkbox" />
          {{ $t('ui.includeSourceFiles') }}
        </label>
        <label class="check-row">
          <input v-model="includeVectors" type="checkbox" />
          {{ $t('ui.includeVectors') }}
        </label>
        <button class="primary-btn" :disabled="backupBusy" @click="downloadBackup">
          {{ backupBusy ? $t('ui.preparingBackup') : $t('ui.downloadBackup') }}
        </button>
      </div>
      <div class="tools-row">
        <label class="plain-btn file-btn">
          <input type="file" accept=".zip,application/zip" @change="onRestoreFile" />
          <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z" />
          </svg>
          {{ $t('ui.chooseBackupFile') }}
        </label>
        <span class="file-name" :class="{ empty: !restoreFile }">
          {{ restoreFile ? `${restoreFile.name} · ${formatBytes(restoreFile.size)}` : $t('ui.noBackupFileSelected') }}
        </span>
        <button class="plain-btn" :disabled="!restoreFile || restoreBusy" @click="uploadRestore">
          {{ restoreBusy ? $t('ui.restoringBackup') : $t('ui.restoreBackup') }}
        </button>
      </div>
      <p v-if="backupMessage" class="hint">{{ backupMessage }}</p>
      <p v-if="restoreMessage" class="hint">{{ restoreMessage }}</p>
    </section>

    <!-- Diagnostics -->
    <section class="status-block">
      <div class="block-header">
        <div>
          <h3>{{ $t('ui.diagnosticsSection') }}</h3>
          <p>{{ $t('ui.diagnosticsSectionHint') }}</p>
        </div>
        <button class="plain-btn" :disabled="diagnosticsLoading" @click="loadDiagnostics">{{ $t('ui.refresh') }}</button>
      </div>
      <div v-if="diagnosticsLoading && !diagnostics" class="state-row">{{ $t('ui.loading') }}</div>
      <template v-else-if="diagnostics">
        <div class="diag-grid">
          <div class="diag-item">
            <span>{{ $t('ui.appVersion') }}</span>
            <strong>{{ diagnostics.app.version }} · Python {{ diagnostics.app.python }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.uptime') }}</span>
            <strong>{{ formatUptime(diagnostics.app.uptime_seconds) }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.database') }}</span>
            <strong>{{ formatBytes(diagnostics.database.size_bytes) }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.projectsFilesSegments') }}</span>
            <strong>
              {{ formatNumber(diagnostics.database.counts.projects) }} /
              {{ formatNumber(diagnostics.database.counts.files) }} /
              {{ formatNumber(diagnostics.database.counts.segments) }}
            </strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.vectorStore') }}</span>
            <strong>{{ diagnostics.vectors.mode || '—' }} · {{ formatNumber(vectorRows) }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.storageData') }}</span>
            <strong>{{ formatBytes(diagnostics.storage.data_bytes) }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.storageUploads') }}</span>
            <strong>{{ formatBytes(diagnostics.storage.uploads_bytes) }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.diskFree') }}</span>
            <strong :class="{ bad: diskLow }">{{ formatBytes(diagnostics.storage.disk_free_bytes) }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.searxng') }}</span>
            <strong :class="diagnostics.services.searxng.reachable ? 'ok' : 'bad'">
              {{ diagnostics.services.searxng.reachable ? $t('ui.available') : $t('ui.unavailable') }}
            </strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.embedding') }}</span>
            <strong :class="embeddingClass" :title="diagnostics.services.embedding.error || ''">{{ embeddingLabel }}</strong>
          </div>
          <div class="diag-item">
            <span>{{ $t('ui.llm') }}</span>
            <strong>
              {{ diagnostics.services.llm.configured ? diagnostics.services.llm.model : $t('ui.notConfigured') }}
            </strong>
          </div>
        </div>
        <div class="diag-logs">
          <h4>{{ $t('ui.recentErrors') }}</h4>
          <p v-if="!diagnostics.logs.recent.length" class="muted">{{ $t('ui.noRecentErrors') }}</p>
          <pre v-else>{{ diagnostics.logs.recent.join('\n') }}</pre>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getAdminDiagnostics,
  getAdminUsage,
  getAdminUsers,
  prepareAdminBackup,
  stageAdminRestore,
  type AdminDiagnostics,
  type AdminUsageRow,
  type AdminUsageTotals,
  type AdminUser,
} from '../../services/api'
import { locale, t } from '../../i18n'

const LOW_DISK_BYTES = 10 * 1024 ** 3

const users = ref<AdminUser[]>([])
const usageLoading = ref(true)
const usageRows = ref<AdminUsageRow[]>([])
const usageTotals = reactive<AdminUsageTotals>({
  call_count: 0,
  input_uncached_tokens: 0,
  input_cache_read_tokens: 0,
  input_cache_write_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
})
const usageFilters = reactive({
  start_date: toDateInputValue(addDays(new Date(), -29)),
  end_date: toDateInputValue(new Date()),
  user_id: '',
})

const includeUploads = ref(false)
const includeVectors = ref(true)
const backupBusy = ref(false)
const restoreBusy = ref(false)
const restoreFile = ref<File | null>(null)
const backupMessage = ref('')
const restoreMessage = ref('')

const diagnostics = ref<AdminDiagnostics | null>(null)
const diagnosticsLoading = ref(false)

function toast(message: string, type: 'success' | 'error' = 'success') {
  window.dispatchEvent(new CustomEvent('global-toast', { detail: { message, type } }))
}

function errorMessage(error: any): string {
  return error?.response?.data?.detail || error?.message || t('ui.operationFailed')
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function toDateInputValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function formatNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat(locale.value).format(value || 0)
}

function formatBytes(value: number | null | undefined): string {
  if (value == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 || size >= 10 ? 0 : 1)} ${units[unit]}`
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  if (minutes) return `${minutes}m`
  return `${seconds}s`
}

const vectorRows = computed(() => {
  const collections = diagnostics.value?.vectors.collections || {}
  return Object.values(collections).reduce((sum, item) => sum + (item.rows || 0), 0)
})

const diskLow = computed(() => {
  const free = diagnostics.value?.storage.disk_free_bytes
  return free != null && free < LOW_DISK_BYTES
})

const embeddingLabel = computed(() => {
  const emb = diagnostics.value?.services.embedding
  if (!emb) return '—'
  if (emb.source !== 'local') {
    const label = emb.source === 'custom' ? t('ui.custom') : emb.source
    return emb.model ? `${label} · ${emb.model}` : label
  }
  const local = t('ui.localService')
  if (!emb.local_running) return `${local} · ${t('ui.embeddingNotResponding')}`
  const details = [emb.model, emb.dim ? `${emb.dim}d` : ''].filter(Boolean).join(', ')
  return details ? `${local} · ${t('ui.running')} (${details})` : `${local} · ${t('ui.running')}`
})

const embeddingClass = computed(() => {
  const emb = diagnostics.value?.services.embedding
  if (!emb || emb.source !== 'local') return ''
  return emb.local_running ? 'ok' : 'bad'
})

async function loadUsers() {
  try {
    const response = await getAdminUsers()
    users.value = response.users
  } catch {
    // The user filter is optional; the usage table still loads for everyone.
    users.value = []
  }
}

async function loadUsage() {
  try {
    usageLoading.value = true
    const response = await getAdminUsage({
      start_date: usageFilters.start_date || undefined,
      end_date: usageFilters.end_date || undefined,
      user_id: usageFilters.user_id || undefined,
    })
    usageRows.value = response.rows
    Object.assign(usageTotals, response.totals)
  } catch (error) {
    toast(errorMessage(error), 'error')
  } finally {
    usageLoading.value = false
  }
}

async function downloadBackup() {
  if (backupBusy.value) return
  backupBusy.value = true
  backupMessage.value = ''
  try {
    const prepared = await prepareAdminBackup(includeUploads.value, includeVectors.value)
    // A plain link: the browser streams the archive to disk with its own download manager.
    const link = document.createElement('a')
    link.href = prepared.download_url
    link.download = prepared.filename
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
    backupMessage.value = t('ui.backupDownloadStarted', { size: formatBytes(prepared.size_bytes) })
  } catch (error) {
    backupMessage.value = errorMessage(error)
  } finally {
    backupBusy.value = false
  }
}

function onRestoreFile(event: Event) {
  const input = event.target as HTMLInputElement
  restoreFile.value = input.files?.[0] || null
  restoreMessage.value = ''
}

async function uploadRestore() {
  if (!restoreFile.value || restoreBusy.value) return
  restoreBusy.value = true
  restoreMessage.value = ''
  try {
    const result = await stageAdminRestore(restoreFile.value)
    const manifest = result.manifest || {}
    restoreMessage.value =
      manifest.vectors_included === false
        ? `${t('ui.restoreStaged')} ${t('ui.restoreVectorsMissing')}`
        : t('ui.restoreStaged')
  } catch (error) {
    restoreMessage.value = errorMessage(error)
  } finally {
    restoreBusy.value = false
  }
}

async function loadDiagnostics() {
  diagnosticsLoading.value = true
  try {
    diagnostics.value = await getAdminDiagnostics()
  } catch (error) {
    toast(errorMessage(error), 'error')
  } finally {
    diagnosticsLoading.value = false
  }
}

onMounted(() => {
  void loadUsers()
  void loadUsage()
  void loadDiagnostics()
})
</script>

<style scoped>
.system-status {
  display: flex;
  flex-direction: column;
  gap: 36px;
}

.status-block + .status-block {
  padding-top: 32px;
  border-top: 1px solid var(--border-color);
}

.block-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.block-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.block-header p {
  margin: 4px 0 0;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.5;
}

.usage-filters,
.tools-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tools-row {
  gap: 14px;
  margin: 12px 0;
}

.usage-filters input,
.usage-filters select {
  height: 34px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: #fff;
  color: var(--text-secondary);
  padding: 0 9px;
  font-size: 13px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.chips span {
  padding: 5px 10px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.plain-btn,
.primary-btn {
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: #fff;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  white-space: nowrap;
}

.plain-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}

.primary-btn {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: #fff;
}

.primary-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.state-row {
  padding: 36px 0;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 14px;
}

.table-wrap {
  overflow-x: auto;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
}

th,
td {
  padding: 11px 14px;
  border-bottom: 1px solid #eef0f3;
  text-align: left;
  font-size: 13px;
  white-space: nowrap;
}

th {
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
  background: #fafafa;
}

tr:last-child td {
  border-bottom: 0;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.strong {
  font-weight: 600;
}

.model-name {
  display: inline-block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.file-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  line-height: 32px;
}

.file-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.file-btn:focus-within {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.file-name {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-name.empty {
  color: var(--text-tertiary);
}

.check-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.hint {
  color: var(--text-secondary);
  font-size: 13px;
  margin: 6px 0;
}

.diag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.diag-item {
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.diag-item span {
  color: var(--text-tertiary);
  font-size: 12px;
}

.diag-item strong {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.diag-item .ok {
  color: #2e7d32;
}

.diag-item .bad {
  color: #c62828;
}

.diag-logs {
  margin-top: 18px;
}

.diag-logs h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.diag-logs pre {
  margin: 0;
  background: var(--bg-hover);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.55;
  overflow: auto;
  max-height: 260px;
  white-space: pre-wrap;
}

.muted {
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
