import { jsonInit, requestJson } from '@/shared/api/client'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'
export const getSettings = async () => (await requestJson<{ settings: Record<string, string> }>('/settings')).settings
export const saveSettings = async (settings: Record<string, string>) => (await requestJson<{ settings: Record<string, string> }>('/settings', jsonInit('PUT', { settings }))).settings
export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const saveModels = (payload: ModelConfigResponse) => requestJson<ModelConfigResponse>('/models', jsonInit('PUT', payload))
export const testModel = (model: ModelConfig) => requestJson<{ success: boolean; latency_ms?: number; message: string }>('/models/test', jsonInit('POST', model))
