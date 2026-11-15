import { locale } from '../i18n'

/** Header that tells the server which interface language to answer in. */
export const UI_LANGUAGE_HEADER = 'X-UI-Language'

export function currentUiLanguage(): string {
  return locale.value
}

function isApiRequest(url: string): boolean {
  const apiBase = import.meta.env.VITE_API_BASE || ''
  try {
    const parsed = new URL(url, window.location.href)
    if (!parsed.pathname.includes('/api/')) return false
    return parsed.origin === window.location.origin || (apiBase !== '' && url.startsWith(apiBase))
  } catch {
    return false
  }
}

/**
 * Wrap window.fetch so streamed chat requests and the Settings connection tests,
 * which call fetch directly rather than through axios, carry the interface language too.
 */
export function installUiLanguageFetch(): void {
  if (typeof window === 'undefined' || (window.fetch as { __uiLanguage?: boolean }).__uiLanguage) return
  const originalFetch = window.fetch.bind(window)
  const wrapped = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (!isApiRequest(url)) return originalFetch(input, init)
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
    if (!headers.has(UI_LANGUAGE_HEADER)) headers.set(UI_LANGUAGE_HEADER, currentUiLanguage())
    return originalFetch(input, { ...init, headers })
  }) as typeof window.fetch & { __uiLanguage?: boolean }
  wrapped.__uiLanguage = true
  window.fetch = wrapped
}
