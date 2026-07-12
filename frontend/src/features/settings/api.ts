import { jsonInit, requestJson } from '@/shared/api/client'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'
export interface ChatSettings {
  show_raw_reasoning: boolean
  show_raw_tool_io: boolean
  show_thought_chain: boolean
  memory_enabled: boolean
}
export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const saveModels = (payload: ModelConfigResponse) => requestJson<ModelConfigResponse>('/models', jsonInit('PUT', payload))
export const testModel = (model: ModelConfig) =>
  requestJson<{ success: boolean; latency_ms?: number; message: string }>('/models/test', jsonInit('POST', model))
export const getChatSettings = () => requestJson<ChatSettings>('/settings/chat')
export const saveChatSettings = (payload: Partial<ChatSettings>) => requestJson<ChatSettings>('/settings/chat', jsonInit('PATCH', payload))
