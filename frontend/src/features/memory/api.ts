import { jsonInit, requestJson } from '@/shared/api/client'
import { asArray, asRecord } from '@/shared/lib/format'
export interface Memory { id: string; memory: string; topics?: string[]; input?: string; user_id?: string; agent_id?: string; team_id?: string; feedback?: string; status?: string; created_at?: string; updated_at?: string }
export const getMemories = async (params: { search?: string; user_id?: string; topic?: string }) => { const search = new URLSearchParams(); Object.entries(params).forEach(([k, v]) => v && search.set(k, v)); const data = asRecord(await requestJson<unknown>(`/memory?${search}`)); return { items: asArray<Memory>(data.memories ?? data.items), total: Number(asRecord(data.memory_filters).total ?? data.total ?? 0) } }
export const updateMemory = (id: string, memory: string, topics: string[]) => requestJson(`/memory/${encodeURIComponent(id)}`, jsonInit('PATCH', { memory, topics }))
export const deleteMemory = (id: string, userId?: string) => requestJson(`/memory/${encodeURIComponent(id)}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`, { method: 'DELETE' })
