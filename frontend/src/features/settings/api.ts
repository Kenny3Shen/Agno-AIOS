import { jsonInit, requestJson } from '@/shared/api/client'
import type { ListPaginationMeta } from '@/shared/lib/pagination'
import type { AuthUser, UserRole } from '@/shared/types/auth'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'

export interface ChatSettings {
  show_raw_reasoning: boolean
  show_raw_tool_io: boolean
  show_thought_chain: boolean
  memory_enabled: boolean
}

type RolePreset = { role: UserRole | string; scopes: string[] }

type AdminUserListResult = {
  data: AuthUser[]
  meta: ListPaginationMeta
}

export const SERVER_DEFAULTED_MODEL_FIELDS = [
  'api_protocol',
  'structured_output_mode',
  'default_reasoning_effort',
  'parallel_tool_calls',
  'live_search_enabled',
  'retries',
  'delay_between_retries',
  'exponential_backoff',
  'http_max_retries',
] as const

type ServerManagedModelField =
  | (typeof SERVER_DEFAULTED_MODEL_FIELDS)[number]
  | 'description'
  | 'builtin'

export type ModelConfigInput = Omit<
  ModelConfig,
  ServerManagedModelField | 'capabilities' | 'configured'
> &
  Partial<Pick<ModelConfig, ServerManagedModelField>>

export type ModelConfigUpdatePayload = {
  active_model_id: string
  models: ModelConfigInput[]
}

export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const saveModels = (payload: ModelConfigUpdatePayload) =>
  requestJson<ModelConfigResponse>('/models', jsonInit('PUT', payload))
export const testModel = (model: ModelConfig) =>
  requestJson<{ success: boolean; latency_ms?: number; message: string }>(
    '/models/test',
    jsonInit('POST', model),
  )
export const getChatSettings = () => requestJson<ChatSettings>('/settings/chat')
export const saveChatSettings = (payload: Partial<ChatSettings>) =>
  requestJson<ChatSettings>('/settings/chat', jsonInit('PATCH', payload))

export const listRolePresets = async () => (await requestJson<{ data: RolePreset[] }>('/auth/roles')).data

export const listAdminUsers = async (page = 1, limit = 50): Promise<AdminUserListResult> => {
  const search = new URLSearchParams({ page: String(page), limit: String(limit) })
  return requestJson<AdminUserListResult>(`/auth/admin/users?${search}`)
}

export const setUserRole = (userId: string, role: string) =>
  requestJson<AuthUser>(`/auth/admin/users/${encodeURIComponent(userId)}/role`, jsonInit('PATCH', { role }))
