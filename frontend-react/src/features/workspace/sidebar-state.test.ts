import { describe, expect, it } from 'vitest'

import {
  DEFAULT_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  clampSidebarWidth,
} from './sidebar-state.ts'

describe('sidebar sizing', () => {
  it('keeps sidebar width within the supported range', () => {
    expect(clampSidebarWidth(MIN_SIDEBAR_WIDTH - 80)).toBe(MIN_SIDEBAR_WIDTH)
    expect(clampSidebarWidth(MAX_SIDEBAR_WIDTH + 80)).toBe(MAX_SIDEBAR_WIDTH)
    expect(clampSidebarWidth(DEFAULT_SIDEBAR_WIDTH)).toBe(DEFAULT_SIDEBAR_WIDTH)
  })
})
