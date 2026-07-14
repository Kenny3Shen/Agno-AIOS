import { jsonInit, requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'

export interface Memory {
  id: string
  memory_id?: string
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

export interface MemoryListResult {
  items: Memory[]
  total: number
  page: number
  limit: number
}

const memoryId = (row: Record<string, unknown>) => String(row.id ?? row.memory_id ?? '').trim()

/** Normalize legacy workbench and Agno-native memory rows. */
export const normalizeMemory = (value: unknown): Memory | null => {
  const row = asRecord(value)
  const id = memoryId(row)
  if (!id) return null
  const topicsRaw = row.topics
  const topics = Array.isArray(topicsRaw)
    ? topicsRaw.map((topic) => String(topic)).filter((topic) => topic.trim().length > 0)
    : undefined
  return {
    id,
    memory_id: String(row.memory_id ?? id),
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

const listRows = (data: Record<string, unknown>): unknown[] => {
  if (Array.isArray(data.data)) return data.data
  if (Array.isArray(data.items)) return data.items
  if (Array.isArray(data.memories)) return data.memories
  return []
}

const listTotal = (data: Record<string, unknown>, fallbackItems: number) => {
  const meta = asRecord(data.meta)
  const filters = asRecord(data.memory_filters)
  const candidates = [meta.total_count, data.total_count, data.total, filters.total]
  for (const value of candidates) {
    if (value === undefined || value === null || value === '') continue
    const number = Number(value)
    if (Number.isFinite(number)) return number
  }
  return fallbackItems
}

const listPage = (data: Record<string, unknown>) => {
  const meta = asRecord(data.meta)
  const filters = asRecord(data.memory_filters)
  return Number(meta.page ?? data.page ?? filters.page ?? 1) || 1
}

const listLimit = (data: Record<string, unknown>) => {
  const meta = asRecord(data.meta)
  const filters = asRecord(data.memory_filters)
  return Number(meta.limit ?? data.limit ?? filters.limit ?? 20) || 20
}

export type MemoryListParams = {
  search?: string
  search_content?: string
  user_id?: string
  topic?: string
  page?: number
  limit?: number
}

export const getMemories = async (params: MemoryListParams = {}): Promise<MemoryListResult> => {
  const search = new URLSearchParams()
  const searchValue = params.search_content ?? params.search
  if (searchValue) {
    // Prefer Agno-native query name; backend also accepts `search`.
    search.set('search_content', searchValue)
  }
  if (params.user_id) search.set('user_id', params.user_id)
  if (params.topic) search.set('topic', params.topic)
  if (params.page != null) search.set('page', String(params.page))
  if (params.limit != null) search.set('limit', String(params.limit))
  const query = search.toString()
  const data = asRecord(await requestJson<unknown>(`/memories${query ? `?${query}` : ''}`))
  const items = listRows(data)
    .map((row) => normalizeMemory(row))
    .filter((row): row is Memory => row != null)
  return {
    items,
    total: listTotal(data, items.length),
    page: listPage(data),
    limit: listLimit(data),
  }
}

export const updateMemory = (id: string, memory: string, topics: string[]) =>
  requestJson(`/memories/${encodeURIComponent(id)}`, jsonInit('PATCH', { memory, topics }))

export const deleteMemory = (id: string, userId?: string) =>
  requestJson(`/memories/${encodeURIComponent(id)}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`, {
    method: 'DELETE',
  })
