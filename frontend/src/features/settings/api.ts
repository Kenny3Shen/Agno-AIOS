import { jsonInit, requestJson } from '@/shared/api/client'
import type { ListPaginationMeta } from '@/shared/lib/pagination'
import type { AuthUser, UserRole } from '@/shared/types/auth'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'

/** Single radio for long-term memory behaviour (avoids dual bool switches). */
export type MemoryMode = 'off' | 'automatic' | 'agentic'

export interface ChatSettings {
  show_raw_reasoning: boolean
  show_raw_tool_io: boolean
  show_thought_chain: boolean
  /** Preferred: off | automatic | agentic. Legacy bools are derived. */
  memory_mode: MemoryMode
  /** Derived from memory_mode (API still returns for compatibility). */
  memory_enabled: boolean
  /** Agno num_history_runs — past runs injected into model context. */
  num_history_runs: number
  /** Agno enable_session_summaries + add_session_summary_to_context. */
  session_summaries_enabled: boolean
  /** Agno add_datetime_to_context. */
  add_datetime_to_context: boolean
  /** Agno max_tool_calls_from_history; null = unlimited. */
  max_tool_calls_from_history: number | null
  /** Fallback tool_call_limit when agent profile has none; null = profile only. */
  default_tool_call_limit: number | null
  /** Derived from memory_mode === 'agentic'. */
  enable_agentic_memory: boolean
  /** Agno markdown response formatting. */
  markdown: boolean
  /** Allow MemoryManager to capture durable facts from tool results. */
  memory_tool_content_enabled: boolean
  /** Durable job: auto-prune memories by age + top-k. */
  memory_prune_enabled: boolean
  /** Delete memories whose updated_at is older than N days. */
  memory_prune_retention_days: number
  /** After age prune, keep only top-k scored memories per user. */
  memory_prune_top_k: number
  /** Rank/cap memories before injecting into the system prompt. */
  memory_inject_enabled: boolean
  /** Max memories injected per turn after scoring. */
  memory_inject_top_k: number
  /** Only consider memories updated within N days (0 = no window). */
  memory_inject_window_days: number
  /** Keep one memory per topic (highest score) to reduce conflicts. */
  memory_inject_dedupe_topics: boolean
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

type RolePreset = { role: UserRole; scopes: string[] }

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

type ServerManagedModelField = (typeof SERVER_DEFAULTED_MODEL_FIELDS)[number] | 'description' | 'builtin'

export type ModelConfigInput = Omit<ModelConfig, ServerManagedModelField | 'capabilities' | 'configured'> &
  Partial<Pick<ModelConfig, ServerManagedModelField>>

export type ModelConfigUpdatePayload = {
  active_model_id: string
  /** Dedicated MemoryManager model id; null clears pin (auto-pick). */
  memory_model_id?: string | null
  /** Dedicated Agent Eval judge model id; null clears pin (Agno default). */
  eval_judge_model_id?: string | null
  models: ModelConfigInput[]
}

export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const saveModels = (payload: ModelConfigUpdatePayload) => requestJson<ModelConfigResponse>('/models', jsonInit('PUT', payload))
export const testModel = (model: ModelConfig) =>
  requestJson<{ success: boolean; latency_ms?: number; message: string }>('/models/test', jsonInit('POST', model))
export const getChatSettings = () => requestJson<ChatSettings>('/settings/chat')
export const saveChatSettings = (payload: Partial<ChatSettings>) => requestJson<ChatSettings>('/settings/chat', jsonInit('PATCH', payload))

export interface UserNotificationSettings {
  feishu_webhook_configured: boolean
  feishu_webhook_hint: string
  global_feishu_webhook_configured: boolean
}

export const getNotificationSettings = () => requestJson<UserNotificationSettings>('/settings/notifications')
export const saveNotificationSettings = (payload: { feishu_webhook_url?: string }) =>
  requestJson<UserNotificationSettings>('/settings/notifications', jsonInit('PATCH', payload))

export const getKnowledgeRagSettings = () => requestJson<KnowledgeRagSettings>('/settings/knowledge')
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

export const getGuardrailSettings = () => requestJson<GuardrailSettings>('/settings/guardrails')
export const saveGuardrailSettings = (payload: Partial<GuardrailSettings>) =>
  requestJson<GuardrailSettings>('/settings/guardrails', jsonInit('PATCH', payload))

export interface CveSourceSetting {
  source: string
  enabled: boolean
}

export interface CveSourceSettingsResponse {
  sources: CveSourceSetting[]
}

export const getCveSourceSettings = () => requestJson<CveSourceSettingsResponse>('/settings/cve-sources')
export const saveCveSourceSettings = (sources: Record<string, boolean>) =>
  requestJson<CveSourceSettingsResponse>('/settings/cve-sources', jsonInit('PATCH', { sources }))

export const listRolePresets = async () => (await requestJson<{ data: RolePreset[] }>('/auth/roles')).data

export const listAdminUsers = async (page = 1, limit = 50): Promise<AdminUserListResult> => {
  const search = new URLSearchParams({ page: String(page), limit: String(limit) })
  return requestJson<AdminUserListResult>(`/auth/admin/users?${search}`)
}

export const setUserRole = (userId: string, role: UserRole) =>
  requestJson<AuthUser>(`/auth/admin/users/${encodeURIComponent(userId)}/role`, jsonInit('PATCH', { role }))
