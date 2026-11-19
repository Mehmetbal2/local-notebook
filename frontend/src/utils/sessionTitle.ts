import { t } from '../i18n'

// Titles stored for a chat that has not been named yet. Older chats carry the translated
// default of the UI language they were created in. All of them are shown in the current UI
// language and are replaced by a generated title after the first question.
export const PLACEHOLDER_SESSION_TITLES = new Set(['', '新对话', 'New chat', 'Yeni sohbet'])

export function isPlaceholderSessionTitle(title?: string | null): boolean {
  return PLACEHOLDER_SESSION_TITLES.has((title || '').trim())
}

export function displaySessionTitle(title?: string | null): string {
  return isPlaceholderSessionTitle(title) ? t('ui.newChat') : (title as string).trim()
}
