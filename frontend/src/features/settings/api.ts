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

export type KnowledgeSearchTypeSetting = 'hybrid' | 'vector' | 'keyword'

export interface KnowledgeRagSettings {
  search_type: KnowledgeSearchTypeSetting
  top_k: number
  vector_score_weight: number
  similarity_threshold: number | null
  content_language: string
  prefix_match: boolean
  rerank_enabled: boolean
  rerank_model?: string
  rerank_candidate_multiplier: number
  rerank_min_candidates: number
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

export interface UserNotificationSettings {
  feishu_webhook_configured: boolean
  feishu_webhook_hint: string
  global_feishu_webhook_configured: boolean
}

export const getNotificationSettings = () =>
  requestJson<UserNotificationSettings>('/settings/notifications')
export const saveNotificationSettings = (payload: { feishu_webhook_url?: string }) =>
  requestJson<UserNotificationSettings>('/settings/notifications', jsonInit('PATCH', payload))

export const getKnowledgeRagSettings = () =>
  requestJson<KnowledgeRagSettings>('/settings/knowledge')
export const saveKnowledgeRagSettings = (payload: Partial<KnowledgeRagSettings>) =>
  requestJson<KnowledgeRagSettings>('/settings/knowledge', jsonInit('PATCH', payload))

/** Global Agno input guardrails (no OpenAI Moderation). */
export interface GuardrailSettings {
  enabled: boolean
  pii_enabled: boolean
  pii_mask: boolean
  pii_check_email: boolean
  pii_check_phone: boolean
  prompt_injection_enabled: boolean
}

export const getGuardrailSettings = () =>
  requestJson<GuardrailSettings>('/settings/guardrails')
export const saveGuardrailSettings = (payload: Partial<GuardrailSettings>) =>
  requestJson<GuardrailSettings>('/settings/guardrails', jsonInit('PATCH', payload))

export const listRolePresets = async () => (await requestJson<{ data: RolePreset[] }>('/auth/roles')).data

export const listAdminUsers = async (page = 1, limit = 50): Promise<AdminUserListResult> => {
  const search = new URLSearchParams({ page: String(page), limit: String(limit) })
  return requestJson<AdminUserListResult>(`/auth/admin/users?${search}`)
}

export const setUserRole = (userId: string, role: string) =>
  requestJson<AuthUser>(`/auth/admin/users/${encodeURIComponent(userId)}/role`, jsonInit('PATCH', { role }))
