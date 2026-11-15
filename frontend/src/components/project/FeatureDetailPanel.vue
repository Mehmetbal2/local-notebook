<template>
  <div class="feature-detail-panel">
    <div class="panel-header">

      <div class="panel-title-row">
        <input
          v-if="isEditingTitle"
          ref="titleInputRef"
          v-model="editingTitleValue"
          class="panel-title-input"
          @blur="handleSaveTitle"
          @keydown.enter="handleSaveTitle"
          @keydown.escape="cancelEditTitle"
        />
        <span
          v-else
          class="panel-title editable"
          @click="startEditTitle"
          :title="$t('ui.clickToRename')"
        >{{ feature.title || $t('ui.toolbox') }}</span>
      </div>
      <span v-if="!isNote" class="feature-status-badge" :class="getFeatureStatusClass(feature.status)">
        {{ getFeatureStatusText(feature.status) }}
      </span>
      <span v-else class="feature-status-badge status-note">{{ $t('ui.note') }}</span>

      <button class="panel-toggle-btn" @click="$emit('close')" :title="$t('ui.close')">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      </button>
    </div>

    <div v-if="hasContent" class="feature-toolbar">
      <div v-if="interactive" class="view-switch" role="tablist">
        <button
          class="view-switch-btn"
          :class="{ active: viewMode === 'interactive' }"
          type="button"
          role="tab"
          :aria-selected="viewMode === 'interactive'"
          @click="viewMode = 'interactive'"
        >{{ $t('ui.interactiveView') }}</button>
        <button
          class="view-switch-btn"
          :class="{ active: viewMode === 'document' }"
          type="button"
          role="tab"
          :aria-selected="viewMode === 'document'"
          @click="viewMode = 'document'"
        >{{ $t('ui.documentView') }}</button>
      </div>
      <span class="feature-toolbar-spacer"></span>
      <button v-if="isManualNote" class="toolbar-btn" type="button" :title="$t('ui.editNote')" :aria-label="$t('ui.editNote')" @click="emit('editNote')">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
          <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" />
        </svg>
      </button>
      <button class="toolbar-btn" type="button" :title="$t('ui.copyContent')" :aria-label="$t('ui.copyContent')" @click="copyContent">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
          <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
        </svg>
      </button>
      <div ref="downloadMenuRef" class="toolbar-menu-wrap">
        <button
          class="toolbar-btn"
          type="button"
          :title="$t('ui.download')"
          :aria-label="$t('ui.download')"
          aria-haspopup="menu"
          :aria-expanded="downloadMenuOpen"
          @click="downloadMenuOpen = !downloadMenuOpen"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" />
          </svg>
        </button>
        <div v-if="downloadMenuOpen" class="toolbar-menu" role="menu">
          <button type="button" role="menuitem" @click="downloadAs('md')">{{ $t('ui.downloadMarkdown') }}</button>
          <button type="button" role="menuitem" @click="downloadAs('doc')">{{ $t('ui.downloadWord') }}</button>
        </div>
      </div>
      <button v-if="!isNote" class="toolbar-btn" type="button" :title="$t('ui.regenerate')" :aria-label="$t('ui.regenerate')" @click="emit('regenerate')">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
          <path d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
        </svg>
      </button>
    </div>

    <div
      class="feature-report-content"
      :class="{ 'is-canvas': interactive?.kind === 'mind_map' && viewMode === 'interactive' }"
      ref="featureReportRef"
      @click="handleContentClick"
    >
      <div v-if="interactive && viewMode === 'interactive'" class="interactive-body">
        <FlashcardsView
          v-if="interactive.kind === 'flashcards'"
          :cards="interactive.cards"
          :active-citation-num="activeCitationNum"
          @citation-click="emit('citationClick', $event)"
        />
        <FaqView
          v-else-if="interactive.kind === 'faq'"
          :items="interactive.cards"
          :active-citation-num="activeCitationNum"
          @citation-click="emit('citationClick', $event)"
        />
        <QuizView
          v-else-if="interactive.kind === 'quiz'"
          :questions="interactive.questions"
          :active-citation-num="activeCitationNum"
          @citation-click="emit('citationClick', $event)"
        />
        <TimelineView
          v-else-if="interactive.kind === 'timeline'"
          :entries="interactive.entries"
          :active-citation-num="activeCitationNum"
          @citation-click="emit('citationClick', $event)"
        />
        <PodcastView
          v-else-if="interactive.kind === 'podcast'"
          :turns="interactive.turns"
          :title="feature.title || $t('ui.podcast')"
          :audio-url="audioBlock?.asset?.url ? getAssetUrl(audioBlock.asset.url) : undefined"
          :caption="audioBlock?.caption || undefined"
          :active-citation-num="activeCitationNum"
          @citation-click="emit('citationClick', $event)"
        />
        <MindMapView
          v-else-if="interactive.kind === 'mind_map'"
          :root="interactive.root"
          :title="feature.title || undefined"
          @ask="emit('askInChat', $event)"
        />
      </div>
      <div v-else-if="feature.blocks && feature.blocks.length > 0" class="report-body">
        <ResearchSourcesPanel
          v-if="feature.feature_type === 'deep_research' && feature.research_sources?.length"
          :project-id="feature.project_id"
          :sources="feature.research_sources"
          @imported="result => emit('sourcesImported', result)"
        />
        <template v-for="(processed, idx) in processFeatureBlocks(feature.blocks)" :key="idx">
          <div
            v-if="processed.type === 'single' && processed.block"
            class="feature-block"
            :data-block-index="processed.originalIndex"
          >
            <component
              v-if="processed.block.block_type === 'heading'"
              :is="'h' + (processed.block.level || 2)"
              class="feature-heading"
              dir="auto"
            ><template v-for="(part, pi) in processed.block.content_parts" :key="pi"><span v-if="part.type === 'text'" class="feature-text" v-html="parseInlineMarkdown(part.content)"></span><sup
                  v-else-if="part.type === 'citation_ref'"
                  class="inline-citation"
                  :class="{ active: activeCitationNum === part.display_num }"
                  :data-segment-id="part.segment_id"
                  :data-display-num="part.display_num"
                  :title="part.summary"
                  @click="$emit('citationClick', part)"
                >{{ part.display_num }}</sup></template></component>

            <div
              v-else-if="processed.block.block_type === 'paragraph' && processed.block.extra?.is_table && parseMarkdownTable(getTableContent(processed.block))"
              class="feature-table"
              dir="auto"
            >
              <table>
                <thead>
                  <tr>
                    <th v-for="(header, hi) in parseMarkdownTable(getTableContent(processed.block))!.headers" :key="hi" dir="auto">
                      <template v-for="(part, pi) in header.parts" :key="pi">
                        <span v-if="part.type === 'text'" v-html="parseInlineMarkdown(part.content || '')"></span>
                        <sup
                          v-else-if="part.type === 'citation_ref'"
                          class="inline-citation"
                          :class="{ active: activeCitationNum === part.display_num }"
                          :data-segment-id="part.segment_id"
                          :data-display-num="part.display_num"
                          :title="part.summary"
                          @click="$emit('citationClick', part)"
                        >{{ part.display_num }}</sup>
                      </template>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in parseMarkdownTable(getTableContent(processed.block))!.rows" :key="ri">
                    <td v-for="(cell, ci) in row" :key="ci" dir="auto">
                      <template v-for="(part, pi) in cell.parts" :key="pi">
                        <span v-if="part.type === 'text'" v-html="parseInlineMarkdown(part.content || '')"></span>
                        <sup
                          v-else-if="part.type === 'citation_ref'"
                          class="inline-citation"
                          :class="{ active: activeCitationNum === part.display_num }"
                          :data-segment-id="part.segment_id"
                          :data-display-num="part.display_num"
                          :title="part.summary"
                          @click="$emit('citationClick', part)"
                        >{{ part.display_num }}</sup>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <hr v-else-if="isRuleBlock(processed.block)" class="feature-rule" />

            <p v-else-if="processed.block.block_type === 'paragraph'" class="feature-paragraph" dir="auto">
              <template v-for="(part, pi) in processed.block.content_parts" :key="pi"><span v-if="part.type === 'text'" class="feature-text" v-html="parseInlineMarkdown(part.content)"></span><sup
                  v-else-if="part.type === 'citation_ref'"
                  class="inline-citation"
                  :class="{ active: activeCitationNum === part.display_num }"
                  :data-segment-id="part.segment_id"
                  :data-display-num="part.display_num"
                  :title="part.summary"
                  @click="$emit('citationClick', part)"
                >{{ part.display_num }}</sup></template>
            </p>

            <blockquote v-else-if="processed.block.block_type === 'quote'" class="feature-quote" dir="auto"><template v-for="(part, pi) in processed.block.content_parts" :key="pi"><span v-if="part.type === 'text'" class="feature-text" v-html="parseInlineMarkdown(part.content)"></span><sup
                  v-else-if="part.type === 'citation_ref'"
                  class="inline-citation"
                  :class="{ active: activeCitationNum === part.display_num }"
                  :data-segment-id="part.segment_id"
                  :data-display-num="part.display_num"
                  :title="part.summary"
                  @click="$emit('citationClick', part)"
                >{{ part.display_num }}</sup></template></blockquote>

            <figure v-else-if="processed.block.block_type === 'image'" class="feature-image">
              <div class="image-wrapper">
                <img v-if="processed.block.asset" :src="getAssetUrl(processed.block.asset.url)" :alt="processed.block.caption || ''" />
                <button v-if="processed.block.asset" class="image-download-btn" @click="downloadImage(getAssetUrl(processed.block.asset.url))" :title="$t('ui.downloadImage')">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                    <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                  </svg>
                </button>
              </div>
              <figcaption v-if="processed.block.caption">{{ processed.block.caption }}</figcaption>
            </figure>

            <div v-else-if="processed.block.block_type === 'image_group'" class="feature-image-group">
              <figure v-for="(asset, ai) in processed.block.assets" :key="ai" class="feature-image">
                <div class="image-wrapper">
                  <img :src="getAssetUrl(asset.url)" :alt="processed.block.caption || ''" />
                  <button class="image-download-btn" @click="downloadImage(getAssetUrl(asset.url))" :title="$t('ui.downloadImage')">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                      <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                    </svg>
                  </button>
                </div>
              </figure>
              <figcaption v-if="processed.block.caption">{{ processed.block.caption }}</figcaption>
            </div>

            <figure v-else-if="processed.block.block_type === 'video'" class="feature-video">
              <video v-if="processed.block.asset" :src="getAssetUrl(processed.block.asset.url)" controls :poster="processed.block.asset.thumbnail_url ? getAssetUrl(processed.block.asset.thumbnail_url) : undefined"></video>
              <figcaption v-if="processed.block.caption">{{ processed.block.caption }}</figcaption>
            </figure>

            <div v-else-if="processed.block.block_type === 'audio' && processed.block.asset?.url" class="feature-audio-card">
              <div class="feature-audio-header">
                <div class="feature-audio-meta">
                  <span class="feature-audio-icon">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                      <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                    </svg>
                  </span>
                  <span class="feature-audio-title">{{ feature.title || $t('ui.audioOverview') }}</span>
                  <span v-if="processed.block.caption" class="feature-audio-caption">{{ processed.block.caption }}</span>
                </div>
                <button
                  type="button"
                  class="feature-audio-download"
                  @click.prevent="downloadAudio(getAssetUrl(processed.block.asset.url), processed.block.asset.mime_type)"
                  :title="$t('ui.downloadAudio')"
                >
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
                    <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                  </svg>
                  <span>{{ $t('ui.downloadAudio') }}</span>
                </button>
              </div>
              <AudioPlayer :src="getAssetUrl(processed.block.asset.url)" class="feature-audio-element" />
            </div>
          </div>

          <div
            v-else-if="processed.type === 'list_group' && processed.blocks"
            class="feature-block"
          >
            <ul class="feature-list">
              <li v-for="(listBlock, li) in processed.blocks" :key="li" dir="auto"><template v-for="(part, pi) in listBlock.content_parts" :key="pi"><span v-if="part.type === 'text'" class="feature-text" v-html="parseInlineMarkdown(part.content)"></span><sup
                    v-else-if="part.type === 'citation_ref'"
                    class="inline-citation"
                    :class="{ active: activeCitationNum === part.display_num }"
                    :data-segment-id="part.segment_id"
                    :data-display-num="part.display_num"
                    :title="part.summary"
                    @click="$emit('citationClick', part)"
                  >{{ part.display_num }}</sup></template></li>
            </ul>
          </div>
        </template>
      </div>
      <div v-else-if="feature.status === 'failed'" class="report-error">
        <p>{{ $t('ui.generationFailedWithReason', { reason: feature.error_message || $t('ui.unknownError') }) }}</p>
      </div>
      <div v-else-if="feature.status === 'pending' || feature.status === 'processing'" class="report-waiting">
        <div class="report-waiting-spinner"></div>
        <p>{{ feature.status === 'pending' ? $t('ui.quickToolQueuedMessage') : $t('ui.quickToolGeneratingMessage') }}</p>
        <p v-if="feature.progress" class="report-waiting-progress">{{ feature.progress }}</p>
      </div>
      <div v-else class="report-empty">
        <p>{{ $t('ui.quickToolNoContentYet') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Feature, FeatureBlock, FeatureCitationRefPart } from '../../types'
import { marked } from 'marked'
import { parseInlineMarkdown, sanitizeHtml } from '../../utils'
import { markRtlForWord } from '../../utils/wordRtl'
import FlashcardsView from './feature/FlashcardsView.vue'
import AudioPlayer from '../common/AudioPlayer.vue'
import FaqView from './feature/FaqView.vue'
import QuizView from './feature/QuizView.vue'
import TimelineView from './feature/TimelineView.vue'
import MindMapView from './feature/MindMapView.vue'
import PodcastView from './feature/PodcastView.vue'
import ResearchSourcesPanel from './feature/ResearchSourcesPanel.vue'
import {
  blocksToMarkdown,
  isRuleBlock,
  getInteractiveKind,
  parseCards,
  parseDialogue,
  parseMindMap,
  parseQuiz,
  parseTimeline,
  type CardItem,
  type DialogueTurn,
  type MindNode,
  type QuizQuestion,
  type TimelineEntry,
} from './feature/featureStructure'
import { getAssetUrl, getFeatureReferences, type SourceReference, type WebSourceImportResponse } from '../../services/api'
import { t } from '../../i18n'


const isEditingTitle = ref(false)
const editingTitleValue = ref('')
const titleInputRef = ref<HTMLInputElement | null>(null)

const props = defineProps<{
  feature: Feature
  activeCitationNum: number | null
}>()


const emit = defineEmits<{
  (e: 'close'): void
  (e: 'citationClick', part: FeatureCitationRefPart): void
  (e: 'clearCitation'): void
  (e: 'rename', newTitle: string): void
  (e: 'regenerate'): void
  (e: 'editNote'): void
  (e: 'askInChat', payload: { topic: string; context: string }): void
  (e: 'sourcesImported', result: WebSourceImportResponse): void
}>()

type InteractiveContent =
  | { kind: 'flashcards' | 'faq'; cards: CardItem[] }
  | { kind: 'quiz'; questions: QuizQuestion[] }
  | { kind: 'timeline'; entries: TimelineEntry[] }
  | { kind: 'mind_map'; root: MindNode }
  | { kind: 'podcast'; turns: DialogueTurn[] }

const isNote = computed(() => props.feature.feature_type === 'note')
const isManualNote = computed(() => isNote.value && props.feature.note_source === 'manual')
const hasContent = computed(() => props.feature.status === 'completed' && (props.feature.blocks?.length || 0) > 0)

/** Structured form of the result, or null when it only reads as a document. */
const interactive = computed<InteractiveContent | null>(() => {
  if (!hasContent.value) return null
  const blocks = props.feature.blocks
  const kind = getInteractiveKind(props.feature)
  if (kind === 'flashcards' || kind === 'faq') {
    const cards = parseCards(blocks)
    return cards ? { kind, cards } : null
  }
  if (kind === 'quiz') {
    const questions = parseQuiz(blocks)
    return questions ? { kind, questions } : null
  }
  if (kind === 'timeline') {
    const entries = parseTimeline(blocks)
    return entries ? { kind, entries } : null
  }
  if (kind === 'mind_map') {
    const root = parseMindMap(blocks, props.feature.title || t('ui.mindMap'))
    return root ? { kind, root } : null
  }
  if (kind === 'podcast') {
    const turns = parseDialogue(blocks)
    return turns ? { kind, turns } : null
  }
  return null
})

const audioBlock = computed(() => {
  const block = props.feature.blocks?.find((item) => item.block_type === 'audio')
  return block && block.block_type === 'audio' ? block : null
})

const viewMode = ref<'interactive' | 'document'>('interactive')
watch(() => props.feature.id, () => { viewMode.value = 'interactive' })

const downloadMenuOpen = ref(false)
const downloadMenuRef = ref<HTMLElement | null>(null)

function notify(message: string, type: 'success' | 'error' = 'success') {
  window.dispatchEvent(new CustomEvent('global-toast', { detail: { message, type } }))
}

/** Markdown of the result, with each source as: work name, page, and a sentence to search for. */
async function markdownWithReferences(): Promise<string> {
  let references: Record<string, SourceReference> = {}
  try {
    references = await getFeatureReferences(props.feature.id)
  } catch (error) {
    console.warn('Could not load reference details; using file names only:', error)
  }
  const formatReference = (citationId: string): string | null => {
    const ref = references[citationId]
    if (!ref?.name) return null
    let location = ''
    if (ref.page) {
      location = ref.volume
        ? t('ui.refVolumePage', { volume: ref.volume, page: ref.page })
        : ref.page_kind === 'pdf'
          ? t('ui.refPdfPage', { page: ref.page })
          : t('ui.refPage', { page: ref.page })
    }
    const head = location ? `${ref.name}, ${location}` : ref.name
    return ref.sentence ? `${head} — “${ref.sentence}”` : head
  }
  return blocksToMarkdown(props.feature, { host: t('ui.podcastHost'), guest: t('ui.podcastGuest') }, formatReference)
}

async function copyContent() {
  const markdown = await markdownWithReferences()
  try {
    await navigator.clipboard.writeText(markdown)
    notify(t('ui.copied'))
  } catch {
    notify(t('ui.copyFailed'), 'error')
  }
}

function safeFileName(): string {
  const base = (props.feature.title || t('ui.note')).replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ').trim()
  return (base || 'export').slice(0, 80)
}

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function downloadAs(format: 'md' | 'doc') {
  downloadMenuOpen.value = false
  const markdown = await markdownWithReferences()

  if (format === 'md') {
    saveBlob(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }), `${safeFileName()}.md`)
    return
  }

  // Word opens HTML saved with a .doc extension; this keeps headings, lists and tables.
  const body = markRtlForWord(sanitizeHtml(marked.parse(markdown, { async: false }) as string))
  const html = `<!DOCTYPE html><html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"><title></title><style>body{font-family:Calibri,Arial,sans-serif;mso-bidi-font-family:'Times New Roman';font-size:11pt;line-height:1.5}h1{font-size:20pt}h2{font-size:15pt}h3{font-size:12pt}table{border-collapse:collapse}td,th{border:1px solid #999;padding:4pt 6pt}blockquote{margin-left:0;padding-left:10pt;border-left:3pt solid #bbb;color:#444}</style></head><body dir="auto">${body}</body></html>`
  saveBlob(new Blob(['\ufeff', html], { type: 'application/msword' }), `${safeFileName()}.doc`)
}

function handleDocumentClick(event: MouseEvent) {
  if (downloadMenuRef.value && !downloadMenuRef.value.contains(event.target as Node)) {
    downloadMenuOpen.value = false
  }
}

onMounted(() => document.addEventListener('click', handleDocumentClick))
onUnmounted(() => document.removeEventListener('click', handleDocumentClick))


function handleContentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  
  if (!target.closest('.inline-citation')) {
    emit('clearCitation')
  }
}


interface ProcessedBlock {
  type: 'single' | 'list_group'
  block?: any
  blocks?: any[]
  originalIndex?: number
  originalIndices?: number[]
}

interface TableTextPart {
  type: 'text'
  content?: string
}

interface TableCitationPart {
  type: 'citation_ref'
  citation_id: string
  display_num: number
  segment_id?: string
  summary?: string
}

type TableCellPart = TableTextPart | TableCitationPart

interface ParsedTable {
  headers: Array<{ parts: TableCellPart[] }>
  rows: Array<Array<{ parts: TableCellPart[] }>>
}

function processFeatureBlocks(blocks: FeatureBlock[]): ProcessedBlock[] {
  if (!blocks || blocks.length === 0) return []

  const result: ProcessedBlock[] = []
  let currentListGroup: { block: FeatureBlock; index: number }[] = []

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i]!
    if (block.block_type === 'list') {
      currentListGroup.push({ block, index: i })
    } else {
      
      if (currentListGroup.length > 0) {
        result.push({
          type: 'list_group',
          blocks: currentListGroup.map(item => item.block),
          originalIndices: currentListGroup.map(item => item.index)
        })
        currentListGroup = []
      }
      result.push({ type: 'single', block, originalIndex: i })
    }
  }

  
  if (currentListGroup.length > 0) {
    result.push({
      type: 'list_group',
      blocks: currentListGroup.map(item => item.block),
      originalIndices: currentListGroup.map(item => item.index)
    })
  }

  return result
}

function getTableContent(block: any): string {
  if (block.content && typeof block.content === 'string') {
    return block.content
  }

  if (block.content_parts && Array.isArray(block.content_parts)) {
    return block.content_parts
      .map((part: any) => {
        if (part.type === 'text') return part.content || ''
        if (part.type === 'citation_ref') return `[${part.citation_id}]`
        return ''
      })
      .join('')
  }

  return ''
}

function parseTableCellContent(cellText: string): TableCellPart[] {
  const parts: TableCellPart[] = []
  const regex = /\[(citation_[a-zA-Z0-9_]+)\]/g
  let lastIndex = 0
  let match

  while ((match = regex.exec(cellText)) !== null) {
    if (match.index > lastIndex) {
      parts.push({
        type: 'text',
        content: cellText.slice(lastIndex, match.index)
      })
    }

    const citationId = match[1] as string
    const citation = props.feature.citations?.[citationId]
    parts.push({
      type: 'citation_ref',
      citation_id: citationId,
      display_num: citation?.display_num || 0,
      segment_id: citation?.segment_id,
      summary: citation?.summary
    })

    lastIndex = regex.lastIndex
  }

  if (lastIndex < cellText.length) {
    parts.push({
      type: 'text',
      content: cellText.slice(lastIndex)
    })
  }

  if (parts.length === 0) {
    parts.push({ type: 'text', content: '' })
  }

  return parts
}

function parseMarkdownTable(content: string): ParsedTable | null {
  if (!content) return null

  const lines = content.trim().split('\n').filter(line => line.trim())
  if (lines.length < 2) return null

  const headerLine = lines[0]
  if (!headerLine?.startsWith('|') || !headerLine?.endsWith('|')) return null

  const separatorLine = lines[1]
  if (!separatorLine?.includes('---')) return null

  const headerCells = headerLine
    .slice(1, -1)
    .split('|')
    .map(cell => cell.trim())

  const rows: Array<Array<{ parts: TableCellPart[] }>> = []
  for (const line of lines.slice(2)) {
    if (!line.startsWith('|') || !line.endsWith('|')) continue
    rows.push(
      line
        .slice(1, -1)
        .split('|')
        .map(cell => ({
          parts: parseTableCellContent(cell.trim())
        }))
    )
  }

  return {
    headers: headerCells.map(cell => ({
      parts: parseTableCellContent(cell)
    })),
    rows
  }
}


async function downloadImage(url: string) {
  try {
    const response = await fetch(url)
    const blob = await response.blob()
    const blobUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = 'local-notebook-image.png'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(blobUrl)
  } catch (error) {
  }
}

function getAudioExtension(mimeType?: string): string {
  const mime = (mimeType || '').toLowerCase()
  if (mime.includes('wav')) return 'wav'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mp4') || mime.includes('m4a')) return 'm4a'
  return 'mp3'
}

async function downloadAudio(url: string, mimeType?: string) {
  try {
    const response = await fetch(url)
    if (!response.ok) return
    const blob = await response.blob()
    const blobUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    const baseName = (props.feature.title || props.feature.id || 'audio-overview').replace(/[\\/:*?"<>|]/g, '_')
    link.download = `${baseName}.${getAudioExtension(mimeType || blob.type)}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(blobUrl)
  } catch (error) {
  }
}


function startEditTitle() {
  editingTitleValue.value = props.feature.title || t('ui.toolbox')
  isEditingTitle.value = true
  nextTick(() => {
    titleInputRef.value?.focus()
  })
}

function handleSaveTitle() {
  if (!isEditingTitle.value) return
  
  const newTitle = editingTitleValue.value.trim()
  if (newTitle && newTitle !== props.feature.title) {
    emit('rename', newTitle)
  }
  isEditingTitle.value = false
}

function cancelEditTitle() {
  isEditingTitle.value = false
  editingTitleValue.value = ''
}


function getFeatureStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: t('ui.waiting'),
    processing: t('ui.generating2'),
    completed: t('ui.completed'),
    failed: t('ui.failed')
  }
  return map[status] || status
}


function getFeatureStatusClass(status: string): string {
  const map: Record<string, string> = {
    pending: 'status-pending',
    processing: 'status-processing',
    completed: 'status-completed',
    failed: 'status-failed'
  }
  return map[status] || ''
}

</script>

<style scoped>
.report-waiting-progress {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
  max-width: 420px;
}

.feature-detail-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  background: #fff;
  flex-shrink: 0;
  gap: 8px;
  border-radius: 16px 16px 0 0;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.panel-title.editable {
  cursor: pointer;
  transition: color 0.2s;
}

.panel-title.editable:hover {
  color: #3b82f6;
}

.panel-title-input {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  border: 1px solid #3b82f6;
  border-radius: 4px;
  padding: 4px 8px;
  outline: none;
  background: white;
  width: 100%;
  min-width: 100px;
}


.panel-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: #6b7280;
  transition: all 0.2s;
  margin-left: auto;
}

.panel-toggle-btn:hover {
  background: #f3f4f6;
  color: #111827;
}

.feature-report-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.report-body {
  max-width: 100%;
}


.feature-block {
  transition: background-color 0.3s ease, box-shadow 0.3s ease;
  border-radius: 6px;
  padding: 2px 0;
  margin: -2px 0;
}

.feature-heading {
  color: #111827;
  margin: 0 0 16px 0;
  line-height: 1.4;
}

h1.feature-heading {
  font-size: 24px;
}

h2.feature-heading {
  font-size: 20px;
}

h3.feature-heading {
  font-size: 18px;
}

h4.feature-heading,
h5.feature-heading,
h6.feature-heading {
  font-size: 16px;
}

.feature-rule {
  margin: 20px 0;
  border: none;
  border-top: 1px solid var(--border-color);
}

.feature-paragraph {
  color: #374151;
  font-size: 15px;
  line-height: 1.75;
  margin: 0 0 16px 0;
}

.feature-quote {
  margin: 0 0 16px 0;
  padding: 12px 16px;
  border-left: 4px solid #3b82f6;
  background: #f8fafc;
  color: #4b5563;
  font-style: italic;
}

.feature-list {
  margin: 0 0 16px 0;
  padding-left: 24px;
  color: #374151;
  font-size: 15px;
  line-height: 1.75;
}

.feature-list li {
  margin-bottom: 8px;
}

.feature-table {
  margin: 0 0 16px 0;
  overflow-x: auto;
}

.feature-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.feature-table th,
.feature-table td {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
}

.feature-table th {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
}

.feature-table tbody tr:nth-child(even) {
  background: #f9fafb;
}

.feature-table tbody tr:hover {
  background: #f3f4f6;
}

.feature-table :deep(strong) {
  font-weight: 600;
}

.feature-table :deep(em) {
  font-style: italic;
}

.feature-image {
  margin: 0 0 16px 0;
}

.feature-image .image-wrapper {
  position: relative;
  display: inline-block;
}

.feature-image img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
}

.image-download-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 6px;
  cursor: pointer;
  color: #fff;
  opacity: 0;
  transition: opacity 0.2s;
}

.feature-image .image-wrapper:hover .image-download-btn {
  opacity: 1;
}

.image-download-btn:hover {
  background: rgba(0, 0, 0, 0.7);
}

.feature-image figcaption {
  margin-top: 8px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}

.feature-image-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0 0 16px 0;
}

.feature-image-group .feature-image {
  margin: 0;
  flex: 1;
  min-width: 150px;
  max-width: calc(50% - 6px);
}

.feature-image-group > figcaption {
  width: 100%;
  margin-top: 8px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}

.feature-video {
  margin: 0 0 16px 0;
}

.feature-video video {
  max-width: 100%;
  border-radius: 8px;
}

.feature-video figcaption {
  margin-top: 8px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}

.feature-audio-card {
  margin: 0 0 18px 0;
  padding: 14px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 247, 237, 0.95) 0%, rgba(254, 243, 199, 0.55) 100%);
  border: 1px solid rgba(234, 88, 12, 0.22);
}

.feature-audio-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.feature-audio-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.feature-audio-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: rgba(234, 88, 12, 0.14);
  color: #c2410c;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.feature-audio-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feature-audio-caption {
  font-size: 12px;
  color: #9a3412;
  background: rgba(255, 255, 255, 0.72);
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(234, 88, 12, 0.16);
  white-space: nowrap;
}

.feature-audio-download {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  color: #c2410c;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(234, 88, 12, 0.24);
  cursor: pointer;
  transition: background 0.15s ease;
}

.feature-audio-download:hover {
  background: #ffffff;
}

.feature-audio-element {
  width: 100%;
}

.inline-citation {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 11px;
  font-weight: 500;
  color: #3b82f6;
  background: #eff6ff;
  border-radius: 9px;
  cursor: pointer;
  vertical-align: middle;
  margin-left: 3px;
  position: relative;
  top: -1px;
  transition: all 0.2s;
}

.inline-citation:hover {
  background: #dbeafe;
  color: #2563eb;
}

.inline-citation.active {
  background: #3b82f6;
  color: #fff;
}

.report-error {
  padding: 24px;
  text-align: center;
  color: #ef4444;
}

.report-error p {
  margin: 0;
}

.report-waiting,
.report-empty {
  display: flex;
  min-height: 240px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  color: #6b7280;
  text-align: center;
}

.report-waiting p,
.report-empty p {
  margin: 0;
}

.report-waiting-spinner {
  width: 28px;
  height: 28px;
  border-radius: 9999px;
  background:
    radial-gradient(farthest-side, #2563eb 94%, transparent) top / 4px 4px no-repeat,
    conic-gradient(#2563eb 20%, #dbeafe 0);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 4px), #000 0);
  mask: radial-gradient(farthest-side, transparent calc(100% - 4px), #000 0);
  animation: featureSpinnerRotate 0.8s linear infinite;
}

.feature-text :deep(strong) {
  font-weight: 600;
}

.feature-text :deep(em) {
  font-style: italic;
}

.feature-text :deep(code) {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.9em;
}

@keyframes featureSpinnerRotate {
  to {
    transform: rotate(360deg);
  }
}
</style>

<style scoped>
.feature-status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 9999px;
  white-space: nowrap;
}

.feature-status-badge.status-pending {
  background: var(--bg-hover);
  color: var(--text-tertiary);
}

.feature-status-badge.status-processing {
  background: var(--primary-soft);
  color: var(--primary-color);
  animation: breathing 1.6s ease-in-out infinite;
}

.feature-status-badge.status-processing::after {
  content: '...';
  display: inline-block;
  margin-left: 2px;
  animation: workflowDots 1.2s steps(4, end) infinite;
}

.feature-status-badge.status-completed {
  background: #dcfce7;
  color: #16a34a;
}

.feature-status-badge.status-failed {
  background: var(--error-soft);
  color: var(--error-color);
}

@keyframes breathing {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.25);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(37, 99, 235, 0);
  }
}

@keyframes workflowDots {
  0% { clip-path: inset(0 100% 0 0); }
  33% { clip-path: inset(0 66% 0 0); }
  66% { clip-path: inset(0 33% 0 0); }
  100% { clip-path: inset(0 0 0 0); }
}


.feature-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 44px;
  padding: 4px 12px 4px 16px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

.feature-toolbar-spacer {
  flex: 1;
}

.view-switch {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border-radius: var(--radius-full);
  background: var(--bg-secondary);
}

.view-switch-btn {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 500;
}

.view-switch-btn.active {
  background: var(--bg-white);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
}

.toolbar-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.toolbar-menu-wrap {
  position: relative;
}

.toolbar-menu {
  position: absolute;
  top: calc(100% + 6px);
  inset-inline-end: 0;
  z-index: 30;
  min-width: 210px;
  padding: 6px;
  background: var(--bg-white);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}

.toolbar-menu button {
  display: block;
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  text-align: start;
}

.toolbar-menu button:hover {
  background: var(--bg-hover);
}

.interactive-body {
  min-height: 100%;
}

/* The mind map is a pan-and-zoom canvas that fills the panel. */
.feature-report-content.is-canvas {
  display: flex;
  padding: 0;
  overflow: hidden;
}

.feature-report-content.is-canvas > .interactive-body {
  flex: 1;
  min-height: 0;
}

.feature-status-badge.status-note {
  background: var(--warning-soft);
  color: var(--warning-color);
}
</style>

