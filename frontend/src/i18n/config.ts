export const STORAGE_KEY = 'local-notebook-locale'

export const localeConfig = {
  'zh-CN': {
    htmlLang: 'zh-CN',
    modelOutputLanguage: 'Chinese',
    relativeNow: '刚刚',
    matchesBrowserLanguage: (language: string) => language.startsWith('zh'),
  },
  tr: {
    htmlLang: 'tr',
    modelOutputLanguage: 'Turkish',
    relativeNow: 'Az önce',
    matchesBrowserLanguage: (language: string) => language.startsWith('tr'),
  },
  en: {
    htmlLang: 'en',
    modelOutputLanguage: 'English',
    relativeNow: 'Just now',
    matchesBrowserLanguage: (language: string) => language.startsWith('en'),
  },
} as const

export type Locale = keyof typeof localeConfig

export const DEFAULT_LOCALE: Locale = 'zh-CN'
export const supportedLocales = Object.keys(localeConfig) as Locale[]

export function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) return null
  const normalized = value.toLowerCase()
  if (normalized === 'zh' || normalized.startsWith('zh-')) return 'zh-CN'
  if (normalized === 'tr' || normalized.startsWith('tr-')) return 'tr'
  if (normalized === 'en' || normalized.startsWith('en-')) return 'en'
  return supportedLocales.includes(value as Locale) ? value as Locale : null
}

export function detectBrowserLocale(browserLanguage: string): Locale {
  const normalized = browserLanguage.toLowerCase()
  return supportedLocales.find((item) => localeConfig[item].matchesBrowserLanguage(normalized)) || 'en'
}
