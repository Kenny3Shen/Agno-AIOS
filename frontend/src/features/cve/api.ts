import { jsonInit, requestJson } from '@/shared/api/client'

export interface Cve {
  id: number
  cve_id: string
  github_url: string
  description: string
  source: string
  create_time: string
}

export interface CveSearchResponse {
  data: Cve[]
  meta: {
    page: number
    limit: number
    total_pages: number
    total_count: number
    search_time_ms?: number
  }
}

export const searchCves = (payload: { query: string; source?: string; page: number; size: number }) =>
  requestJson<CveSearchResponse>('/cve/search', jsonInit('POST', payload))

export const updateCves = () => requestJson<Record<string, unknown>>('/cve/update', { method: 'POST' })
