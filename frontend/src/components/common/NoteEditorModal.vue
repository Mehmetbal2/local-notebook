<template>
  <Teleport to="body">
    <div v-if="visible" class="note-editor-overlay modal-overlay" @click.self="handleClose">
      <form class="note-editor" role="dialog" aria-modal="true" @submit.prevent="handleSubmit">
        <header class="note-editor-header">
          <h3>{{ isEditing ? $t('ui.editNote') : $t('ui.newNote') }}</h3>
          <button class="icon-btn" type="button" :title="$t('ui.close')" :aria-label="$t('ui.close')" @click="handleClose">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" />
            </svg>
          </button>
        </header>

        <input
          v-model="title"
          class="note-editor-title"
          type="text"
          maxlength="120"
          :placeholder="$t('ui.noteTitlePlaceholder')"
          :aria-label="$t('ui.noteTitlePlaceholder')"
        />
        <textarea
          ref="contentRef"
          v-model="content"
          class="note-editor-content"
          dir="auto"
          :placeholder="$t('ui.noteContentPlaceholder')"
          :aria-label="$t('ui.note')"
          @keydown.meta.enter.prevent="handleSubmit"
          @keydown.ctrl.enter.prevent="handleSubmit"
        ></textarea>

        <div v-if="confirmingDiscard" class="note-editor-discard" role="alert">
          <span>{{ $t('ui.unsavedChangesPrompt') }}</span>
          <div class="note-editor-discard-actions">
            <button ref="keepEditingRef" class="btn btn-text" type="button" @click="confirmingDiscard = false">{{ $t('ui.keepEditing') }}</button>
            <button class="btn btn-tonal danger" type="button" @click="discardAndClose">{{ $t('ui.discardChanges') }}</button>
          </div>
        </div>

        <footer v-else class="note-editor-actions">
          <button class="btn btn-text" type="button" @click="handleClose">{{ $t('ui.cancel') }}</button>
          <button class="btn btn-filled" type="submit" :disabled="!content.trim() || saving">
            {{ saving ? $t('ui.saving') : $t('ui.save') }}
          </button>
        </footer>
      </form>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useEscapeClose } from '../../composables/useEscapeClose'

const props = defineProps<{
  visible: boolean
  isEditing?: boolean
  initialTitle?: string
  initialContent?: string
  saving?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'submit', payload: { title: string; content: string }): void
}>()

const title = ref('')
const content = ref('')
const contentRef = ref<HTMLTextAreaElement | null>(null)
const keepEditingRef = ref<HTMLButtonElement | null>(null)
const confirmingDiscard = ref(false)

const isDirty = computed(() =>
  title.value.trim() !== (props.initialTitle || '').trim() ||
  content.value.trim() !== (props.initialContent || '').trim()
)

// Closing with unsaved changes asks first instead of silently throwing the text away.
function handleClose() {
  if (props.saving) return
  if (confirmingDiscard.value) {
    confirmingDiscard.value = false
    return
  }
  if (isDirty.value) {
    confirmingDiscard.value = true
    nextTick(() => keepEditingRef.value?.focus())
    return
  }
  emit('close')
}

function discardAndClose() {
  confirmingDiscard.value = false
  emit('close')
}

function handleSubmit() {
  const text = content.value.trim()
  if (!text || props.saving) return
  emit('submit', { title: title.value.trim(), content: text })
}

watch(
  () => props.visible,
  (visible) => {
    if (!visible) return
    title.value = props.initialTitle || ''
    content.value = props.initialContent || ''
    confirmingDiscard.value = false
    nextTick(() => contentRef.value?.focus())
  },
)

useEscapeClose(() => props.visible, handleClose)
</script>

<style scoped>
.note-editor-discard {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--warning-soft, #fef7e0);
  color: var(--text-primary);
  font-size: 13.5px;
}

.note-editor-discard-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.note-editor-discard .danger {
  color: var(--error-color);
  background: var(--error-soft);
}

.note-editor-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.note-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  max-width: 640px;
  max-height: min(720px, 100%);
  padding: 20px 24px 24px;
  background: var(--bg-white);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
}

.note-editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.note-editor-header h3 {
  font-size: 20px;
  font-weight: 500;
}

.note-editor-title {
  height: 44px;
  padding: 0 14px;
  font-size: 15px;
  font-weight: 500;
  border-color: var(--border-strong);
  border-radius: var(--radius-md);
}

.note-editor-content {
  flex: 1;
  min-height: 280px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  border-color: var(--border-strong);
  border-radius: var(--radius-md);
}

.note-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
