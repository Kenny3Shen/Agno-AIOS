/** Memory workbench client (Agno data/meta list, mutate, clear). */
import { jsonInit, requestJson } from '@/shared/api/client'
import type { ListPaginationMeta } from '@/shared/lib/pagination'

export interface Memory {
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

/** Agno-style memory list envelope. */
type MemoryListResult = {
  data: Memory[]
  meta: ListPaginationMeta
}

type MemoryListParams = {
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
  return requestJson<MemoryListResult>(`/memories${query ? `?${query}` : ''}`)
}

export const updateMemory = (memoryId: string, memory: string, topics: string[]) =>
  requestJson(`/memories/${encodeURIComponent(memoryId)}`, jsonInit('PATCH', { memory, topics }))

export const deleteMemory = (memoryId: string, userId?: string) =>
  requestJson(`/memories/${encodeURIComponent(memoryId)}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`, {
    method: 'DELETE',
  })

type ClearMemoriesParams = {
  user_id?: string
  /** Admin-only: wipe every memory in the store. */
  all_users?: boolean
}

export const clearMemories = (params: ClearMemoriesParams = {}) =>
  requestJson<{ deleted: number; user_id?: string | null; all_users?: boolean }>(
    '/memories/clear',
    jsonInit('POST', {
      user_id: params.user_id || undefined,
      all_users: Boolean(params.all_users),
    }),
  )
