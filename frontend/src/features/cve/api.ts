import { jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'

export interface Cve {
  id: number
  cve_id: string
  github_url: string
  description: string
  source: string
  create_time: string
}

export type CveSearchResponse = {
  data: Cve[]
  meta: ListPaginationMeta
}

const normalizeCve = (value: unknown): Cve | null => {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const id = Number(row.id)
  const cveId = String(row.cve_id ?? '').trim()
  if (!Number.isFinite(id) || !cveId) return null
  return {
    id,
    cve_id: cveId,
    github_url: String(row.github_url ?? ''),
    description: String(row.description ?? ''),
    source: String(row.source ?? ''),
    create_time: String(row.create_time ?? ''),
  }
}

export const searchCves = async (payload: {
  query: string
  source?: string
  page: number
  size: number
}): Promise<CveSearchResponse> => {
  const raw = await requestJson<unknown>('/cve/search', jsonInit('POST', payload))
  return normalizePaginatedList(raw, {
    page: payload.page,
    limit: payload.size,
    mapItem: normalizeCve,
  })
}

export const updateCves = () =>
  requestJson<{ message?: string; add_count?: number; del_count?: number }>('/cve/update', { method: 'POST' })
