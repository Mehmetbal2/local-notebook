<template>
  <div class="studio-results-scroll">
    <div class="oneclick-queue">
      <div class="queue-header">
        <span class="queue-title">{{ t('ui.generatedResult') }}</span>
        <button class="add-note-btn" type="button" @click="emit('add-note')">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
            <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
          </svg>
          {{ t('ui.addNote') }}
        </button>
      </div>

      <div v-if="allEntries.length > 0" class="result-search">
        <div class="result-search-box" :class="{ active: query }">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
          <input
            v-model="query"
            type="search"
            class="result-search-input"
            :placeholder="t('ui.searchResultsPlaceholder')"
            :aria-label="t('ui.searchResultsPlaceholder')"
            @keydown.esc.prevent="clear"
          />
          <span v-if="searching" class="result-search-spinner" aria-hidden="true"></span>
          <button v-if="query" type="button" class="result-search-clear" :title="t('ui.clearSearch')" @click="clear">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
        <div class="result-filter-row">
          <button
            type="button"
            class="result-filter-chip"
            :class="{ active: searchContent }"
            :title="t('ui.searchResultContentHint')"
            :aria-pressed="searchContent"
            @click="searchContent = !searchContent"
          >{{ t('ui.searchInContent') }}</button>
          <span class="result-filter-sep"></span>
          <button
            v-for="option in kindOptions"
            :key="option.value"
            type="button"
            class="result-filter-chip"
            :class="{ active: kind === option.value }"
            @click="kind = kind === option.value ? 'all' : option.value"
          >{{ option.label }}</button>
        </div>
      </div>

      <div v-if="allEntries.length === 0" class="queue-empty">
        <p v-if="mode === 'oneclick'">{{ hasReadyFiles ? t('ui.useTheButtonsAboveToGenerateAReport') : t('ui.uploadSourcesToGenerateAReport') }}</p>
        <p v-else>{{ hasReadyFiles ? t('ui.useTheButtonsAboveToGenerateQuickTool') : t('ui.uploadSourcesToGenerateQuickTool') }}</p>
      </div>

      <div v-else-if="visibleEntries.length === 0" class="queue-empty">
        <p>{{ t('ui.noResultsMatch') }}</p>
      </div>

      <div v-else class="workflow-list">
        <template v-for="{ key, feature, workflow } in visibleEntries" :key="key">
        <div
          v-if="feature"
          v-key-activate class="workflow-item feature-item"
          :class="{ highlighted: highlightedFeatureId === feature.id }"
          @click="emit('view-feature-detail', feature)"
        >
          <div class="workflow-item-icon icon-default" :class="getFeatureSourceClass(feature)">
            <svg v-bind="getToolIconSvgProps(getFeatureIcon(feature))">
              <path v-for="(d, idx) in getToolIconDefinition(getFeatureIcon(feature)).paths" :key="idx" :d="d" />
            </svg>
          </div>
          <div class="workflow-item-info">
            <div class="workflow-item-title-row">
              <div class="workflow-item-name"><template v-for="(seg, si) in highlight(getFeatureDisplayName(feature), resultWords)" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></div>
              <span class="workflow-source-chip" :class="getFeatureSourceClass(feature)">
                {{ getFeatureSourceLabel(feature) }}
              </span>
            </div>
            <div class="workflow-item-status">
              <span v-if="feature.feature_type !== 'note'" class="workflow-status-badge" :class="getFeatureStatusClass(feature.status)">
                {{ getFeatureStatusText(feature.status) }}
              </span>
              <span v-if="feature.created_at" class="workflow-item-time">{{ formatTime(feature.created_at) }}</span>
            </div>
            <div
              v-if="feature.progress && (feature.status === 'pending' || feature.status === 'processing')"
              class="feature-progress-line"
              :title="feature.progress"
            >{{ feature.progress }}</div>
            <div v-if="resultSnippet(featureHits, feature.id)" class="result-hit" dir="auto">
              <template v-for="(seg, si) in resultSnippet(featureHits, feature.id)!" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template>
              <span v-if="(featureHits.get(feature.id)?.count || 0) > 1" class="result-hit-more">{{ t('ui.moreMatches', { count: (featureHits.get(feature.id)?.count || 0) - 1 }) }}</span>
            </div>
          </div>
          <button
            v-if="feature.status !== 'pending' && feature.status !== 'processing'"
            class="workflow-rename-btn"
            type="button"
            @click.stop="emit('rename-feature', feature, getFeatureDisplayName(feature))"
            :title="t('ui.rename')"
            :aria-label="t('ui.rename')"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button class="workflow-delete-btn" @click.stop="emit('delete-feature', feature)" :title="t('ui.delete')">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
        </div>
        <div
          v-else-if="workflow"
          v-key-activate class="workflow-item"
          :class="{ highlighted: highlightedWorkflowId === workflow.id }"
          @click="emit('view-workflow-detail', workflow.id)"
        >
          <div class="workflow-item-icon icon-default" :class="getWorkflowSourceClass(workflow)">
            <svg v-if="getWorkflowPresetKey(workflow) === 'quick_read'" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M4 4h16v2H4V4zm0 4h10v2H4V8zm0 4h16v2H4v-2zm0 4h10v2H4v-2z"/>
            </svg>
            <svg v-else-if="getWorkflowPresetKey(workflow) === 'deep_dive'" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M9 3h6l1 2h4a1 1 0 0 1 1 1v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4l1-2zm1.24 2-.5 1H5v13h14V7h-4.74l-.5-1h-3.52zM7 10h10v2H7v-2zm0 4h7v2H7v-2z"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 21v-7"/>
              <path d="M4 10V3"/>
              <path d="M12 21v-9"/>
              <path d="M12 8V3"/>
              <path d="M20 21v-5"/>
              <path d="M20 12V3"/>
              <path d="M2 14h4"/>
              <path d="M10 8h4"/>
              <path d="M18 16h4"/>
            </svg>
          </div>
          <div class="workflow-item-info">
            <div class="workflow-item-title-row">
              <div class="workflow-item-name"><template v-for="(seg, si) in highlight(getWorkflowDisplayName(workflow), resultWords)" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></div>
              <span class="workflow-source-chip" :class="getWorkflowSourceClass(workflow)">
                {{ getWorkflowSourceLabel(workflow) }}
              </span>
            </div>
            <div class="workflow-item-status">
              <span class="workflow-status-badge" :class="getWorkflowStatusClass(workflow.status)">
                {{ getWorkflowDisplayStatusText(workflow) }}
              </span>
              <span v-if="isWorkflowActiveStatus(workflow.status)" class="workflow-item-time">
                {{ formatWorkflowProgress(workflow) }}
              </span>
              <span v-if="isWorkflowActiveStatus(workflow.status) && workflow.created_at" class="workflow-item-time">
                {{ formatWorkflowElapsed(workflow.created_at) }}
              </span>
              <span v-else-if="workflow.created_at" class="workflow-item-time">{{ formatTime(workflow.created_at) }}</span>
            </div>
            <div v-if="resultSnippet(workflowHits, workflow.id)" class="result-hit" dir="auto">
              <span v-if="workflowHits.get(workflow.id)?.snippets[0]?.section" class="result-hit-section">{{ workflowHits.get(workflow.id)?.snippets[0]?.section }}:</span>
              <template v-for="(seg, si) in resultSnippet(workflowHits, workflow.id)!" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template>
              <span v-if="(workflowHits.get(workflow.id)?.count || 0) > 1" class="result-hit-more">{{ t('ui.moreMatches', { count: (workflowHits.get(workflow.id)?.count || 0) - 1 }) }}</span>
            </div>
          </div>
          <button
            v-if="isWorkflowCancellable(workflow.status)"
            class="workflow-stop-btn"
            @click.stop="emit('cancel-workflow', workflow.id)"
            :title="t('ui.stopGeneration')"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
              <path d="M6 6h12v12H6z"/>
            </svg>
          </button>
          <button
            v-if="!isWorkflowCancellable(workflow.status)"
            class="workflow-rename-btn"
            type="button"
            @click.stop="emit('rename-workflow', workflow.id, getWorkflowDisplayName(workflow))"
            :title="t('ui.rename')"
            :aria-label="t('ui.rename')"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button v-if="!isWorkflowCancellable(workflow.status)" class="workflow-delete-btn" @click.stop="emit('delete-workflow', workflow.id)" :title="t('ui.delete')">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
        </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { FeatureListItem, SearchHit, WorkflowListItem } from '../../services/api'
import { t } from '../../i18n'
import { TOOL_TYPES, getToolIconDefinition, getToolIconSvgProps } from '../../views/projectPage/toolTypes'
import {
  formatWorkflowProgress,
  getWorkflowDisplayName,
  getWorkflowDisplayStatusText,
  getWorkflowPresetKey,
  getWorkflowSourceClass,
  getWorkflowSourceLabel,
  getWorkflowStatusClass,
  isWorkflowActiveStatus,
  isWorkflowCancellable,
} from '../../views/projectPage/workflowHelpers'
import { useResultSearch, type ResultKind } from '../../composables/useResultSearch'
import { highlight, matchesAll, queryWords, snippetSegments, type TextSegment } from '../../utils/searchText'

/** 'tools' = learning tab, 'analysis' = analysis tab, 'oneclick' = comprehensive reports. */
type PanelMode = 'tools' | 'analysis' | 'oneclick'

const props = defineProps<{
  mode: PanelMode
  features: FeatureListItem[]
  workflows: WorkflowListItem[]
  hasReadyFiles: boolean
  highlightedFeatureId: string | null
  highlightedWorkflowId: string | null
  formatTime: (isoString: string) => string
  formatWorkflowElapsed: (isoString: string) => string
}>()

const emit = defineEmits<{
  (e: 'add-note'): void
  (e: 'view-feature-detail', feature: FeatureListItem): void
  (e: 'rename-feature', feature: FeatureListItem, currentName: string): void
  (e: 'delete-feature', feature: FeatureListItem): void
  (e: 'view-workflow-detail', workflowId: string): void
  (e: 'cancel-workflow', workflowId: string): void
  (e: 'rename-workflow', workflowId: string, currentName: string): void
  (e: 'delete-workflow', workflowId: string): void
}>()

const route = useRoute()
const { query, searchContent, kind, featureHits, workflowHits, searching, clear } =
  useResultSearch(String(route.params.id || ''))

type QuickTool = typeof TOOL_TYPES[number]

function getFeatureTool(feature: FeatureListItem): QuickTool | undefined {
  return TOOL_TYPES.find(tool => tool.type === feature.feature_type)
}

function getFeatureSourceLabel(feature: FeatureListItem): string {
  if (feature.feature_type === 'note') {
    return feature.note_source === 'chat' ? t('ui.noteFromChat') : t('ui.note')
  }
  const tool = getFeatureTool(feature)
  return tool ? t(tool.titleKey) : t('ui.quickTools')
}

function getFeatureDisplayName(feature: FeatureListItem): string {
  return feature.title || feature.display_name || getFeatureSourceLabel(feature)
}

function getFeatureIcon(feature: FeatureListItem): string {
  if (feature.feature_type === 'note') return 'note'
  return getFeatureTool(feature)?.icon || 'summary'
}

function getFeatureSourceClass(feature: FeatureListItem): string {
  if (feature.feature_type === 'note') return 'feature-source-note'
  const color = getFeatureTool(feature)?.color || 'cyan'
  return `feature-source-${color}`
}

function getFeatureStatusText(status: FeatureListItem['status']): string {
  if (status === 'pending') return t('ui.queued')
  if (status === 'processing') return t('ui.generating2')
  if (status === 'completed') return t('ui.completed')
  if (status === 'failed') return t('ui.failed')
  return status
}

function getFeatureStatusClass(status: FeatureListItem['status']): string {
  if (status === 'pending' || status === 'processing') return 'status-processing'
  if (status === 'completed') return 'status-completed'
  if (status === 'failed') return 'status-failed'
  return ''
}

// ── Filters ────────────────────────────────────────────────────────────────
const kindOptions = computed<{ value: ResultKind; label: string }[]>(() => [
  { value: 'note', label: t('ui.filterNotes') },
  {
    value: 'tab',
    label: props.mode === 'oneclick'
      ? t('ui.filterReports')
      : props.mode === 'analysis' ? t('ui.filterAnalysisResults') : t('ui.filterLearningResults'),
  },
  { value: 'deep_research', label: t('ui.deepResearch') },
])

/** Which tab a result belongs to: learning tools, analysis tools (and other quick tools). */
function featureTab(feature: FeatureListItem): PanelMode | null {
  if (feature.feature_type === 'note' || feature.feature_type === 'deep_research') return null
  return getFeatureTool(feature)?.category === 'learn' ? 'tools' : 'analysis'
}

interface Entry {
  key: string
  created: number
  feature?: FeatureListItem
  workflow?: WorkflowListItem
}

const allEntries = computed<Entry[]>(() => {
  const entries: Entry[] = [
    ...props.features.map(feature => ({
      key: `f:${feature.id}`,
      created: Date.parse(feature.created_at || '') || 0,
      feature,
    })),
    ...props.workflows.map(workflow => ({
      key: `w:${workflow.id}`,
      created: Date.parse(workflow.created_at || '') || 0,
      workflow,
    })),
  ]
  return entries.sort((a, b) => b.created - a.created)
})

const resultWords = computed(() => queryWords(query.value))

function passesKind(entry: Entry): boolean {
  switch (kind.value) {
    case 'note':
      return entry.feature?.feature_type === 'note'
    case 'deep_research':
      return entry.feature?.feature_type === 'deep_research'
    case 'tab':
      if (props.mode === 'oneclick') return !!entry.workflow
      return !!entry.feature && featureTab(entry.feature) === props.mode
    default:
      return true
  }
}

function matchesQuery(entry: Entry): boolean {
  if (!resultWords.value.length) return true
  if (entry.feature) {
    return matchesAll(getFeatureDisplayName(entry.feature), resultWords.value) ||
      (searchContent.value && featureHits.value.has(entry.feature.id))
  }
  const workflow = entry.workflow!
  return matchesAll(getWorkflowDisplayName(workflow), resultWords.value) ||
    (searchContent.value && workflowHits.value.has(workflow.id))
}

const visibleEntries = computed(() => allEntries.value.filter(entry => passesKind(entry) && matchesQuery(entry)))

function resultSnippet(hits: Map<string, SearchHit>, id: string): TextSegment[] | null {
  if (!searchContent.value || !resultWords.value.length) return null
  const snippet = hits.get(id)?.snippets[0]
  return snippet ? snippetSegments(snippet.text, snippet.ranges) : null
}
</script>

<style scoped>
/* The box draws the frame and focus ring; the field inside stays plain. */
.result-search-input,
.result-search-input:focus,
.result-search-input:focus-visible {
  border: none;
  border-radius: 0;
  box-shadow: none;
  outline: none;
  padding: 0;
}

.result-search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: var(--focus-ring);
}

.result-search {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 0 10px;
}

.result-search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-white);
  color: var(--text-tertiary);
}

.result-search-box:focus-within,
.result-search-box.active {
  border-color: var(--primary-color);
}

.result-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
}

.result-search-input::-webkit-search-cancel-button {
  display: none;
}

.result-search-clear {
  display: flex;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
}

.result-search-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--primary-light);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: result-search-spin 0.8s linear infinite;
}

@keyframes result-search-spin {
  to { transform: rotate(360deg); }
}

.result-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.result-filter-chip {
  padding: 2px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  background: var(--bg-white);
  color: var(--text-secondary);
  font-size: 11.5px;
  cursor: pointer;
}

.result-filter-chip.active {
  border-color: var(--primary-color);
  background: var(--primary-light);
  color: var(--primary-color);
}

.result-filter-sep {
  width: 1px;
  height: 14px;
  background: var(--border-color);
  margin: 0 2px;
}

.search-hit {
  background: #fde68a;
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}

.result-hit {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-hit-section {
  font-weight: 600;
  margin-right: 4px;
}

.result-hit-more {
  margin-left: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.oneclick-queue {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
  margin-bottom: 8px;
}

.add-note-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 12px 0 8px;
  border-radius: var(--radius-full);
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--border-strong);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 500;
}

.add-note-btn:hover {
  background: var(--bg-hover);
}

.workflow-item-icon.feature-source-note {
  background: #fdefc3;
  color: #8a5a00;
}

.workflow-source-chip.feature-source-note {
  background: #fdefc3;
  color: #8a5a00;
}

.queue-title {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.queue-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  line-height: 1.5;
  color: var(--text-tertiary);
  font-size: 13px;
}

.workflow-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s;
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.workflow-item:hover {
  background: var(--bg-hover);
}

.workflow-item.highlighted {
  background: rgba(20, 184, 166, 0.12);
  box-shadow: inset 0 0 0 1px rgba(13, 148, 136, 0.28);
}

.workflow-item-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-right: 12px;
}

.workflow-item-icon.icon-default {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.workflow-item-icon.source-quick-read {
  background: rgba(147, 197, 253, 0.5);
  color: var(--primary-hover);
}

.workflow-item-icon.source-deep-dive {
  background: rgba(199, 210, 254, 0.5);
  color: #4338ca;
}

.workflow-item-icon.source-custom {
  background:
    rgba(20, 184, 166, 0.28),
    radial-gradient(circle at 85% 12%, rgba(255, 255, 255, 0.68) 0%, rgba(255, 255, 255, 0) 34%);
  border: 1px solid rgba(13, 148, 136, 0.28);
  color: #0f766e;
}

.workflow-item-icon.feature-source-cyan {
  background: rgba(165, 243, 252, 0.5);
  color: #0e7490;
}

.workflow-item-icon.feature-source-amber {
  background: rgba(253, 230, 138, 0.5);
  color: #b45309;
}

.workflow-item-icon.feature-source-indigo {
  background: rgba(199, 210, 254, 0.5);
  color: #4338ca;
}

.workflow-item-icon.feature-source-green {
  background: rgba(187, 247, 208, 0.55);
  color: #15803d;
}

.workflow-item-icon.feature-source-teal {
  background: rgba(153, 246, 228, 0.5);
  color: #0f766e;
}

.workflow-item-icon.feature-source-purple {
  background: rgba(233, 213, 255, 0.55);
  color: #7e22ce;
}

.workflow-item-icon.feature-source-rose {
  background: rgba(254, 205, 211, 0.55);
  color: #be123c;
}

.workflow-item-icon.feature-source-blue {
  background: rgba(147, 197, 253, 0.5);
  color: var(--primary-hover);
}

.workflow-item-icon.feature-source-orange {
  background: rgba(254, 215, 170, 0.6);
  color: #c2410c;
}

.workflow-item-icon.feature-source-custom {
  background:
    rgba(20, 184, 166, 0.28),
    radial-gradient(circle at 85% 12%, rgba(255, 255, 255, 0.68) 0%, rgba(255, 255, 255, 0) 34%);
  border: 1px solid rgba(13, 148, 136, 0.28);
  color: #0f766e;
}

.workflow-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.workflow-item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.workflow-item-name {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.35;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-source-chip {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  height: 18px;
  max-width: 118px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 650;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-source-chip.source-quick-read {
  background: rgba(147, 197, 253, 0.42);
  color: var(--primary-hover);
}

.workflow-source-chip.source-deep-dive {
  background: rgba(199, 210, 254, 0.55);
  color: #4338ca;
}

.workflow-source-chip.source-custom {
  background:
    rgba(20, 184, 166, 0.2),
    radial-gradient(circle at 86% 12%, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0) 36%);
  border: 1px solid rgba(13, 148, 136, 0.22);
  color: #0f766e;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  letter-spacing: 0;
}

.workflow-source-chip.feature-source-cyan {
  background: rgba(165, 243, 252, 0.44);
  color: #0e7490;
}

.workflow-source-chip.feature-source-amber {
  background: rgba(253, 230, 138, 0.5);
  color: #b45309;
}

.workflow-source-chip.feature-source-indigo {
  background: rgba(199, 210, 254, 0.55);
  color: #4338ca;
}

.workflow-source-chip.feature-source-green {
  background: rgba(187, 247, 208, 0.55);
  color: #15803d;
}

.workflow-source-chip.feature-source-teal {
  background: rgba(153, 246, 228, 0.52);
  color: #0f766e;
}

.workflow-source-chip.feature-source-purple {
  background: rgba(233, 213, 255, 0.58);
  color: #7e22ce;
}

.workflow-source-chip.feature-source-rose {
  background: rgba(254, 205, 211, 0.58);
  color: #be123c;
}

.workflow-source-chip.feature-source-blue {
  background: rgba(147, 197, 253, 0.42);
  color: var(--primary-hover);
}

.workflow-source-chip.feature-source-orange {
  background: rgba(254, 215, 170, 0.58);
  color: #c2410c;
}

.workflow-source-chip.feature-source-custom {
  background:
    rgba(20, 184, 166, 0.2),
    radial-gradient(circle at 86% 12%, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0) 36%);
  border: 1px solid rgba(13, 148, 136, 0.22);
  color: #0f766e;
}

.workflow-item-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.workflow-item-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workflow-status-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.feature-progress-line {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-status-badge.status-pending {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.workflow-status-badge.status-processing {
  background: rgba(59, 130, 246, 0.15);
  color: var(--primary-color);
  position: relative;
  animation: workflowBreathing 1.6s ease-in-out infinite;
}

.workflow-status-badge.status-cancelling {
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
  position: relative;
}

.workflow-status-badge.status-completed {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.workflow-status-badge.status-failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--error-color);
}

.workflow-status-badge.status-partial {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.workflow-status-badge.status-cancelled {
  background: rgba(107, 114, 128, 0.15);
  color: var(--text-tertiary);
}

.workflow-status-badge.status-processing::after,
.workflow-status-badge.status-cancelling::after {
  content: '...';
  display: inline-block;
  margin-left: 2px;
  animation: workflowDots 1.2s steps(4, end) infinite;
}

@keyframes workflowDots {
  0% { clip-path: inset(0 100% 0 0); }
  33% { clip-path: inset(0 66% 0 0); }
  66% { clip-path: inset(0 33% 0 0); }
  100% { clip-path: inset(0 0 0 0); }
}

@keyframes workflowBreathing {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.25);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(59, 130, 246, 0);
  }
}

.workflow-stop-btn,
.workflow-delete-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 8px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.workflow-rename-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 8px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.workflow-rename-btn + .workflow-delete-btn {
  margin-left: 2px;
}

.workflow-rename-btn:hover {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.workflow-item:hover .workflow-stop-btn,
.workflow-item:hover .workflow-rename-btn,
.workflow-item:hover .workflow-delete-btn,
.workflow-item:focus-within .workflow-rename-btn,
.workflow-item:focus-within .workflow-delete-btn {
  opacity: 1;
}

@media (hover: none) {
  .workflow-rename-btn,
  .workflow-delete-btn {
    opacity: 1;
  }
}

.workflow-stop-btn {
  opacity: 1;
}

.workflow-stop-btn:hover {
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.workflow-delete-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color);
}
</style>
