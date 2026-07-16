import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

export const compactId = (value?: string | null) => {
  const text = value?.trim() ?? ''
  if (!text) return '-'
  return text.length <= 18 ? text : `${text.slice(0, 8)}...${text.slice(-4)}`
}

export const formatDate = (value?: string | number | null, locale: string = 'zh-CN') => {
  if (value === undefined || value === null || value === '') return '-'
  const date = new Date(typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value)
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString(locale)
}

/** Locale-aware date formatter bound to the active i18n language. */
export const useFormatDate = () => {
  const { i18n } = useTranslation()
  return useCallback((value?: string | number | null) => formatDate(value, i18n.language || 'zh-CN'), [i18n.language])
}

const timestampMs = (value?: string | number | null) => {
  if (value === undefined || value === null || value === '') return Number.NEGATIVE_INFINITY
  const date = new Date(typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value)
  return Number.isNaN(date.valueOf()) ? Number.NEGATIVE_INFINITY : date.valueOf()
}

/** Compare date-like values for Table sorters (missing/invalid sort first ascending). */
export const compareTimestamp = (a?: string | number | null, b?: string | number | null) =>
  timestampMs(a) - timestampMs(b)

export const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
