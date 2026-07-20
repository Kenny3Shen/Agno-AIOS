import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { consumeSse } from '@/features/chat/utils'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'

export interface IpBlacklistEntry {
  id: number
  indicator: string
  indicator_type: string
  source: string
  list_name: string
  description: string
  first_seen: string | null
  last_seen: string | null
  updated_at?: string | null
}

type SearchResponse = {
  data: IpBlacklistEntry[]
  meta: ListPaginationMeta
}

const isPositiveInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value > 0

const parseEntry = (value: unknown, context: string): IpBlacklistEntry => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context}: invalid IP blacklist payload`)
  }
  const row = value as Record<string, unknown>
  if (
    !isPositiveInteger(row.id) ||
    typeof row.indicator !== 'string' ||
    !row.indicator.trim() ||
    typeof row.indicator_type !== 'string' ||
    typeof row.source !== 'string' ||
    typeof row.list_name !== 'string' ||
    typeof row.description !== 'string'
  ) {
    throw new Error(`${context}: invalid IP blacklist payload`)
  }
  return {
    id: row.id,
    indicator: row.indicator,
    indicator_type: row.indicator_type,
    source: row.source,
    list_name: row.list_name,
    description: row.description,
    first_seen: typeof row.first_seen === 'string' ? row.first_seen : null,
    last_seen: typeof row.last_seen === 'string' ? row.last_seen : null,
    updated_at: typeof row.updated_at === 'string' ? row.updated_at : null,
  }
}

export const searchIpBlacklist = async (payload: {
  query: string
  source?: string
  page: number
  size: number
}): Promise<SearchResponse> => {
  const raw = await requestJson<unknown>('/ip-blacklist/search', jsonInit('POST', payload))
  return normalizePaginatedList(raw, {
    mapItem: (item) => parseEntry(item, 'searchIpBlacklist'),
  })
}

export type IpBlacklistUpdateProgress = {
  stage?: string
  status?: string
  message?: string
  source?: string
  source_index?: number
  source_total?: number
  add_count?: number
  del_count?: number
  error?: string
  code?: number
}

export const updateIpBlacklistStream = async (
  onProgress: (event: IpBlacklistUpdateProgress) => void,
  signal?: AbortSignal,
) => {
  const response = await apiFetch('/ip-blacklist/update?stream=true', {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`IP blacklist update failed (${response.status})`)
  }
  await consumeSse(
    response.body,
    ({ event, data }) => {
      if (event && event !== 'progress' && event !== 'message') return
      try {
        onProgress(JSON.parse(data) as IpBlacklistUpdateProgress)
      } catch {
        // ignore non-JSON
      }
    },
    signal,
  )
}
