// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  THEME_STORAGE_KEY,
  applyThemeClass,
  getStoredTheme,
  setStoredTheme,
} from './theme.ts'

describe('theme utilities', () => {
  afterEach(() => {
    window.localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('falls back to light when localStorage has no valid theme', () => {
    expect(getStoredTheme()).toBe('light')

    window.localStorage.setItem(THEME_STORAGE_KEY, 'contrast')

    expect(getStoredTheme()).toBe('light')
  })

  it('stores valid theme values', () => {
    setStoredTheme('dark')

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(getStoredTheme()).toBe('dark')
  })

  it('toggles the dark class on the provided root element', () => {
    const root = document.createElement('html')

    applyThemeClass('dark', root)
    expect(root.classList.contains('dark')).toBe(true)

    applyThemeClass('light', root)
    expect(root.classList.contains('dark')).toBe(false)
  })
})
