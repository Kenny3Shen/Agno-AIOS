import { ApiError, apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { consumeSse } from '@/features/chat/utils'
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

export type CveUpdateProgress = {
  stage?: string
  status?: string
  message?: string
  source?: string
  source_index?: number
  source_total?: number
  add_count?: number
  del_count?: number
  pending_add?: number
  pending_del?: number
  duration_seconds?: number
  error?: string
  code?: number
}

export const updateCvesStream = async (
  onProgress: (event: CveUpdateProgress) => void,
  signal?: AbortSignal,
): Promise<{ add_count: number; del_count: number }> => {
  const response = await apiFetch('/cve/update?stream=true', {
    method: 'POST',
    signal,
    headers: { Accept: 'text/event-stream' },
  })
  if (!response.ok) {
    let message = `CVE update failed (${response.status})`
    try {
      const payload = (await response.json()) as { detail?: string; message?: string }
      message = payload.detail || payload.message || message
    } catch {
      // ignore non-json error bodies
    }
    throw new ApiError(message, response.status)
  }
  if (!response.body) {
    throw new Error('CVE update stream has no body')
  }
  let addCount = 0
  let delCount = 0
  let failed: string | null = null
  await consumeSse(
    response.body,
    ({ event, data }) => {
      let payload: CveUpdateProgress = {}
      try {
        payload = data ? (JSON.parse(data) as CveUpdateProgress) : {}
      } catch {
        payload = { message: data }
      }
      onProgress(payload)
      if (typeof payload.add_count === 'number') addCount = payload.add_count
      if (typeof payload.del_count === 'number') delCount = payload.del_count
      if (event === 'progress.failed' || payload.status === 'failed') {
        failed = payload.error || payload.message || 'CVE update failed'
      }
    },
    signal,
  )
  if (failed) throw new Error(failed)
  return { add_count: addCount, del_count: delCount }
}
