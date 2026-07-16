import { jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'
import type { AuthUser, UserRole } from '@/shared/types/auth'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'

export interface ChatSettings {
  show_raw_reasoning: boolean
  show_raw_tool_io: boolean
  show_thought_chain: boolean
  memory_enabled: boolean
}

export type RolePreset = { role: UserRole | string; scopes: string[] }

export type AdminUserListResult = {
  data: AuthUser[]
  meta: ListPaginationMeta
}

export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const saveModels = (payload: ModelConfigResponse) =>
  requestJson<ModelConfigResponse>('/models', jsonInit('PUT', payload))
export const testModel = (model: ModelConfig) =>
  requestJson<{ success: boolean; latency_ms?: number; message: string }>(
    '/models/test',
    jsonInit('POST', model),
  )
export const getChatSettings = () => requestJson<ChatSettings>('/settings/chat')
export const saveChatSettings = (payload: Partial<ChatSettings>) =>
  requestJson<ChatSettings>('/settings/chat', jsonInit('PATCH', payload))

export const listRolePresets = async () => {
  const payload = await requestJson<{ data: RolePreset[] }>('/auth/roles')
  return Array.isArray(payload?.data) ? payload.data : []
}

export const listAdminUsers = async (page = 1, limit = 50): Promise<AdminUserListResult> => {
  const search = new URLSearchParams({ page: String(page), limit: String(limit) })
  const payload = await requestJson<unknown>(`/auth/admin/users?${search}`)
  return normalizePaginatedList(payload, {
    page,
    limit,
    mapItem: (row) => {
      if (!row || typeof row !== 'object') return null
      const item = row as Record<string, unknown>
      const id = String(item.id ?? '').trim()
      const email = String(item.email ?? '').trim()
      if (!id || !email) return null
      return {
        id,
        email,
        role: (item.role as AuthUser['role']) ?? 'user',
        scopes: Array.isArray(item.scopes) ? (item.scopes as string[]) : [],
        is_active: Boolean(item.is_active ?? true),
        is_superuser: Boolean(item.is_superuser),
        is_verified: Boolean(item.is_verified),
      } satisfies AuthUser
    },
  })
}

export const setUserRole = (userId: string, role: string) =>
  requestJson<AuthUser>(`/auth/admin/users/${encodeURIComponent(userId)}/role`, jsonInit('PATCH', { role }))
