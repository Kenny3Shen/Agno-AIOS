import { requestJson } from '@/shared/api/client'
import type { TraceDetail, TraceList } from './types'
export const listTraces = (params: Record<string, string | number | undefined>) => { const search = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') search.set(key, String(value)) }); return requestJson<TraceList>(`/traces?${search}`) }
export const getTrace = (id: string) => requestJson<TraceDetail>(`/traces/${encodeURIComponent(id)}`)
