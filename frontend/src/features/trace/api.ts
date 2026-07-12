import { requestJson } from '@/shared/api/client'
import type { TraceDetail, TraceList, TraceSessionList, TraceSessionSummary } from './types'

type TraceParams = Record<string, string | number | undefined>

const traceSearch = (params: TraceParams) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  return search
}

export const listTraces = (params: TraceParams) => requestJson<TraceList>(`/traces?${traceSearch(params)}`)

const listTraceSessionsPage = (params: TraceParams) => requestJson<TraceSessionList>(`/traces/sessions?${traceSearch(params)}`)

export const listTraceSessions = async (params: TraceParams) => {
  const limit = 200
  let page = 1
  let totalCount = 0
  const items: TraceSessionSummary[] = []

  while (true) {
    const response = await listTraceSessionsPage({ ...params, page, limit })
    totalCount = response.total_count
    items.push(...response.items)
    if (items.length >= totalCount || response.items.length === 0) {
      return { ...response, items, total_count: totalCount, page: 1, limit }
    }
    page += 1
  }
}

export const getTrace = (id: string) => requestJson<TraceDetail>(`/traces/${encodeURIComponent(id)}`)
