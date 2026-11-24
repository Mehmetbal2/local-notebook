<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="handleClose">
      <div class="modal-container" :class="{ 'paste-mode': isPasteMode, 'web-mode': isWebMode }">

        <template v-if="isWebMode">
          <div class="modal-header">
            <button class="back-btn" :disabled="webImporting" @click="exitWebMode">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
              </svg>
            </button>
            <h2>{{ $t('ui.webSourcesTitle') }}</h2>
            <button class="close-btn" @click="handleClose">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
              </svg>
            </button>
          </div>

          <div class="modal-body web-body">
            <div class="web-search-box compact">
              <input
                v-model="webQuery"
                class="web-search-input"
                :placeholder="$t('ui.webSourcesPlaceholder')"
                :disabled="webSearching || webImporting"
                @keydown.enter.prevent="runWebSearch"
              />
              <div class="web-search-controls">
                <div class="scope-pills">
                  <button
                    v-for="option in scopeOptions"
                    :key="option.value"
                    class="scope-pill"
                    :class="{ active: webScope === option.value }"
                    :disabled="webSearching || webImporting"
                    @click="webScope = option.value"
                  >{{ option.label }}</button>
                  <span class="pill-sep"></span>
                  <button
                    v-for="option in depthOptions"
                    :key="option.value"
                    class="scope-pill depth"
                    :class="{ active: webDepth === option.value }"
                    :title="option.hint"
                    :disabled="webSearching || webImporting || deepStarting"
                    @click="webDepth = option.value"
                  >{{ option.label }}</button>
                </div>
                <button class="web-search-go" :disabled="!canSearch" :title="$t('ui.webSourcesSearch')" @click="runWebSearch">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/></svg>
                </button>
              </div>
            </div>

            <div v-if="webSearching" class="web-state">
              <span class="web-spinner"></span>
              <span>{{ $t('ui.webSourcesSearching') }}</span>
            </div>
            <div v-else-if="webError" class="web-state error">{{ webError }}</div>
            <template v-else-if="webSearched">
              <p v-if="webQueries.length" class="web-queries">
                {{ $t('ui.webSourcesQueriesUsed') }}
                <span v-for="q in webQueries" :key="q" class="web-query-chip">{{ q }}</span>
              </p>
              <p v-if="webExpanding" class="web-rank-state">
                <span class="web-spinner small"></span>{{ $t('ui.webSourcesFindingMore') }}
              </p>
              <p v-else-if="webRankState === 'ranking'" class="web-rank-state">
                <span class="web-spinner small"></span>{{ $t('ui.webSourcesRanking') }}
              </p>
              <p v-else-if="webRankState === 'unranked'" class="web-rank-state muted">{{ $t('ui.webSourcesRankUnavailable') }}</p>
              <div v-if="!webResults.length" class="web-state">{{ $t('ui.webSourcesNoResults') }}</div>
              <ul v-else class="web-results">
                <template v-for="(item, index) in webResults" :key="item.url">
                <li v-if="lessRelevantFrom !== null && index === lessRelevantFrom" class="web-divider">
                  {{ $t('ui.webSourcesLessRelevant') }}
                </li>
                <li
                  class="web-result"
                  :class="{
                    selected: selectedUrls.has(item.url),
                    done: item.imported,
                    failed: !!importErrors[item.url],
                    dim: lessRelevantFrom !== null && index >= lessRelevantFrom,
                  }"
                  @click="toggleResult(item)"
                >
                  <input
                    type="checkbox"
                    :checked="selectedUrls.has(item.url) || item.imported"
                    :disabled="item.imported || webImporting"
                    @click.stop="toggleResult(item)"
                  />
                  <div class="web-result-main">
                    <div class="web-result-title-row">
                      <a :href="safeHref(item.url)" target="_blank" rel="noopener noreferrer" class="web-result-title" @click.stop>{{ item.title }}</a>
                      <span v-if="item.imported" class="web-badge done">{{ $t('ui.webSourcesAdded') }}</span>
                    </div>
                    <div class="web-result-meta">
                      <span>{{ metaLine(item) }}</span>
                      <span
                        v-if="accessLabel(item)"
                        class="web-badge"
                        :class="accessClass(item)"
                        :title="accessHint(item)"
                      >{{ accessLabel(item) }}</span>
                    </div>
                    <p v-if="item.reason" class="web-result-reason">{{ item.reason }}</p>
                    <p v-else-if="item.snippet" class="web-result-snippet">{{ item.snippet }}</p>
                    <p v-if="importErrors[item.url]" class="web-result-error">{{ importErrors[item.url] }}</p>
                  </div>
                </li>
                </template>
              </ul>
            </template>
            <p v-else class="web-state hint">{{ $t('ui.webSourcesIntro') }}</p>
          </div>

          <div class="modal-footer web-footer">
            <span class="web-selected-count">
              {{ $t('ui.webSourcesSelectedCount', { count: selectedUrls.size, remaining: remainingCount }) }}
            </span>
            <button
              class="insert-btn"
              :disabled="!selectedUrls.size || webImporting || webSearching"
              @click="importSelected"
            >
              {{ webImporting ? $t('ui.webSourcesImporting') : $t('ui.webSourcesImport', { count: selectedUrls.size }) }}
            </button>
          </div>
        </template>

        <template v-else-if="!isPasteMode">
          <div class="modal-header">
            <h2>{{ $t('ui.generateNotesFromContent') }}</h2>
            <button class="close-btn" @click="handleClose">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">

            <div v-if="isAtLimit" class="limit-warning">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
              </svg>
              <span>{{ $t('ui.fileLimitReachedWithCount', { count: maxFileCount }) }}</span>
            </div>


            <div v-if="projectId" class="web-search-box">
              <div class="web-search-label">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                <span>{{ $t('ui.webSourcesFindTitle') }}</span>
              </div>
              <input
                v-model="webQuery"
                class="web-search-input"
                :placeholder="$t('ui.webSourcesPlaceholder')"
                :disabled="isAtLimit && webDepth === 'quick'"
                @keydown.enter.prevent="runWebSearch"
              />
              <div class="web-search-controls">
                <div class="scope-pills">
                  <button
                    v-for="option in scopeOptions"
                    :key="option.value"
                    class="scope-pill"
                    :class="{ active: webScope === option.value }"
                    @click="webScope = option.value"
                  >{{ option.label }}</button>
                  <span class="pill-sep"></span>
                  <button
                    v-for="option in depthOptions"
                    :key="option.value"
                    class="scope-pill depth"
                    :class="{ active: webDepth === option.value }"
                    :title="option.hint"
                    :disabled="webSearching || webImporting || deepStarting"
                    @click="webDepth = option.value"
                  >{{ option.label }}</button>
                </div>
                <button class="web-search-go" :disabled="!canSearch" :title="$t('ui.webSourcesSearch')" @click="runWebSearch">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/></svg>
                </button>
              </div>
            </div>

            <p v-if="projectId && webDepth === 'deep'" class="deep-hint">{{ $t('ui.deepResearchHint') }}</p>

            <div
              class="upload-dropzone"
              :class="{ dragover: isDragover && !isAtLimit && !props.isUploading, disabled: isAtLimit, uploading: props.isUploading }"
              @click="!isAtLimit && !props.isUploading && triggerFileInput()"
              @dragover.prevent="!isAtLimit && !props.isUploading && (isDragover = true)"
              @dragleave.prevent="isDragover = false"
              @drop.prevent="!props.isUploading && handleDrop($event)"
            >
              <div class="dropzone-icon" :class="{ spinning: props.isUploading }">
                <svg v-if="props.isUploading" viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
                  <path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
                  <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/>
                </svg>
              </div>
              <p class="dropzone-text">{{ props.isUploading ? $t('ui.uploading') : (isAtLimit ? $t('ui.fileLimitReached') : $t('ui.clickToUploadOrDragFilesHere')) }}</p>
              <p class="dropzone-hint">{{ $t('ui.supportsPdfDocxDocEpubJpgJpegPng') }}</p>
              <input
                ref="fileInputRef"
                type="file"
                :accept="SUPPORTED_UPLOAD_ACCEPT"
                multiple
                style="display: none"
                @change="handleFileSelect"
              />
            </div>


            <button class="paste-text-btn" :disabled="isAtLimit || props.isUploading" @click="enterPasteMode">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/>
              </svg>
              <span>{{ $t('ui.pasteText') }}</span>
            </button>
          </div>


          <div class="modal-footer">
            <div class="file-progress">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
              </div>
              <span class="progress-text">{{ currentFileCount }}/{{ maxFileCount }}</span>
            </div>
          </div>
        </template>


        <template v-else>
          <div class="modal-header">
            <button class="back-btn" @click="exitPasteMode">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
              </svg>
            </button>
            <h2>{{ $t('ui.pasteCopiedText') }}</h2>
            <button class="close-btn" @click="handleClose">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
              </svg>
            </button>
          </div>

          <div class="modal-body paste-body">
            <p class="paste-hint">{{ $t('ui.pasteCopiedTextAsSource') }}</p>
            <textarea
              ref="pasteTextareaRef"
              v-model="pasteContent"
              class="paste-textarea"
              :placeholder="$t('ui.pasteTextContentHere')"
            ></textarea>
          </div>

          <div class="modal-footer paste-footer">
            <div class="file-progress">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
              </div>
              <span class="progress-text">{{ currentFileCount }}/{{ maxFileCount }}</span>
            </div>
            <button
              class="insert-btn"
              :disabled="!pasteContent.trim()"
              @click="handleInsertText"
            >
              {{ $t('ui.insert') }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { safeHref } from '../../utils/sanitize'
import { useEscapeClose } from '../../composables/useEscapeClose'
import { ref, computed, watch, nextTick, reactive } from 'vue'
import {
  SUPPORTED_FILE_EXTENSIONS,
  SUPPORTED_UPLOAD_ACCEPT,
} from '../../constants/fileTypes'
import { getModelOutputLanguage, t } from '@/i18n'
import {
  expandWebSources,
  importWebSources,
  rankWebSources,
  searchWebSources,
  startDeepResearch,
  type FeatureListItem,
  type WebSourceImportResponse,
  type WebSourceResult,
} from '../../services/api'

const props = defineProps<{
  visible: boolean
  currentFileCount: number
  maxFileCount?: number
  isUploading?: boolean
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'upload-files', files: File[]): void
  (e: 'insert-text', content: string): void
  (e: 'web-imported', result: WebSourceImportResponse): void
  (e: 'deep-research-started', item: FeatureListItem): void
}>()

const maxFileCount = computed(() => props.maxFileCount || 30)
const progressPercent = computed(() => (props.currentFileCount / maxFileCount.value) * 100)
const isAtLimit = computed(() => props.currentFileCount >= maxFileCount.value)
const remainingCount = computed(() => maxFileCount.value - props.currentFileCount)

const isPasteMode = ref(false)
const isDragover = ref(false)
const pasteContent = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const pasteTextareaRef = ref<HTMLTextAreaElement | null>(null)


// ── Web source search ──────────────────────────────────────────────────────
type WebScope = 'web' | 'academic'
const isWebMode = ref(false)
const webQuery = ref('')
const webScope = ref<WebScope>('web')
const webSearching = ref(false)
const webImporting = ref(false)
const webSearched = ref(false)
const webError = ref('')
const webQueries = ref<string[]>([])
const webResults = ref<WebSourceResult[]>([])
// Model ordering runs after the results are shown: idle → ranking → ranked | unranked
const webRankState = ref<'idle' | 'ranking' | 'ranked' | 'unranked'>('idle')
const webExpanding = ref(false)
const lessRelevantFrom = ref<number | null>(null)
let searchSeq = 0
const selectedUrls = ref(new Set<string>())
const importErrors = reactive<Record<string, string>>({})

type WebDepth = 'quick' | 'deep'
const webDepth = ref<WebDepth>('quick')
const deepStarting = ref(false)
const depthOptions = computed<{ value: WebDepth; label: string; hint: string }[]>(() => [
  { value: 'quick', label: t('ui.quickResearch'), hint: t('ui.quickResearchHint') },
  { value: 'deep', label: t('ui.deepResearch'), hint: t('ui.deepResearchHint') },
])

async function launchDeepResearch() {
  if (!props.projectId || deepStarting.value) return
  deepStarting.value = true
  webError.value = ''
  try {
    const item = await startDeepResearch(props.projectId, webQuery.value.trim(), webScope.value, getModelOutputLanguage())
    emit('deep-research-started', item)
    handleClose()
  } catch (error: any) {
    isWebMode.value = true
    webError.value = errorText(error)
  } finally {
    deepStarting.value = false
  }
}

const scopeOptions = computed<{ value: WebScope; label: string }[]>(() => [
  { value: 'web', label: t('ui.webSourcesScopeWeb') },
  { value: 'academic', label: t('ui.webSourcesScopeAcademic') },
])
const canSearch = computed(() =>
  webQuery.value.trim().length >= (webDepth.value === 'deep' ? 3 : 2) &&
  !webSearching.value && !webImporting.value && !deepStarting.value &&
  (webDepth.value === 'deep' || !isAtLimit.value)
)

function errorText(error: any): string {
  return error?.response?.data?.detail || error?.response?.data?.error || error?.message || t('ui.webSourcesSearchFailed')
}

async function runWebSearch() {
  if (!canSearch.value || !props.projectId) return
  if (webDepth.value === 'deep') {
    await launchDeepResearch()
    return
  }
  isWebMode.value = true
  webSearching.value = true
  webError.value = ''
  webSearched.value = false
  selectedUrls.value = new Set()
  for (const key of Object.keys(importErrors)) delete importErrors[key]
  webRankState.value = 'idle'
  webExpanding.value = false
  lessRelevantFrom.value = null
  const seq = ++searchSeq
  const query = webQuery.value.trim()
  const scope = webScope.value
  try {
    // Phase 1: the user's own query, shown as soon as the search engine answers.
    const data = await searchWebSources(props.projectId, query, scope, getModelOutputLanguage())
    if (seq !== searchSeq) return
    webQueries.value = data.queries || []
    webResults.value = data.results || []
    webSearched.value = true
  } catch (error: any) {
    if (seq === searchSeq) webError.value = errorText(error)
    return
  } finally {
    if (seq === searchSeq) webSearching.value = false
  }
  void enrichAndRank(seq, query, scope)
}

async function enrichAndRank(seq: number, query: string, scope: WebScope) {
  if (!props.projectId) return
  // Phase 2: extra queries from the model. Best effort; phase 1 is already on screen.
  webExpanding.value = true
  try {
    const excludeUrls = webResults.value.map(r => r.url)
    const data = await expandWebSources(
      props.projectId,
      query,
      scope,
      excludeUrls,
      getModelOutputLanguage()
    )
    if (seq !== searchSeq) return
    if (data.queries?.length) webQueries.value = data.queries
    const known = new Set(webResults.value.map(r => r.url))
    const added = (data.results || []).filter(r => !known.has(r.url))
    if (added.length) webResults.value = [...webResults.value, ...added]
  } catch {
    // Expansion is optional; ranking still runs on the first-phase results.
  } finally {
    if (seq === searchSeq) webExpanding.value = false
  }
  if (seq !== searchSeq) return
  await rankResults(seq, query, scope)
}

async function rankResults(seq: number, query: string, scope: WebScope) {
  if (!props.projectId || !webResults.value.length) return
  webRankState.value = 'ranking'
  try {
    const data = await rankWebSources(props.projectId, query, scope, webResults.value, getModelOutputLanguage())
    if (seq !== searchSeq) return
    if (!data.ok || !data.order.length) {
      webRankState.value = 'unranked'
      return
    }
    const byUrl = new Map(webResults.value.map(r => [r.url, r]))
    const picked: WebSourceResult[] = []
    for (const entry of data.order) {
      const row = byUrl.get(entry.url)
      if (!row) continue
      row.reason = entry.reason
      picked.push(row)
      byUrl.delete(entry.url)
    }
    const rest = webResults.value.filter(r => byUrl.has(r.url))
    webResults.value = [...picked, ...rest]
    lessRelevantFrom.value = rest.length ? picked.length : null
    webRankState.value = 'ranked'
  } catch {
    if (seq === searchSeq) webRankState.value = 'unranked'
  }
}

// DOI resolver hosts say nothing about where a work was published.
const RESOLVER_HOSTS = new Set(['oadoi.org', 'doi.org', 'dx.doi.org', 'hdl.handle.net'])

function sourceLabel(item: WebSourceResult): string {
  if (item.venue) return item.venue
  return RESOLVER_HOSTS.has(item.domain) ? '' : item.domain
}

function metaLine(item: WebSourceResult): string {
  return [
    item.authors?.length ? authorLine(item.authors) : '',
    sourceLabel(item),
    item.published_date ? item.published_date.slice(0, 4) : '',
  ].filter(Boolean).join(' · ')
}

function authorLine(authors: string[]): string {
  if (!authors.length) return ''
  return authors.length > 2 ? `${authors[0]} ${t('ui.webSourcesEtAl')}` : authors.join(', ')
}

function accessLabel(item: WebSourceResult): string {
  if (item.access === 'full' || item.kind === 'pdf') return t('ui.webSourcesFullText')
  if (item.access === 'oa_page') return t('ui.webSourcesOpenAccess')
  if (item.access === 'abstract') return t('ui.webSourcesAbstractOnly')
  return ''
}

function accessClass(item: WebSourceResult): string {
  if (item.access === 'full' || item.kind === 'pdf') return 'full'
  if (item.access === 'oa_page') return 'oa'
  return 'abstract'
}

function accessHint(item: WebSourceResult): string {
  if (item.access === 'full' || item.kind === 'pdf') return t('ui.webSourcesFullTextHint')
  if (item.access === 'oa_page') return t('ui.webSourcesOpenAccessHint')
  return t('ui.webSourcesAbstractOnlyHint')
}

function toggleResult(item: WebSourceResult) {
  if (item.imported || webImporting.value) return
  const next = new Set(selectedUrls.value)
  if (next.has(item.url)) {
    next.delete(item.url)
  } else {
    if (next.size >= remainingCount.value) return
    next.add(item.url)
  }
  selectedUrls.value = next
}

async function importSelected() {
  if (!props.projectId || !selectedUrls.value.size) return
  const items = webResults.value
    .filter(r => selectedUrls.value.has(r.url))
    .map(r => ({
      url: r.url,
      title: r.title,
      pdf_url: r.pdf_url || undefined,
      landing_url: r.landing_url || undefined,
      doi: r.doi || undefined,
      authors: r.authors || [],
      published_date: r.published_date || undefined,
    }))
  webImporting.value = true
  for (const key of Object.keys(importErrors)) delete importErrors[key]
  try {
    const result = await importWebSources(props.projectId, items, getModelOutputLanguage())
    const done = new Set([
      ...result.imported.map(f => f.source_url || ''),
      ...result.skipped.map(s => s.url),
    ])
    for (const row of webResults.value) {
      if (done.has(row.url)) row.imported = true
    }
    for (const fail of result.failed) importErrors[fail.url] = fail.reason
    selectedUrls.value = new Set()
    emit('web-imported', result)
    if (!result.failed.length) handleClose()
  } catch (error: any) {
    webError.value = errorText(error)
  } finally {
    webImporting.value = false
  }
}

function exitWebMode() {
  if (webImporting.value) return
  isWebMode.value = false
}

function resetWebSearch() {
  searchSeq++
  webRankState.value = 'idle'
  webExpanding.value = false
  lessRelevantFrom.value = null
  isWebMode.value = false
  webSearching.value = false
  webSearched.value = false
  webError.value = ''
  webQueries.value = []
  webResults.value = []
  selectedUrls.value = new Set()
  for (const key of Object.keys(importErrors)) delete importErrors[key]
}

watch(() => props.visible, (newVal) => {
  if (!newVal) {
    isPasteMode.value = false
    pasteContent.value = ''
    isDragover.value = false
    if (!webImporting.value) resetWebSearch()
  }
})

function handleClose() {
  emit('close')
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileSelect(event: Event) {
  if (isAtLimit.value) return
  const input = event.target as HTMLInputElement
  const files = input.files
  if (files && files.length > 0) {

    const filesToUpload = Array.from(files).slice(0, remainingCount.value)
    if (filesToUpload.length > 0) {
      emit('upload-files', filesToUpload)
      handleClose()
    }
    input.value = ''
  }
}

function handleDrop(event: DragEvent) {
  isDragover.value = false
  if (isAtLimit.value) return
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {

    const validFiles = Array.from(files).filter(file => {
      const ext = file.name.toLowerCase().split('.').pop()
      return SUPPORTED_FILE_EXTENSIONS.includes(ext || '')
    })

    const filesToUpload = validFiles.slice(0, remainingCount.value)
    if (filesToUpload.length > 0) {
      emit('upload-files', filesToUpload)
      handleClose()
    }
  }
}

function enterPasteMode() {
  isPasteMode.value = true
  nextTick(() => {
    pasteTextareaRef.value?.focus()
  })
}

function exitPasteMode() {
  isPasteMode.value = false
  pasteContent.value = ''
}

function handleInsertText() {
  if (pasteContent.value.trim()) {
    emit('insert-text', pasteContent.value.trim())
    handleClose()
  }
}

useEscapeClose(() => props.visible, () => handleClose())
</script>

<style scoped>
/* The box draws the frame and focus ring; the field inside stays plain. */
.web-search-input,
.web-search-input:focus,
.web-search-input:focus-visible {
  border: none;
  border-radius: 0;
  box-shadow: none;
  outline: none;
  padding: 0;
}

.web-search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: var(--focus-ring);
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  width: 560px;
  max-width: 90vw;
  max-height: 80vh;
  background: var(--bg-white);
  border-radius: var(--radius-xl);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  animation: slideUp 0.25s ease;
}

.modal-container.paste-mode {
  height: 500px;
}

.modal-container.web-mode {
  width: 720px;
  height: 80vh;
}

.web-search-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  background: var(--bg-white);
}

.web-search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-light);
}

.web-search-box.compact {
  padding: 10px 12px;
  gap: 8px;
}

.web-search-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.web-search-label svg {
  color: var(--primary-color);
}

.web-search-input {
  width: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  color: var(--text-primary);
  padding: 4px 2px;
}

.web-search-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.scope-pills {
  display: flex;
  gap: 6px;
}

.scope-pill {
  padding: 5px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  background: var(--bg-white);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.scope-pill.active {
  border-color: var(--primary-color);
  background: var(--primary-light);
  color: var(--primary-color);
  font-weight: 500;
}

.scope-pill:disabled {
  cursor: default;
  opacity: 0.6;
}

.pill-sep {
  width: 1px;
  align-self: stretch;
  margin: 2px 4px;
  background: var(--border-color);
}

.deep-hint {
  margin: -6px 2px 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.45;
}

.web-search-go {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-color);
  color: white;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.web-search-go:disabled {
  background: var(--bg-hover);
  color: var(--text-tertiary);
  cursor: not-allowed;
}

.web-body {
  overflow: hidden;
  min-height: 0;
  gap: 12px;
}

.web-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px 16px;
  color: var(--text-secondary);
  font-size: 14px;
  text-align: center;
}

.web-state.error {
  color: #b42318;
  background: #fef3f2;
  border-radius: 12px;
  padding: 16px;
}

.web-state.hint {
  color: var(--text-tertiary);
}

.web-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--primary-light);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.web-rank-state {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--primary-color);
}

.web-rank-state.muted {
  color: var(--text-tertiary);
}

.web-spinner.small {
  width: 12px;
  height: 12px;
  border-width: 2px;
}

.web-divider {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 6px 2px 0;
  border-top: 1px dashed var(--border-color);
  margin-top: 4px;
}

.web-result.dim {
  opacity: 0.7;
}

.web-queries {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.web-query-chip {
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--bg-main);
  color: var(--text-secondary);
}

.web-results {
  list-style: none;
  margin: 0;
  padding: 0 4px 0 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.web-result {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.web-result:hover {
  border-color: var(--primary-color);
}

.web-result.selected {
  border-color: var(--primary-color);
  background: var(--primary-light);
}

.web-result.done {
  cursor: default;
  opacity: 0.75;
}

.web-result.failed {
  border-color: #f04438;
}

.web-result input[type='checkbox'] {
  margin-top: 3px;
  flex-shrink: 0;
  accent-color: var(--primary-color);
}

.web-result-main {
  min-width: 0;
  flex: 1;
}

.web-result-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.web-result-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.web-result-title:hover {
  color: var(--primary-color);
  text-decoration: underline;
}

.web-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 6px;
}

.web-badge.full {
  background: #dcfae6;
  color: #067647;
}

.web-badge.oa {
  background: #e0f2fe;
  color: #026aa2;
}

.web-badge.abstract {
  background: #f2f4f7;
  color: #475467;
}

.web-result-meta .web-badge {
  margin-left: 4px;
  font-size: 10.5px;
}

.web-badge.done {
  background: var(--primary-light);
  color: var(--primary-color);
}

.web-result-meta {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-tertiary);
  display: flex;
  gap: 4px;
}

.web-result-reason,
.web-result-snippet,
.web-result-error {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.45;
}

.web-result-reason {
  color: var(--text-secondary);
}

.web-result-snippet {
  color: var(--text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.web-result-error {
  color: #b42318;
}

.web-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid var(--border-color);
}

.web-selected-count {
  font-size: 13px;
  color: var(--text-tertiary);
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 24px 16px;
  position: relative;
}

.modal-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  position: absolute;
  right: 20px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: 50%;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.back-btn {
  position: absolute;
  left: 20px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: 50%;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.back-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  padding: 16px 24px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.limit-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 8px;
  color: #b45309;
  font-size: 14px;
}

.upload-dropzone {
  border: 2px dashed var(--border-color);
  border-radius: 16px;
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-main);
}

.upload-dropzone:hover:not(.disabled),
.upload-dropzone.dragover {
  border-color: var(--primary-color);
  background: var(--primary-light);
}

.upload-dropzone.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-dropzone.uploading {
  cursor: default;
  border-color: var(--primary-color);
  background: var(--primary-light);
}

.dropzone-icon {
  color: var(--text-tertiary);
  margin-bottom: 16px;
  transition: color 0.2s;
}

.upload-dropzone:hover .dropzone-icon,
.upload-dropzone.dragover .dropzone-icon,
.upload-dropzone.uploading .dropzone-icon {
  color: var(--primary-color);
}

.dropzone-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.dropzone-text {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.dropzone-hint {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}

.dropzone-hint.unsupported {
  text-decoration: line-through;
  opacity: 0.5;
  font-size: 12px;
  margin-top: 4px;
}

.paste-text-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 14px 24px;
  background: var(--bg-white);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.paste-text-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.paste-text-btn svg {
  color: var(--text-secondary);
}

.paste-text-btn:hover:not(:disabled) svg {
  color: var(--primary-color);
}

.paste-text-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}


.paste-body {
  padding: 8px 24px 16px;
}

.paste-hint {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 16px;
}

.paste-textarea {
  flex: 1;
  width: 100%;
  padding: 16px;
  border: 2px solid var(--primary-color);
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--bg-white);
  resize: none;
  outline: none;
}

.paste-textarea::placeholder {
  color: var(--text-tertiary);
}

.paste-textarea:focus {
  box-shadow: 0 0 0 3px var(--primary-light);
}

.modal-footer {
  padding: 16px 24px 24px;
}

.paste-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.file-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-hover);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 13px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.insert-btn {
  padding: 12px 32px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--radius-full);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.insert-btn:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: scale(1.02);
}

.insert-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
