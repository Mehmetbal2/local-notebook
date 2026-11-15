import { computed, reactive, ref, type ComputedRef, type Ref } from 'vue'
import type { ImageFile } from '@/components/common/ImageGenerationModal.vue'
import type { VideoFile, VideoGenerationConfig, VideoGenerationMode } from '@/components/common/VideoGenerationModal.vue'
import {
  createNote,
  deleteFeature,
  generateFeature,
  getFeature,
  getFeaturesStatusBatch,
  getProjectFeatures,
  regenerateFeature,
  updateFeature,
  type FeatureListItem,
} from '@/services/api'
import type { Feature, FileInfo, Message } from '@/types'
import {
  IMAGE_GENERATION_FILE_TYPES,
  VIDEO_GENERATION_FILE_TYPES,
} from './fileHelpers'
import { IMAGE_GENERATION_TYPES, TOOL_TYPES, VIDEO_GENERATION_TYPES } from './toolTypes'
import { t } from '@/i18n'

type ToastType = 'success' | 'error' | 'info' | 'warning'
type ToolConfig = typeof TOOL_TYPES[0]

interface UseProjectFeaturesOptions {
  projectId: string
  files: Ref<FileInfo[]>
  readyFiles: ComputedRef<FileInfo[]>
  hasReadyFiles: ComputedRef<boolean>
  rightPanelWidth: Ref<number>
  rightPanelWidthBeforeReport: Ref<number | null>
  reportMinWidth: number
  showToast: (message: string, type?: ToastType, duration?: number) => void
  showConfirm: (options: { title: string; message: string; type?: 'info' | 'warning' | 'danger'; confirmText?: string; cancelText?: string }) => Promise<boolean>
  openRenameModal: (type: 'feature', id: string, name: string) => void
}

/** A 404/405 on an endpoint the UI knows about means the backend is still running older code. */
function isOutdatedServerError(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  return status === 404 || status === 405
}

export function useProjectFeatures({
  projectId,
  files,
  readyFiles,
  hasReadyFiles,
  rightPanelWidth,
  rightPanelWidthBeforeReport,
  reportMinWidth,
  showToast,
  showConfirm,
  openRenameModal,
}: UseProjectFeaturesOptions) {
  const features = ref<FeatureListItem[]>([])
  const activeFeature = ref<Feature | null>(null)
  const showFeatureDetail = ref(false)
  const featureMenuId = ref<string | null>(null)
  const pollingFeatureIds = ref<Set<string>>(new Set())
  let featurePollingTimer: ReturnType<typeof setInterval> | null = null

  const toolConfigModal = reactive({
    visible: false,
    toolType: '',
    toolTitle: '',
    description: '',
    hint: '',
    builtinPrompt: '',
    promptPlaceholder: '',
    prompt: '',
    title: '',
    hidePrompt: false
  })

  const imageGenerationModal = reactive({
    visible: false,
    mode: 'text_to_image' as 'text_to_image' | 'reference_to_image'
  })

  const imageFilesForGeneration = computed<ImageFile[]>(() =>
    files.value
      .filter(f => f.status === 'ready' && IMAGE_GENERATION_FILE_TYPES.includes(f.file_type?.toLowerCase() || ''))
      .map(f => ({
        id: f.id,
        file_name: f.file_name,
        file_type: f.file_type,
        status: f.status
      }))
  )

  const videoGenerationModal = reactive({
    visible: false,
    mode: 'text_to_video' as VideoGenerationMode
  })

  const videoFilesForGeneration = computed<VideoFile[]>(() =>
    files.value
      .filter(f => f.status === 'ready' && VIDEO_GENERATION_FILE_TYPES.includes(f.file_type?.toLowerCase() || ''))
      .map(f => ({
        id: f.id,
        file_name: f.file_name,
        file_type: f.file_type,
        status: f.status
      }))
  )

  const noteEditor = reactive({
    visible: false,
    saving: false,
    /** Id of the manual note being edited; null when creating a new one. */
    featureId: null as string | null,
    title: '',
    content: '',
  })
  const savingNoteMessageIds = ref<Set<string>>(new Set())

  /** Saves a chat answer, with its citations, as a note in the results list. */
  async function saveMessageAsNote(message: Message) {
    if (!message.id || savingNoteMessageIds.value.has(message.id)) return
    // Messages still waiting for their server id carry a numeric timestamp id.
    if (/^\d+$/.test(message.id) || message.pending_id_sync) {
      showToast(t('ui.networkSyncingTryLater'), 'warning')
      return
    }

    savingNoteMessageIds.value.add(message.id)
    try {
      const note = await createNote(projectId, { messageId: message.id })
      features.value.unshift(note)
      showToast(t('ui.savedAsNote'), 'success')
    } catch (error) {
      console.error('Failed to save note:', error)
      showToast(isOutdatedServerError(error) ? t('ui.serverOutdatedRestart') : t('ui.noteSaveFailed'), 'error', 6000)
    } finally {
      savingNoteMessageIds.value.delete(message.id)
    }
  }

  function openNoteEditor() {
    noteEditor.featureId = null
    noteEditor.title = ''
    noteEditor.content = ''
    noteEditor.visible = true
  }

  function openNoteEditorForActiveFeature() {
    const feature = activeFeature.value
    if (!feature || feature.note_source !== 'manual') return
    noteEditor.featureId = feature.id
    noteEditor.title = feature.title || ''
    noteEditor.content = feature.note_markdown || ''
    noteEditor.visible = true
  }

  function closeNoteEditor() {
    noteEditor.visible = false
  }

  async function submitNoteEditor(payload: { title: string; content: string }) {
    noteEditor.saving = true
    try {
      if (noteEditor.featureId) {
        const id = noteEditor.featureId
        await updateFeature(id, { title: payload.title || undefined, content: payload.content })
        const refreshed = await getFeature(id)
        if (activeFeature.value?.id === id) activeFeature.value = refreshed
        const item = features.value.find(f => f.id === id)
        if (item) item.title = refreshed.title
      } else {
        const note = await createNote(projectId, { title: payload.title || undefined, content: payload.content })
        features.value.unshift(note)
      }
      noteEditor.visible = false
      showToast(t('ui.savedSuccessfully'), 'success')
    } catch (error) {
      console.error('Failed to save note:', error)
      showToast(isOutdatedServerError(error) ? t('ui.serverOutdatedRestart') : t('ui.noteSaveFailed'), 'error', 6000)
    } finally {
      noteEditor.saving = false
    }
  }

  /** Runs the open quick tool again in place, keeping its sources and prompt. */
  async function regenerateActiveFeature() {
    const feature = activeFeature.value
    if (!feature) return

    try {
      const updated = await regenerateFeature(feature.id)
      const index = features.value.findIndex(f => f.id === feature.id)
      if (index !== -1) features.value[index] = { ...features.value[index]!, ...updated }
      activeFeature.value = { ...feature, status: 'pending', error_message: null, blocks: [], citations: {} }
      pollingFeatureIds.value.add(feature.id)
      startFeaturePolling()
      showToast(t('ui.regenerateStarted'), 'info')
    } catch (error) {
      console.error('Failed to regenerate feature:', error)
      const status = (error as { response?: { status?: number } })?.response?.status
      // 405 = route missing on an old server; 404 there can also mean the result was deleted.
      showToast(status === 405 ? t('ui.serverOutdatedRestart') : t('ui.regenerateFailed'), 'error', 6000)
    }
  }

  const processingToolTypes = computed(() =>
    features.value
      .filter(f => f.status === 'pending' || f.status === 'processing')
      .map(f => f.feature_type)
  )

  async function loadFeatures() {
    try {
      const { features: featureList } = await getProjectFeatures(projectId)
      features.value = featureList
      featureList
        .filter(f => f.status === 'pending' || f.status === 'processing')
        .forEach(f => pollingFeatureIds.value.add(f.id))
      if (pollingFeatureIds.value.size > 0) {
        startFeaturePolling()
      }
    } catch (error) {
      console.error('Failed to load features:', error)
    }
  }

  function startFeaturePolling() {
    if (featurePollingTimer) return

    featurePollingTimer = setInterval(async () => {
      if (pollingFeatureIds.value.size === 0) {
        stopFeaturePolling()
        return
      }

      try {
        const featureIds = Array.from(pollingFeatureIds.value)
        const result = await getFeaturesStatusBatch(featureIds)

        let hasCompleted = false

        for (const [featureId, statusInfo] of Object.entries(result.features)) {
          const index = features.value.findIndex(f => f.id === featureId)
          if (index !== -1) {
            const existingFeature = features.value[index]!
            features.value[index] = {
              ...existingFeature,
              status: statusInfo.status as FeatureListItem['status'],
              error_message: statusInfo.error_message,
              display_name: statusInfo.display_name ?? existingFeature.display_name,
              prompt: statusInfo.prompt ?? existingFeature.prompt,
              title: statusInfo.title ?? existingFeature.title,
              progress: statusInfo.progress ?? null
            }
          }

          if (activeFeature.value?.id === featureId) {
            activeFeature.value = {
              ...activeFeature.value,
              status: statusInfo.status as Feature['status'],
              error_message: statusInfo.error_message,
              title: statusInfo.title ?? activeFeature.value.title,
              progress: statusInfo.progress ?? null
            }
          }

          if (statusInfo.status === 'completed' || statusInfo.status === 'failed') {
            pollingFeatureIds.value.delete(featureId)
            hasCompleted = true
          }
        }

        if (hasCompleted) {
          const { features: featureList } = await getProjectFeatures(projectId)
          features.value = featureList
          if (activeFeature.value && featureList.some(f => f.id === activeFeature.value?.id)) {
            try {
              activeFeature.value = await getFeature(activeFeature.value.id)
            } catch (error) {
              console.error('Failed to refresh active feature:', error)
            }
          }
        }

        if (pollingFeatureIds.value.size === 0) {
          stopFeaturePolling()
        }
      } catch (error) {
        console.error('Failed to poll features:', error)
      }
    }, 3000)
  }

  function stopFeaturePolling() {
    if (featurePollingTimer) {
      clearInterval(featurePollingTimer)
      featurePollingTimer = null
    }
  }

  function openToolConfig(tool: ToolConfig) {
    if (!hasReadyFiles.value) return

    if (IMAGE_GENERATION_TYPES.includes(tool.type)) {
      imageGenerationModal.mode = tool.type as 'text_to_image' | 'reference_to_image'
      imageGenerationModal.visible = true
      return
    }

    if (VIDEO_GENERATION_TYPES.includes(tool.type)) {
      videoGenerationModal.mode = tool.type as VideoGenerationMode
      videoGenerationModal.visible = true
      return
    }

    toolConfigModal.toolType = tool.type
    toolConfigModal.toolTitle = t(tool.titleKey)
    toolConfigModal.description = tool.descriptionKey ? t(tool.descriptionKey) : t(tool.tooltipKey)
    toolConfigModal.hint = tool.hintKey ? t(tool.hintKey) : ''
    toolConfigModal.builtinPrompt = tool.builtinPromptKey ? t(tool.builtinPromptKey) : ''
    toolConfigModal.promptPlaceholder = tool.promptPlaceholderKey ? t(tool.promptPlaceholderKey) : ''
    toolConfigModal.prompt = ''
    toolConfigModal.title = ''
    toolConfigModal.hidePrompt = false
    toolConfigModal.visible = true
  }

  function closeToolConfig() {
    toolConfigModal.visible = false
    toolConfigModal.toolType = ''
    toolConfigModal.toolTitle = ''
    toolConfigModal.description = ''
    toolConfigModal.hint = ''
    toolConfigModal.builtinPrompt = ''
    toolConfigModal.promptPlaceholder = ''
    toolConfigModal.prompt = ''
    toolConfigModal.title = ''
  }

  async function handleToolConfigConfirm(toolType: string, title: string, prompt: string, fileIds: string[]) {
    closeToolConfig()
    await handleToolClick(toolType, prompt, fileIds, title)
  }

  function closeImageGenerationModal() {
    imageGenerationModal.visible = false
  }

  async function handleImageGenerationConfirm(config: { prompt: string; fileIds: string[]; aspectRatio: string }) {
    const toolType = imageGenerationModal.mode
    closeImageGenerationModal()

    try {
      const { feature_id } = await generateFeature(projectId, toolType, {
        prompt: config.prompt,
        file_ids: config.fileIds,
        aspect_ratio: config.aspectRatio
      })

      const toolConfig = TOOL_TYPES.find(t => t.type === toolType)
      features.value.unshift({
        id: feature_id,
        feature_type: toolType,
        display_name: toolConfig ? t(toolConfig.titleKey) : toolType,
        title: null,
        prompt: config.prompt || null,
        status: 'pending',
        error_message: null,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null
      })

      pollingFeatureIds.value.add(feature_id)
      startFeaturePolling()
    } catch (error) {
      console.error('Failed to generate image:', error)
    }
  }

  function closeVideoGenerationModal() {
    videoGenerationModal.visible = false
  }

  async function handleVideoGenerationConfirm(mode: VideoGenerationMode, config: VideoGenerationConfig) {
    closeVideoGenerationModal()

    try {
      const { feature_id } = await generateFeature(projectId, mode, {
        prompt: config.prompt,
        file_ids: config.fileIds,
        duration: config.duration,
        aspect_ratio: config.aspectRatio,
        resolution: config.resolution,
        bgm: config.bgm
      })

      const toolConfig = TOOL_TYPES.find(t => t.type === mode)
      features.value.unshift({
        id: feature_id,
        feature_type: mode,
        display_name: toolConfig ? t(toolConfig.titleKey) : mode,
        title: null,
        prompt: config.prompt || null,
        status: 'pending',
        error_message: null,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null
      })

      pollingFeatureIds.value.add(feature_id)
      startFeaturePolling()
    } catch (error) {
      console.error('Failed to generate video:', error)
    }
  }

  async function handleToolClick(toolType: string, customPrompt?: string, fileIds?: string[], title?: string) {
    if (!hasReadyFiles.value) return

    try {
      const readyFileIds = fileIds && fileIds.length > 0 ? fileIds : readyFiles.value.map(f => f.id)

      const { feature_id } = await generateFeature(projectId, toolType, {
        prompt: customPrompt || '',
        title: title || undefined,
        file_ids: readyFileIds
      })

      const toolConfig = TOOL_TYPES.find(t => t.type === toolType)
      const displayName = title || (toolConfig ? t(toolConfig.titleKey) : toolType)
      features.value.unshift({
        id: feature_id,
        feature_type: toolType,
        display_name: displayName,
        title: title || null,
        prompt: customPrompt || null,
        status: 'pending',
        error_message: null,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null
      })

      pollingFeatureIds.value.add(feature_id)
      startFeaturePolling()
    } catch (error) {
      console.error('Failed to generate feature:', error)
    }
  }

  /** A deep research started from "Add source": show it and follow its progress. */
  function handleDeepResearchStarted(item: FeatureListItem) {
    if (!features.value.some(f => f.id === item.id)) features.value.unshift(item)
    pollingFeatureIds.value.add(item.id)
    startFeaturePolling()
    showToast(t('ui.deepResearchStartedToast'), 'success', 4000)
  }

  async function handleFeatureClick(featureItem: FeatureListItem) {
    try {
      const feature = await getFeature(featureItem.id)
      activeFeature.value = feature

      if (rightPanelWidth.value < reportMinWidth) {
        rightPanelWidthBeforeReport.value = rightPanelWidth.value
        rightPanelWidth.value = reportMinWidth
      }
      showFeatureDetail.value = true
    } catch (error) {
      console.error('Failed to load feature detail:', error)
    }
  }

  function closeFeatureDetail() {
    showFeatureDetail.value = false
    activeFeature.value = null
    if (rightPanelWidthBeforeReport.value !== null) {
      rightPanelWidth.value = rightPanelWidthBeforeReport.value
      rightPanelWidthBeforeReport.value = null
    }
  }

  async function renameFeatureTitle(id: string, newTitle: string) {
    await updateFeature(id, { title: newTitle })

    const feature = features.value.find(f => f.id === id)
    if (feature) feature.title = newTitle

    if (activeFeature.value?.id === id) {
      activeFeature.value.title = newTitle
    }
  }

  function handleRenameFeature(feature: FeatureListItem) {
    openRenameModal('feature', feature.id, feature.title || '')
  }

  async function handleFeatureDetailRename(newTitle: string) {
    if (!activeFeature.value) return

    try {
      const id = activeFeature.value.id
      await renameFeatureTitle(id, newTitle)

      showToast(t('ui.renameSuccess'), 'success')
    } catch (error) {
      console.error('Failed to rename feature:', error)
      showToast(t('ui.renameFailed'), 'error')
    }
  }

  /** Runs a result again with the sources and prompt it was created with (kept on the server). */
  async function handleRegenerateFeature(featureItem: FeatureListItem) {
    featureMenuId.value = null

    try {
      const updated = await regenerateFeature(featureItem.id)
      const index = features.value.findIndex(f => f.id === featureItem.id)
      if (index !== -1) features.value[index] = { ...features.value[index]!, ...updated }
      pollingFeatureIds.value.add(featureItem.id)
      startFeaturePolling()
    } catch (error) {
      console.error('Failed to regenerate feature:', error)
      showToast(t('ui.regenerateFailed'), 'error')
    }
  }

  async function handleDeleteFeature(featureItem: FeatureListItem) {
    featureMenuId.value = null

    const isNote = featureItem.feature_type === 'note'
    const name = featureItem.title || featureItem.display_name || t(isNote ? 'ui.note' : 'ui.result')
    const confirmed = await showConfirm({
      title: t(isNote ? 'ui.deleteNoteTitle' : 'ui.deleteResultTitle'),
      message: t(isNote ? 'ui.deleteNoteMessage' : 'ui.deleteResultMessage', { name }),
      type: 'danger',
      confirmText: t('ui.delete'),
      cancelText: t('ui.cancel'),
    })
    if (!confirmed) return

    try {
      await deleteFeature(featureItem.id)
      features.value = features.value.filter(f => f.id !== featureItem.id)

      if (activeFeature.value?.id === featureItem.id) {
        closeFeatureDetail()
      }
      showToast(t('ui.itemDeleted', { name }), 'success')
    } catch (error) {
      console.error('Failed to delete feature:', error)
      showToast(t('ui.deleteFailed'), 'error')
    }
  }

  return {
    features,
    activeFeature,
    handleDeepResearchStarted,
    showFeatureDetail,
    featureMenuId,
    pollingFeatureIds,
    processingToolTypes,
    toolConfigModal,
    imageGenerationModal,
    imageFilesForGeneration,
    videoGenerationModal,
    videoFilesForGeneration,
    loadFeatures,
    startFeaturePolling,
    stopFeaturePolling,
    openToolConfig,
    closeToolConfig,
    handleToolConfigConfirm,
    closeImageGenerationModal,
    handleImageGenerationConfirm,
    closeVideoGenerationModal,
    handleVideoGenerationConfirm,
    handleToolClick,
    handleFeatureClick,
    closeFeatureDetail,
    renameFeatureTitle,
    handleRenameFeature,
    handleFeatureDetailRename,
    handleRegenerateFeature,
    handleDeleteFeature,
    noteEditor,
    saveMessageAsNote,
    openNoteEditor,
    openNoteEditorForActiveFeature,
    closeNoteEditor,
    submitNoteEditor,
    regenerateActiveFeature,
  }
}
