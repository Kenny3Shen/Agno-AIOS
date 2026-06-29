export const MIN_SIDEBAR_WIDTH = 224
export const DEFAULT_SIDEBAR_WIDTH = 280
export const MAX_SIDEBAR_WIDTH = 380
export const COLLAPSED_SIDEBAR_WIDTH = 72

export function clampSidebarWidth(width: number) {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width))
}
