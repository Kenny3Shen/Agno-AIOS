import { jsonInit, requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'

export interface Memory {
  /** UI key; always mirrored from API ``memory_id``. */
  id: string
  memory_id: string
  memory: string
  topics?: string[]
  input?: string
  user_id?: string
  agent_id?: string
  team_id?: string
  feedback?: string
  status?: string
  created_at?: string
  updated_at?: string
}

export interface MemoryListMeta {
  page: number
  limit: number
  total_count: number
  total_pages: number
  search_time_ms: number
}

/** Agno-style memory list envelope after row normalize. */
export interface MemoryListResult {
  data: Memory[]
  meta: MemoryListMeta
}

/** Map Agno-native memory rows into UI Memory records. */
export const normalizeMemory = (value: unknown): Memory | null => {
  const row = asRecord(value)
  const memoryId = String(row.memory_id ?? '').trim()
  if (!memoryId) return null
  const topicsRaw = row.topics
  const topics = Array.isArray(topicsRaw)
    ? topicsRaw.map((topic) => String(topic)).filter((topic) => topic.trim().length > 0)
    : undefined
  return {
    id: memoryId,
    memory_id: memoryId,
    memory: String(row.memory ?? ''),
    topics,
    input: row.input != null ? String(row.input) : undefined,
    user_id: row.user_id != null ? String(row.user_id) : undefined,
    agent_id: row.agent_id != null ? String(row.agent_id) : undefined,
    team_id: row.team_id != null ? String(row.team_id) : undefined,
    feedback: row.feedback != null ? String(row.feedback) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    created_at: row.created_at != null ? String(row.created_at) : undefined,
    updated_at: row.updated_at != null ? String(row.updated_at) : undefined,
  }
}

export type MemoryListParams = {
  search_content?: string
  user_id?: string
  topic?: string
  page?: number
  limit?: number
}

export const getMemories = async (params: MemoryListParams = {}): Promise<MemoryListResult> => {
  const search = new URLSearchParams()
  if (params.search_content) search.set('search_content', params.search_content)
  if (params.user_id) search.set('user_id', params.user_id)
  if (params.topic) search.set('topic', params.topic)
  if (params.page != null) search.set('page', String(params.page))
  if (params.limit != null) search.set('limit', String(params.limit))
  const query = search.toString()
  const data = asRecord(await requestJson<unknown>(`/memories${query ? `?${query}` : ''}`))
  const meta = asRecord(data.meta)
  const rows = Array.isArray(data.data) ? data.data : []
  const dataRows = rows
    .map((row) => normalizeMemory(row))
    .filter((row): row is Memory => row != null)
  const page = Number(meta.page ?? params.page ?? 1) || 1
  const limit = Number(meta.limit ?? params.limit ?? 20) || 20
  const totalCount = Number(meta.total_count ?? dataRows.length) || 0
  return {
    data: dataRows,
    meta: {
      page,
      limit,
      total_count: totalCount,
      total_pages: Number(meta.total_pages ?? (totalCount ? Math.ceil(totalCount / Math.max(limit, 1)) : 0)) || 0,
      search_time_ms: Number(meta.search_time_ms ?? 0) || 0,
    },
  }
}

export const updateMemory = (id: string, memory: string, topics: string[]) =>
  requestJson(`/memories/${encodeURIComponent(id)}`, jsonInit('PATCH', { memory, topics }))

export const deleteMemory = (id: string, userId?: string) =>
  requestJson(`/memories/${encodeURIComponent(id)}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`, {
    method: 'DELETE',
  })
