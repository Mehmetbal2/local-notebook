import type { FileInfo } from '../../types'
import { t } from '../../i18n'
import {
  AUDIO_FILE_EXTENSIONS,
  DOCUMENT_FILE_EXTENSIONS,
  IMAGE_FILE_EXTENSIONS,
} from '../../constants/fileTypes'

export const IMAGE_TYPES: string[] = [...IMAGE_FILE_EXTENSIONS]
export const AUDIO_TYPES: string[] = [...AUDIO_FILE_EXTENSIONS]
export const IMAGE_GENERATION_FILE_TYPES: string[] = [...IMAGE_TYPES, 'webp']
export const VIDEO_GENERATION_FILE_TYPES: string[] = [...IMAGE_TYPES]

export const MAX_FILE_COUNT = 30

const FILE_SIZE_LIMITS = {
  document: 100 * 1024 * 1024,
  image: 20 * 1024 * 1024,
  audio: 200 * 1024 * 1024,
} as const

export function isImageFile(file: FileInfo): boolean {
  return IMAGE_TYPES.includes(file.file_type?.toLowerCase() || '')
}

export function isAudioFile(file: FileInfo): boolean {
  return AUDIO_TYPES.includes(file.file_type?.toLowerCase() || '')
}

function getFileSizeLimit(file: File): number {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''

  if ((DOCUMENT_FILE_EXTENSIONS as readonly string[]).includes(ext)) {
    return FILE_SIZE_LIMITS.document
  }
  if (IMAGE_TYPES.includes(ext)) {
    return FILE_SIZE_LIMITS.image
  }
  if (AUDIO_TYPES.includes(ext)) {
    return FILE_SIZE_LIMITS.audio
  }
  return FILE_SIZE_LIMITS.document
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

export function checkFileSize(file: File): { valid: boolean; error?: string } {
  const limit = getFileSizeLimit(file)

  if (file.size > limit) {
    return {
      valid: false,
      error: t('ui.fileSizeExceeded', { name: file.name, limit: formatFileSize(limit) })
    }
  }
  return { valid: true }
}

// "Author - Year - Title", the year may be a range (1408/1988) or a no-date mark (t.y. / n.d.).
// The author part may contain hyphens (Ebü'l-Hasan, Jean-Paul); only a spaced dash
// separates the fields, so a hyphen inside a name is not treated as a separator.
const BIBLIOGRAPHIC_NAME = /^\s*.+?\s+[-–]\s+(?:\d{3,4}(?:\s*\/\s*\d{3,4})?|t\.\s?y\.|n\.\s?d\.|无日期)\s+[-–]\s+\S.*$/i

/** Whether a source's file name already reads "Author - Year - Title" (extension ignored). */
export function isBibliographicName(fileName: string): boolean {
  const base = fileName.replace(/\.[A-Za-z0-9]{1,6}$/, '')
  return BIBLIOGRAPHIC_NAME.test(base)
}

export function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    pending: t('ui.pending'),
    processing: t('ui.processing'),
    ready: t('ui.ready'),
    error: t('ui.error'),
    failed: t('ui.parsingFailed'),
    cancelled: t('ui.processingStopped')
  }
  return statusMap[status] || status
}
