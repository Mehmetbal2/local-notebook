<template>
  <Teleport to="body">
    <div v-if="visible" class="naming-overlay modal-overlay" @click.self="emit('close')">
      <section class="naming-dialog" role="dialog" aria-modal="true" :aria-label="$t('ui.sourceNamingTitle')">
        <header class="naming-header">
          <div>
            <h3>{{ $t('ui.sourceNamingTitle') }}</h3>
            <p>{{ $t('ui.sourceNamingIntro') }}</p>
          </div>
          <button class="icon-btn" type="button" :title="$t('ui.close')" :aria-label="$t('ui.close')" @click="emit('close')">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" />
            </svg>
          </button>
        </header>

        <ol class="naming-list">
          <li v-for="row in rows" :key="row.id" class="naming-row" :class="{ excluded: !row.include }">
            <label class="naming-include">
              <input v-model="row.include" type="checkbox" :disabled="row.loading || !!row.error" />
              <span class="naming-current" dir="auto" :title="row.currentName">{{ row.currentName }}</span>
            </label>

            <div v-if="row.loading" class="naming-loading">
              <span class="naming-spinner" aria-hidden="true"></span>
              {{ $t('ui.sourceNamingLoading') }}
            </div>
            <p v-else-if="row.error" class="naming-error">{{ row.error }}</p>
            <template v-else>
              <div class="naming-fields">
                <label>
                  <span>{{ $t('ui.sourceNamingAuthor') }}</span>
                  <input v-model="row.author" type="text" dir="auto" maxlength="120" />
                </label>
                <label class="naming-year">
                  <span>{{ $t('ui.sourceNamingYear') }}</span>
                  <input v-model="row.year" type="text" dir="auto" maxlength="20" :placeholder="$t('ui.sourceNamingNoDate')" />
                </label>
                <label class="naming-title">
                  <span>{{ $t('ui.sourceNamingWorkTitle') }}</span>
                  <input v-model="row.title" type="text" dir="auto" maxlength="200" />
                </label>
              </div>
              <div class="naming-preview">
                <span class="naming-arrow" aria-hidden="true">→</span>
                <strong dir="auto">{{ composeName(row) || '—' }}</strong>
                <span class="naming-confidence" :class="row.confidence">{{ confidenceLabel(row.confidence) }}</span>
              </div>
              <p v-if="row.note" class="naming-note" dir="auto">{{ row.note }}</p>
            </template>
          </li>
        </ol>

        <footer class="naming-actions">
          <span class="naming-hint">{{ $t('ui.sourceNamingHint') }}</span>
          <button class="btn btn-text" type="button" @click="emit('close')">{{ $t('ui.cancel') }}</button>
          <button class="btn btn-filled" type="button" :disabled="saving || readyRows.length === 0" @click="confirm">
            {{ saving ? $t('ui.saving') : $t('ui.sourceNamingConfirm', { count: readyRows.length }) }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FileInfo } from '@/types'
import { suggestFileName } from '@/services/api'
import { getModelOutputLanguage, t } from '@/i18n'
import { useEscapeClose } from '@/composables/useEscapeClose'

interface Row {
  id: string
  currentName: string
  extension: string
  loading: boolean
  error: string
  include: boolean
  author: string
  year: string
  title: string
  confidence: 'high' | 'medium' | 'low'
  note: string
}

const props = defineProps<{
  visible: boolean
  files: FileInfo[]
  saving?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', renames: { id: string; fileName: string }[]): void
}>()

const rows = ref<Row[]>([])
let requestId = 0

function splitExtension(name: string): { base: string; extension: string } {
  const match = /^(.*?)(\.[A-Za-z0-9]{1,6})$/.exec(name)
  return match ? { base: match[1]!, extension: match[2]! } : { base: name, extension: '' }
}

function composeName(row: Row): string {
  const author = row.author.trim()
  const title = row.title.trim()
  if (!author || !title) return ''
  const year = row.year.trim() || t('ui.sourceNamingNoDate')
  return `${author} - ${year} - ${title}${row.extension}`
}

function confidenceLabel(confidence: Row['confidence']): string {
  if (confidence === 'high') return t('ui.sourceNamingConfidenceHigh')
  if (confidence === 'medium') return t('ui.sourceNamingConfidenceMedium')
  return t('ui.sourceNamingConfidenceLow')
}

const readyRows = computed(() => rows.value.filter((row) => row.include && !row.loading && !row.error && composeName(row)))

async function loadSuggestions(files: FileInfo[]) {
  const current = ++requestId
  rows.value = files.map((file) => ({
    id: file.id,
    currentName: file.file_name,
    extension: splitExtension(file.file_name).extension,
    loading: true,
    error: '',
    include: true,
    author: '',
    year: '',
    title: '',
    confidence: 'low',
    note: '',
  }))
  // A few at a time so a long list does not flood the model.
  const queue = [...rows.value]
  const workers = Array.from({ length: Math.min(3, queue.length) }, async () => {
    while (queue.length > 0) {
      const row = queue.shift()!
      try {
        const suggestion = await suggestFileName(row.id, getModelOutputLanguage())
        if (current !== requestId) return
        Object.assign(row, {
          author: suggestion.author,
          year: suggestion.year,
          title: suggestion.title,
          confidence: suggestion.confidence,
          note: suggestion.note,
          include: !!(suggestion.author && suggestion.title),
        })
      } catch (error: any) {
        if (current !== requestId) return
        row.error = error?.response?.data?.detail || t('ui.sourceNamingFailed')
        row.include = false
      } finally {
        row.loading = false
      }
    }
  })
  await Promise.all(workers)
}

function confirm() {
  emit('confirm', readyRows.value.map((row) => ({ id: row.id, fileName: composeName(row) })))
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) loadSuggestions(props.files)
    else requestId++
  },
)

useEscapeClose(() => props.visible, () => emit('close'))
</script>

<style scoped>
.naming-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(31, 41, 55, 0.4);
}

.naming-dialog {
  width: min(760px, 100%);
  max-height: min(86vh, 900px);
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-lg, 16px);
  background: var(--bg-white);
  box-shadow: var(--shadow-lg);
}

.naming-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 12px;
}

.naming-header h3 {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
}

.naming-header p {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.naming-list {
  flex: 1;
  overflow-y: auto;
  margin: 0;
  padding: 4px 24px 8px;
  list-style: none;
}

.naming-row {
  padding: 14px 0;
  border-top: 1px solid var(--border-light, var(--border-color));
}

.naming-row.excluded .naming-fields,
.naming-row.excluded .naming-preview {
  opacity: 0.55;
}

.naming-include {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.naming-current {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.naming-loading,
.naming-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 0 26px;
  font-size: 13px;
  color: var(--text-secondary);
}

.naming-error {
  color: var(--error-color);
}

.naming-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: naming-spin 0.8s linear infinite;
}

.naming-fields {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) 110px minmax(0, 2fr);
  gap: 8px;
  margin: 10px 0 0 26px;
}

.naming-fields label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.naming-fields input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm, 8px);
  background: var(--bg-white);
  color: var(--text-primary);
  font-size: 13.5px;
}

.naming-fields input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: var(--focus-ring);
}

.naming-preview {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 0 26px;
  font-size: 13.5px;
}

.naming-arrow {
  color: var(--text-tertiary);
}

.naming-confidence {
  padding: 2px 8px;
  border-radius: var(--radius-full, 999px);
  font-size: 11.5px;
  font-weight: 600;
}

.naming-confidence.high {
  background: var(--success-soft, #e6f4ea);
  color: var(--success-color, #137333);
}

.naming-confidence.medium {
  background: var(--warning-soft, #fef7e0);
  color: var(--warning-color, #b06000);
}

.naming-confidence.low {
  background: var(--error-soft, #fce8e6);
  color: var(--error-color, #c5221f);
}

.naming-note {
  margin: 6px 0 0 26px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.naming-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px 18px;
  border-top: 1px solid var(--border-light, var(--border-color));
}

.naming-hint {
  margin-right: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}

@media (max-width: 640px) {
  .naming-fields {
    grid-template-columns: 1fr;
  }
}

@keyframes naming-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
