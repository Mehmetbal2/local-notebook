<template>
  <div ref="inputWrapperRef" class="chat-input-wrapper" :class="{ 'disabled-by-selection': isExportSelectionMode }">
    <div class="chat-input-box">
      <div class="input-main-row">
        <textarea
          ref="textareaRef"
          :value="inputMessage"
          :placeholder="generalChat ? $t('ui.generalChatPlaceholder') : $t('ui.whatWouldYouLikeToAsk')"
          :disabled="!hasCurrentSession || isStreaming"
          rows="1"
          @input="handleInput"
          @keydown.enter.exact.prevent="emit('send-enter')"
          @compositionstart="emit('composition-start')"
          @compositionend="emit('composition-end')"
        ></textarea>
        <div v-if="dictation.supported" class="dictation" :class="dictation.state.value">
          <template v-if="dictation.state.value === 'recording'">
            <span class="dictation-timer" aria-live="off">
              <span class="dictation-dot" aria-hidden="true"></span>{{ formatElapsed(dictation.elapsed.value) }}
            </span>
            <button type="button" class="dictation-btn" :title="$t('ui.dictationCancel')" :aria-label="$t('ui.dictationCancel')" @click="dictation.cancel()">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </button>
            <button type="button" class="dictation-btn dictation-stop" :title="$t('ui.dictationStop')" :aria-label="$t('ui.dictationStop')" @click="dictation.stop()">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
            </button>
          </template>
          <span v-else-if="dictation.state.value === 'transcribing'" class="dictation-busy" role="status">
            <span class="dictation-spinner" aria-hidden="true"></span>{{ $t('ui.dictationTranscribing') }}
          </span>
          <button
            v-else
            type="button"
            class="dictation-btn"
            :disabled="!hasCurrentSession || isStreaming"
            :title="$t('ui.dictationStart')"
            :aria-label="$t('ui.dictationStart')"
            @click="dictation.start()"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>
          </button>
        </div>
        <button
          v-if="!isStreaming"
          class="send-btn"
          :disabled="!inputMessage.trim() || !hasCurrentSession"
          :title="$t('ui.send')"
          @click="emit('send-message')"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
        <button
          v-else
          class="send-btn"
          :title="$t('ui.stop')"
          @click="emit('stop-streaming')"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M6 5h4v14H6zm8 0h4v14h-4z" />
          </svg>
        </button>
      </div>
      <div class="input-options-row">
        <div
          class="web-search-tool"
          :class="{ active: webSearchConfigured }"
          :aria-label="webSearchConfigured ? $t('ui.webSearchEnabledAutoHint') : $t('ui.webSearchDisabledAdminHint')"
          :data-tooltip="webSearchConfigured ? $t('ui.webSearchEnabledAutoHint') : $t('ui.webSearchDisabledAdminHint')"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
          <span>{{ $t('ui.webSearch') }}</span>
        </div>

        <span
          v-if="generalChat"
          class="general-chat-chip"
          :data-tooltip="$t('ui.generalChatBadgeTooltip')"
          :aria-label="$t('ui.generalChatBadgeTooltip')"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
            <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
          </svg>
          {{ $t('ui.generalChatBadge') }}
        </span>
        <span v-else class="source-count">{{ $t('ui.sourceCount', { count: sourceCount }) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { t } from '@/i18n'
import { useVoiceDictation } from '@/composables/useVoiceDictation'

interface Props {
  inputMessage: string
  webSearchConfigured: boolean
  sourceCount: number
  /** No sources selected: questions go to general chat. */
  generalChat: boolean
  hasReadyFiles: boolean
  hasCurrentSession: boolean
  isStreaming: boolean
  isExportSelectionMode: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:inputMessage': [value: string]
  'send-enter': []
  'composition-start': []
  'composition-end': []
  'auto-resize': []
  'send-message': []
  'stop-streaming': []
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const inputWrapperRef = ref<HTMLDivElement | null>(null)

defineExpose({
  get textareaElement() {
    return textareaRef.value
  },
  get inputWrapperElement() {
    return inputWrapperRef.value
  }
})

// ---- Dictation: speak, and the transcript is inserted where the cursor is ----
const dictation = useVoiceDictation({
  onText: insertDictatedText,
  onError: (message) => window.dispatchEvent(new CustomEvent('global-toast', { detail: { message, type: 'warning' } })),
  messages: {
    permission: t('ui.dictationNoMicrophone'),
    failed: t('ui.dictationFailed'),
    empty: t('ui.dictationNothingHeard'),
  },
})

function insertDictatedText(text: string) {
  const textarea = textareaRef.value
  const current = props.inputMessage || ''
  const start = textarea ? textarea.selectionStart ?? current.length : current.length
  const end = textarea ? textarea.selectionEnd ?? current.length : current.length
  const before = current.slice(0, start)
  const after = current.slice(end)
  const spacerBefore = before && !/\s$/.test(before) ? ' ' : ''
  const spacerAfter = after && !/^\s/.test(after) ? ' ' : ''
  const next = `${before}${spacerBefore}${text}${spacerAfter}${after}`
  emit('update:inputMessage', next)
  emit('auto-resize')
  const caret = (before + spacerBefore + text).length
  requestAnimationFrame(() => {
    textarea?.focus()
    textarea?.setSelectionRange(caret, caret)
  })
}

function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && dictation.state.value === 'recording') {
    event.stopPropagation()
    dictation.cancel()
  }
}
onMounted(() => document.addEventListener('keydown', onKeydown, true))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown, true))

function handleInput(event: Event) {
  emit('update:inputMessage', (event.target as HTMLTextAreaElement).value)
  emit('auto-resize')
}
</script>

<style scoped>
.chat-input-wrapper {
  padding: 8px 20px 16px;
  position: relative;
}

.chat-input-wrapper.disabled-by-selection {
  opacity: 0.5;
  pointer-events: none;
}

.chat-input-box {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 860px;
  margin: 0 auto;
  padding: 12px 12px 10px 18px;
  background: var(--bg-white);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  transition: border-color 0.15s, box-shadow 0.2s;
}

.chat-input-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: var(--shadow-md), var(--focus-ring);
}

.input-main-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.input-main-row textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  background: transparent;
  max-height: 150px;
  overflow-y: auto;
}

.dictation {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.dictation-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.dictation-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dictation-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.dictation-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.dictation-stop {
  background: var(--primary-color);
  color: #fff;
}

.dictation-stop:hover:not(:disabled) {
  background: var(--primary-hover, var(--primary-color));
  color: #fff;
}

.dictation-timer {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 6px;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--error-color);
}

.dictation-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--error-color);
  animation: dictation-pulse 1.2s ease-in-out infinite;
}

.dictation-busy {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px;
  font-size: 12.5px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.dictation-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: dictation-spin 0.8s linear infinite;
}

@keyframes dictation-pulse {
  50% {
    opacity: 0.25;
  }
}

@keyframes dictation-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .dictation-dot,
  .dictation-spinner {
    animation: none;
  }
}

.input-main-row textarea:focus {
  box-shadow: none;
}

.input-options-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  margin-top: 4px;
}

.general-chat-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  background: var(--warning-soft);
  color: var(--warning-color);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  cursor: default;
}

.source-count {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.send-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-color);
  color: white;
  border-radius: 50%;
}

.send-btn:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: scale(1.05);
}

.send-btn:disabled {
  background: var(--bg-tertiary);
  color: var(--text-disabled);
  opacity: 1;
  border-radius: 50%;
}

.web-search-tool {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  font-size: 12px;
  background: var(--bg-hover);
  color: var(--text-tertiary);
  cursor: default;
  border-radius: 12px;
  transition: all 0.2s;
  user-select: none;
  position: relative;
}

.web-search-tool.active {
  background: var(--primary-light);
  color: var(--primary-color);
}

.web-search-tool svg {
  flex-shrink: 0;
}

</style>
