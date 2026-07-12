export const LOGIN_PATH = '/login'
export const DEFAULT_AUTHENTICATED_PATH = '/dashboard'

interface AppLocation {
  pathname: string
  searchStr?: string
}

export const sanitizeNextPath = (value: unknown): string | null => {
  if (typeof value !== 'string') return null
  const next = value.trim()
  if (!next || !next.startsWith('/') || next.startsWith('//')) return null
  try {
    const url = new URL(next, 'https://agno-aios.local')
    if (url.origin !== 'https://agno-aios.local' || url.pathname === LOGIN_PATH) return null
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return null
  }
}

export const nextPathFromLocation = (location: AppLocation) => {
  return sanitizeNextPath(`${location.pathname}${location.searchStr ?? ''}`)
}

export const loginPath = (next: string | null) => {
  return next ? `${LOGIN_PATH}?next=${encodeURIComponent(next)}` : LOGIN_PATH
}
