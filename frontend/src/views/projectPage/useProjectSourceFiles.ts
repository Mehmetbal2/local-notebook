import { computed, ref, watch } from 'vue'
import { getModelOutputLanguage, locale, t } from '@/i18n'
import {
  cancelFilesProcessing,
  deleteFile,
  deleteFilesBatch,
  getFiles,
  getFilesStatusBatch,
  reprocessFile,
  updateFile,
  uploadFile,
} from '@/services/api'
import type { FileInfo } from '@/types'
import type { WebSourceImportResponse } from '@/services/api'
import type { UploadingFile } from '@/components/project/source/types'
import { checkFileSize, isBibliographicName, isImageFile, MAX_FILE_COUNT } from './fileHelpers'

type ToastType = 'success' | 'error' | 'info' | 'warning'

interface ConfirmOptions {
  title: string
  message: string
  type?: 'info' | 'warning' | 'danger'
  confirmText?: string
  cancelText?: string
}

interface UseProjectSourceFilesOptions {
  projectId: string
  showToast: (message: string, type?: ToastType, duration?: number) => void
  showConfirm: (options: ConfirmOptions) => Promise<boolean>
  onFileDeleted?: (fileId: string) => void
}

export function useProjectSourceFiles({
  projectId,
  showToast,
  showConfirm,
  onFileDeleted,
}: UseProjectSourceFilesOptions) {
  const files = ref<FileInfo[]>([])
  const selectedFileIds = ref<string[]>([])
  const hoveringFileId = ref<string | null>(null)
  const pollingFileIds = ref<Set<string>>(new Set())
  const openMenuFileId = ref<string | null>(null)
  const showUploadModal = ref(false)
  const isUploading = ref(false)
  const uploadingFiles = ref<UploadingFile[]>([])
  let filePollingTimer: ReturnType<typeof setInterval> | null = null

  const sortedFiles = computed(() => {
    return [...files.value].sort((a, b) => {
      const aIsImage = isImageFile(a)
      const bIsImage = isImageFile(b)
      if (aIsImage === bIsImage) return 0
      return aIsImage ? 1 : -1
    })
  })

  const readyFiles = computed(() => files.value.filter(f => f.status === 'ready'))
  const hasReadyFiles = computed(() => readyFiles.value.length > 0)
  const isAllSelected = computed(() =>
    readyFiles.value.length > 0 && selectedFileIds.value.length === readyFiles.value.length
  )

  watch(readyFiles, (newReadyFiles, oldReadyFiles) => {
    const oldIds = new Set((oldReadyFiles || []).map(f => f.id))
    const currentSelected = new Set(selectedFileIds.value)

    newReadyFiles.forEach(file => {
      if (!oldIds.has(file.id)) {
        currentSelected.add(file.id)
      }
    })

    const newIds = new Set(newReadyFiles.map(f => f.id))
    selectedFileIds.value = Array.from(currentSelected).filter(id => newIds.has(id))
  }, { immediate: true })

  async function loadFiles() {
    try {
      files.value = await getFiles(projectId)

      for (const file of files.value) {
        if (file.status === 'processing' || file.status === 'pending') {
          pollFileStatus(file.id)
        }
      }
    } catch (error) {
      console.error('Failed to load files:', error)
    }
  }

  function toggleFileSelection(fileId: string, event?: Event) {
    event?.stopPropagation()
    const index = selectedFileIds.value.indexOf(fileId)
    if (index === -1) {
      selectedFileIds.value.push(fileId)
    } else {
      selectedFileIds.value.splice(index, 1)
    }
  }

  /** Select the given sources: add them to the selection, or select only them. */
  function setFileSelection(fileIds: string[], mode: 'add' | 'only') {
    const ready = new Set(readyFiles.value.map(f => f.id))
    const ids = fileIds.filter(id => ready.has(id))
    selectedFileIds.value = mode === 'only'
      ? ids
      : Array.from(new Set([...selectedFileIds.value, ...ids]))
  }

  function toggleSelectAll() {
    if (selectedFileIds.value.length === readyFiles.value.length) {
      selectedFileIds.value = []
    } else {
      selectedFileIds.value = readyFiles.value.map(f => f.id)
    }
  }

  function triggerFileUpload() {
    showUploadModal.value = true
  }

  async function handleUploadFiles(fileList: File[]) {
    const remainingCount = MAX_FILE_COUNT - files.value.length
    if (remainingCount <= 0) {
      showToast(t('ui.fileLimitReachedWithCount', { count: MAX_FILE_COUNT }), 'error')
      return
    }

    const filesToUpload = fileList.slice(0, remainingCount)
    const validFiles: File[] = []
    const sizeErrors: string[] = []
    const typeErrors: string[] = []

    for (const file of filesToUpload) {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      if (ext === 'doc') {
        typeErrors.push(t('ui.unsupportedLegacyDocFile', { name: file.name }))
        continue
      }

      const check = checkFileSize(file)
      if (check.valid) {
        validFiles.push(file)
      } else {
        sizeErrors.push(check.error!)
      }
    }

    const errors = [...typeErrors, ...sizeErrors]
    if (errors.length > 0) {
      showToast(errors.join('\n'), 'error', 5000)
      if (validFiles.length === 0) return
    }

    isUploading.value = true
    uploadingFiles.value = validFiles.map(f => ({
      name: f.name,
      progress: 0,
      status: 'uploading' as const
    }))

    let successCount = 0
    let failedCount = 0

    for (let i = 0; i < validFiles.length; i++) {
      const file = validFiles[i]!
      const uploadItem = uploadingFiles.value[i]!
      try {
        const uploaded = await uploadFile(
          projectId,
          file,
          (progress) => {
            uploadItem.progress = progress
          },
          getModelOutputLanguage()
        )
        files.value.push(uploaded)
        uploadItem.status = 'success'
        uploadItem.progress = 100
        successCount++

        if (uploaded.status !== 'ready' && uploaded.status !== 'failed') {
          pollFileStatus(uploaded.id)
        }
      } catch (error: any) {
        console.error('Failed to upload file:', error)
        const errorMsg = error?.response?.data?.error || error?.response?.data?.detail || error?.message || t('ui.uploadFailed')
        uploadItem.status = 'error'
        uploadItem.error = errorMsg
        failedCount++
      }
    }

    isUploading.value = false

    if (failedCount > 0 && successCount > 0) {
      showToast(t('ui.uploadMixedResult', { success: successCount, failed: failedCount }), 'info', 4000)
    } else if (failedCount > 0) {
      showToast(t('ui.filesUploadFailed', { count: failedCount }), 'error', 4000)
    } else if (successCount > 0) {
      showToast(t('ui.filesUploadSucceeded', { count: successCount }), 'success', 3000)
    }

    setTimeout(() => {
      uploadingFiles.value = []
    }, 3000)
  }

  async function handleInsertText(content: string) {
    if (files.value.length >= MAX_FILE_COUNT) {
      showToast(t('ui.fileLimitReachedWithCount', { count: MAX_FILE_COUNT }), 'error')
      return
    }

    const fileName = `${t('ui.pastedTextFileNamePrefix')}_${new Date().toLocaleString(locale.value, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(/[\/\s:]/g, '')}.txt`
    const blob = new Blob([content], { type: 'text/plain' })
    const file = new File([blob], fileName, { type: 'text/plain' })

    isUploading.value = true
    try {
      const uploaded = await uploadFile(projectId, file, undefined, getModelOutputLanguage())
      files.value.push(uploaded)

      if (uploaded.status !== 'ready' && uploaded.status !== 'failed') {
        pollFileStatus(uploaded.id)
      }
    } catch (error: any) {
      console.error('Failed to upload pasted text:', error)
      const msg = error?.response?.data?.error || error?.response?.data?.detail || error?.message || t('ui.uploadFailed')
      showToast(msg, 'error', 4000)
    } finally {
      isUploading.value = false
    }
  }

  function pollFileStatus(fileId: string) {
    pollingFileIds.value.add(fileId)
    startFilePolling()
  }

  function startFilePolling() {
    if (filePollingTimer) return

    filePollingTimer = setInterval(async () => {
      if (pollingFileIds.value.size === 0) {
        stopFilePolling()
        return
      }

      try {
        const fileIds = Array.from(pollingFileIds.value)
        const result = await getFilesStatusBatch(fileIds)

        for (const fileStatus of result.files) {
          const index = files.value.findIndex(f => f.id === fileStatus.id)
          if (index !== -1) {
            const existingFile = files.value[index]!
            files.value[index] = {
              ...existingFile,
              status: fileStatus.status as FileInfo['status'],
              error_message: fileStatus.error_message ?? undefined,
              processing_current: fileStatus.processing_current ?? null,
              processing_total: fileStatus.processing_total ?? null,
              processing_message: fileStatus.processing_message ?? null
            }
          }

          if (fileStatus.status === 'ready' || fileStatus.status === 'failed' || fileStatus.status === 'cancelled') {
            pollingFileIds.value.delete(fileStatus.id)
          }
        }

        if (pollingFileIds.value.size === 0) {
          stopFilePolling()
        }
      } catch (error) {
        console.error('Failed to poll file status:', error)
      }
    }, 2000)
  }

  function stopFilePolling() {
    if (filePollingTimer) {
      clearInterval(filePollingTimer)
      filePollingTimer = null
    }
  }

  async function handleDeleteFile(fileId: string) {
    const file = files.value.find(f => f.id === fileId)
    const fileName = file?.file_name || t('ui.thisFile')

    openMenuFileId.value = null

    const confirmed = await showConfirm({
      title: t('ui.deleteFile'),
      message: t('ui.deleteFileMessage', { name: fileName }),
      type: 'danger',
      confirmText: t('ui.delete'),
      cancelText: t('ui.cancel')
    })
    if (!confirmed) return

    try {
      await deleteFile(fileId)
      files.value = files.value.filter((f) => f.id !== fileId)
      pollingFileIds.value.delete(fileId)
      onFileDeleted?.(fileId)
      showToast(t('ui.itemDeleted', { name: fileName }), 'success')
    } catch (error) {
      console.error('Failed to delete file:', error)
      showToast(t('ui.deleteFilesFailed'), 'error')
    }
  }

  async function handleCancelFiles(fileIds: string[]) {
    openMenuFileId.value = null
    const active = fileIds.filter(id => {
      const status = files.value.find(f => f.id === id)?.status
      return status === 'pending' || status === 'processing'
    })
    if (active.length === 0) return

    const firstName = files.value.find(f => f.id === active[0])?.file_name || t('ui.thisFile')
    const confirmed = await showConfirm({
      title: t('ui.stopProcessingTitle', { count: active.length }),
      message: active.length === 1
        ? t('ui.stopProcessingMessage', { name: firstName })
        : t('ui.stopProcessingMessageMany', { count: active.length }),
      type: 'warning',
      confirmText: t('ui.stopProcessing'),
      cancelText: t('ui.cancel'),
    })
    if (!confirmed) return

    try {
      const { stopped } = await cancelFilesProcessing(active)
      for (const id of stopped) {
        const index = files.value.findIndex(f => f.id === id)
        if (index !== -1) {
          files.value[index] = {
            ...files.value[index]!,
            status: 'cancelled',
            error_message: undefined,
            processing_message: null,
          }
        }
        pollingFileIds.value.delete(id)
      }
      if (stopped.length > 0) {
        showToast(
          stopped.length === 1 ? t('ui.fileProcessingStopped') : t('ui.filesProcessingStopped', { count: stopped.length }),
          'success',
        )
      }
    } catch (error) {
      console.error('Failed to stop file processing:', error)
      showToast(t('ui.stopProcessingFailed'), 'error')
    }
  }

  async function handleDeleteFiles(fileIds: string[]): Promise<boolean> {
    openMenuFileId.value = null
    const ids = fileIds.filter(id => files.value.some(f => f.id === id))
    if (ids.length === 0) return false
    if (ids.length === 1) {
      await handleDeleteFile(ids[0]!)
      return !files.value.some(f => f.id === ids[0])
    }

    const activeCount = files.value.filter(f => ids.includes(f.id) && (f.status === 'pending' || f.status === 'processing')).length
    const confirmed = await showConfirm({
      title: t('ui.deleteFilesTitle', { count: ids.length }),
      message: activeCount > 0
        ? t('ui.deleteFilesMessageWithActive', { count: ids.length, active: activeCount })
        : t('ui.deleteFilesMessage', { count: ids.length }),
      type: 'danger',
      confirmText: t('ui.delete'),
      cancelText: t('ui.cancel'),
    })
    if (!confirmed) return false

    try {
      const { deleted } = await deleteFilesBatch(ids)
      const deletedSet = new Set(deleted)
      files.value = files.value.filter(f => !deletedSet.has(f.id))
      for (const id of deleted) {
        pollingFileIds.value.delete(id)
        onFileDeleted?.(id)
      }
      showToast(t('ui.filesDeleted', { count: deleted.length }), 'success')
      return true
    } catch (error) {
      console.error('Failed to delete files:', error)
      showToast(t('ui.deleteFilesFailed'), 'error')
      return false
    }
  }

  /** Re-embed ready files from stored segments, or start parsing stopped/failed files again. */
  async function handleReprocessFiles(fileIds: string[]) {
    openMenuFileId.value = null
    const ids = fileIds.filter(id => {
      const status = files.value.find(f => f.id === id)?.status
      return status === 'cancelled' || status === 'failed' || status === 'ready'
    })
    if (ids.length === 0) return

    let started = 0
    let lastError = ''
    let shouldRefresh = false
    for (const fileId of ids) {
      try {
        const updated = await reprocessFile(fileId, getModelOutputLanguage())
        const index = files.value.findIndex(f => f.id === fileId)
        if (index !== -1) files.value[index] = { ...files.value[index]!, ...updated }
        pollFileStatus(fileId)
        started++
      } catch (error: any) {
        console.error('Failed to reprocess file:', error)
        if (error?.response?.status === 409) {
          shouldRefresh = true
        }
        const msg = error?.response?.data?.detail
        lastError = typeof msg === 'string' ? msg : t('ui.reprocessFailed')
      }
    }
    if (shouldRefresh) {
      await loadFiles()
    }
    if (started > 0) {
      showToast(started === 1 ? t('ui.fileProcessingRestarted') : t('ui.filesProcessingRestarted', { count: started }), 'success')
    }
    if (lastError) showToast(lastError, 'error')
  }

  // ---- "Author - Year - Title" naming suggestions (the user always confirms) ----
  const namingDismissedKey = `ln.sourceNamingDismissed.${projectId}`
  const namingDismissed = ref<Set<string>>(new Set(readDismissed()))
  const namingDialog = ref<{ visible: boolean; fileIds: string[]; saving: boolean }>({ visible: false, fileIds: [], saving: false })

  function readDismissed(): string[] {
    try {
      const raw = JSON.parse(localStorage.getItem(namingDismissedKey) || '[]')
      return Array.isArray(raw) ? raw.filter((id): id is string => typeof id === 'string') : []
    } catch {
      return []
    }
  }

  function persistDismissed() {
    try {
      localStorage.setItem(namingDismissedKey, JSON.stringify([...namingDismissed.value]))
    } catch {
      // storage unavailable: the reminder simply comes back next time
    }
  }

  /** Ready sources whose names are not "Author - Year - Title" and that the user has not dismissed. */
  const filesNeedingNames = computed(() =>
    files.value.filter(f => f.status === 'ready' && !isBibliographicName(f.file_name) && !namingDismissed.value.has(f.id))
  )
  const namingDialogFiles = computed(() =>
    namingDialog.value.fileIds.map(id => files.value.find(f => f.id === id)).filter((f): f is FileInfo => !!f)
  )

  function openNamingDialog(fileIds: string[]) {
    openMenuFileId.value = null
    const ids = fileIds.filter(id => files.value.some(f => f.id === id && f.status === 'ready'))
    if (ids.length === 0) return
    namingDialog.value = { visible: true, fileIds: ids, saving: false }
  }

  function closeNamingDialog() {
    namingDialog.value.visible = false
  }

  function dismissNamingReminder(fileIds: string[]) {
    const next = new Set(namingDismissed.value)
    fileIds.forEach(id => next.add(id))
    namingDismissed.value = next
    persistDismissed()
  }

  async function confirmSourceNames(renames: { id: string; fileName: string }[]) {
    if (renames.length === 0) return
    namingDialog.value.saving = true
    let renamed = 0
    for (const { id, fileName } of renames) {
      try {
        await renameFile(id, fileName)
        renamed++
      } catch (error) {
        console.error('Failed to rename source:', error)
      }
    }
    namingDialog.value.saving = false
    // Whatever the user decided in the dialog, do not remind again about these files.
    dismissNamingReminder(namingDialog.value.fileIds)
    namingDialog.value.visible = false
    if (renamed > 0) showToast(t('ui.sourcesRenamed', { count: renamed }), 'success')
    if (renamed < renames.length) showToast(t('ui.renameFailed'), 'error')
  }

  async function renameFile(fileId: string, newName: string) {
    await updateFile(fileId, { file_name: newName })
    const file = files.value.find(f => f.id === fileId)
    if (file) file.file_name = newName
  }

  function toggleFileMenu(fileId: string) {
    if (openMenuFileId.value === fileId) {
      openMenuFileId.value = null
    } else {
      openMenuFileId.value = fileId
    }
  }

  /** Files added from "Search the web": show them and follow their processing. */
  function handleWebImported(result: WebSourceImportResponse) {
    for (const file of result.imported) {
      if (!files.value.some(f => f.id === file.id)) files.value.push(file)
      if (file.status !== 'ready' && file.status !== 'failed') pollFileStatus(file.id)
    }
    if (result.imported.length) {
      showToast(t('ui.webSourcesImportedToast', { count: result.imported.length }), 'success', 3000)
    }
    if (result.failed.length) {
      showToast(t('ui.webSourcesImportFailedToast', { count: result.failed.length }), 'error', 5000)
    } else if (result.abstract_only?.length) {
      showToast(t('ui.webSourcesAbstractOnlyToast', { count: result.abstract_only.length }), 'info', 5000)
    }
  }

  function handleClickOutside(event: MouseEvent) {
    const target = event.target as HTMLElement
    if (!target.closest('.source-menu-wrapper')) {
      openMenuFileId.value = null
    }
  }

  return {
    files,
    sortedFiles,
    readyFiles,
    hasReadyFiles,
    selectedFileIds,
    hoveringFileId,
    pollingFileIds,
    openMenuFileId,
    showUploadModal,
    isUploading,
    uploadingFiles,
    isAllSelected,
    maxFileCount: MAX_FILE_COUNT,
    loadFiles,
    toggleFileSelection,
    toggleSelectAll,
    setFileSelection,
    triggerFileUpload,
    handleUploadFiles,
    handleInsertText,
    handleWebImported,
    pollFileStatus,
    startFilePolling,
    stopFilePolling,
    handleDeleteFile,
    handleCancelFiles,
    handleDeleteFiles,
    handleReprocessFiles,
    filesNeedingNames,
    namingDialog,
    namingDialogFiles,
    openNamingDialog,
    closeNamingDialog,
    dismissNamingReminder,
    confirmSourceNames,
    renameFile,
    toggleFileMenu,
    handleClickOutside,
  }
}
