export const compactId = (value?: string | null) => {
  const text = value?.trim() ?? ''
  if (!text) return '-'
  return text.length <= 18 ? text : `${text.slice(0, 8)}...${text.slice(-4)}`
}

export const formatDate = (value?: string | number | null, locale: unknown = 'zh-CN') => {
  if (value === undefined || value === null || value === '') return '-'
  const date = new Date(typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value)
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString(typeof locale === 'string' ? locale : 'zh-CN')
}

export const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' ? value as Record<string, unknown> : {}
)

export const asArray = <T = Record<string, unknown>>(value: unknown): T[] => Array.isArray(value) ? value as T[] : []
