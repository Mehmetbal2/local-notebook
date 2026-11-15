<template>
  <section v-if="sources.length" class="research-sources">
    <button class="rs-toggle" type="button" @click="open = !open">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" :class="{ rotated: open }">
        <path d="M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
      </svg>
      <span>{{ $t('ui.researchSourcesTitle', { count: sources.length, cited: citedCount }) }}</span>
    </button>

    <div v-if="open" class="rs-body">
      <p class="rs-hint">{{ $t('ui.researchSourcesHint') }}</p>
      <div class="rs-actions">
        <label class="rs-select-all">
          <input type="checkbox" :checked="allSelected" :disabled="importing || !selectable.length" @change="toggleAll" />
          <span>{{ $t('ui.selectAll') }}</span>
        </label>
        <button
          class="rs-import"
          type="button"
          :disabled="!selected.size || importing"
          @click="importSelected"
        >
          {{ importing ? $t('ui.webSourcesImporting') : $t('ui.researchSourcesImport', { count: selected.size }) }}
        </button>
      </div>
      <ul class="rs-list">
        <li
          v-for="source in sources"
          :key="source.url"
          class="rs-item"
          :class="{ done: imported.has(source.url), failed: !!errors[source.url] }"
        >
          <input
            type="checkbox"
            :checked="selected.has(source.url) || imported.has(source.url)"
            :disabled="imported.has(source.url) || importing"
            @change="toggle(source.url)"
          />
          <div class="rs-main">
            <div class="rs-title-row">
              <span class="rs-num">[{{ source.n }}]</span>
              <a :href="source.url" target="_blank" rel="noopener noreferrer" class="rs-title">{{ source.title }}</a>
            </div>
            <div class="rs-meta">
              <span>{{ metaLine(source) }}</span>
              <span class="rs-badge" :class="source.full_text ? 'full' : 'abstract'">
                {{ source.full_text ? $t('ui.webSourcesFullText') : $t('ui.webSourcesAbstractOnly') }}
              </span>
              <span v-if="!source.cited" class="rs-badge muted">{{ $t('ui.researchSourceNotCited') }}</span>
              <span v-if="imported.has(source.url)" class="rs-badge added">{{ $t('ui.webSourcesAdded') }}</span>
            </div>
            <p v-if="errors[source.url]" class="rs-error">{{ errors[source.url] }}</p>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ResearchSource } from '../../../types'
import { importWebSources, type WebSourceImportResponse } from '../../../services/api'
import { getModelOutputLanguage, t } from '@/i18n'

const props = defineProps<{
  projectId: string
  sources: ResearchSource[]
}>()

const emit = defineEmits<{
  (e: 'imported', result: WebSourceImportResponse): void
}>()

const open = ref(false)
const importing = ref(false)
const selected = ref(new Set<string>())
const imported = ref(new Set<string>())
const errors = reactive<Record<string, string>>({})

const citedCount = computed(() => props.sources.filter(s => s.cited).length)
const selectable = computed(() => props.sources.filter(s => !imported.value.has(s.url)))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every(s => selected.value.has(s.url)))

watch(() => props.sources, () => {
  selected.value = new Set()
  imported.value = new Set()
  for (const key of Object.keys(errors)) delete errors[key]
})

const RESOLVER_HOSTS = new Set(['oadoi.org', 'doi.org', 'dx.doi.org', 'hdl.handle.net'])

function metaLine(source: ResearchSource): string {
  const who = source.authors?.length
    ? (source.authors.length > 2 ? `${source.authors[0]} ${t('ui.webSourcesEtAl')}` : source.authors.join(', '))
    : ''
  const where = source.venue || (RESOLVER_HOSTS.has(source.domain) ? '' : source.domain)
  return [who, where, source.year].filter(Boolean).join(' · ')
}

function toggle(url: string) {
  const next = new Set(selected.value)
  if (next.has(url)) next.delete(url)
  else next.add(url)
  selected.value = next
}

function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(selectable.value.map(s => s.url))
}

async function importSelected() {
  if (!selected.value.size) return
  importing.value = true
  for (const key of Object.keys(errors)) delete errors[key]
  try {
    const items = props.sources
      .filter(s => selected.value.has(s.url))
      .map(s => ({
        url: s.url,
        title: s.title,
        pdf_url: s.pdf_url || undefined,
        landing_url: s.landing_url || undefined,
        doi: s.doi || undefined,
        authors: s.authors || [],
        published_date: s.year || undefined,
      }))
    const result = await importWebSources(props.projectId, items, getModelOutputLanguage())
    const done = new Set(imported.value)
    for (const file of result.imported) if (file.source_url) done.add(file.source_url)
    for (const skip of result.skipped) done.add(skip.url)
    imported.value = done
    for (const fail of result.failed) errors[fail.url] = fail.reason
    selected.value = new Set()
    emit('imported', result)
  } catch (error: any) {
    const reason = error?.response?.data?.detail || error?.message || t('ui.uploadFailed')
    for (const url of selected.value) errors[url] = reason
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.research-sources {
  margin: 0 0 16px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--bg-main);
}

.rs-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.rs-toggle svg {
  transition: transform 0.15s;
  color: var(--text-tertiary);
}

.rs-toggle svg.rotated {
  transform: rotate(90deg);
}

.rs-body {
  padding: 0 12px 12px;
}

.rs-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.rs-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.rs-select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-secondary);
}

.rs-import {
  padding: 6px 14px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--primary-color);
  color: #fff;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.rs-import:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.rs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 340px;
  overflow-y: auto;
}

.rs-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg-white);
  border: 1px solid transparent;
}

.rs-item.failed {
  border-color: #f04438;
}

.rs-item.done {
  opacity: 0.75;
}

.rs-item input {
  margin-top: 3px;
  accent-color: var(--primary-color);
}

.rs-main {
  min-width: 0;
  flex: 1;
}

.rs-title-row {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.rs-num {
  font-size: 12px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.rs-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  text-decoration: none;
}

.rs-title:hover {
  color: var(--primary-color);
  text-decoration: underline;
}

.rs-meta {
  margin-top: 2px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.rs-badge {
  padding: 0 6px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 600;
}

.rs-badge.full {
  background: #dcfae6;
  color: #067647;
}

.rs-badge.abstract,
.rs-badge.muted {
  background: #f2f4f7;
  color: #475467;
}

.rs-badge.added {
  background: var(--primary-light);
  color: var(--primary-color);
}

.rs-error {
  margin: 4px 0 0;
  font-size: 12px;
  color: #b42318;
}
</style>
