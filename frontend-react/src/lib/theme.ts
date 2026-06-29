export type ThemeMode = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'agno-aios-theme'

export function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'light' || value === 'dark'
}

function resolveStorage(storage?: Storage) {
  if (storage) return storage
  if (typeof window === 'undefined') return undefined
  return window.localStorage
}

export function getStoredTheme(storage?: Storage) {
  const targetStorage = resolveStorage(storage)

  const value = targetStorage?.getItem(THEME_STORAGE_KEY) ?? null
  return isThemeMode(value) ? value : ('light' satisfies ThemeMode)
}

export function setStoredTheme(theme: ThemeMode, storage?: Storage) {
  resolveStorage(storage)?.setItem(THEME_STORAGE_KEY, theme)
}

export function applyThemeClass(theme: ThemeMode, root?: HTMLElement) {
  const targetRoot =
    root ??
    (typeof document === 'undefined' ? undefined : document.documentElement)

  targetRoot?.classList.toggle('dark', theme === 'dark')
}
