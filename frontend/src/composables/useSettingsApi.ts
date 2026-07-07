import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromResponse } from './useApiCore'
import type {
  ModelConfig,
  ModelConnectivityTestResponse,
  ModelConfigResponse,
  SettingsResponse
} from '../types'

/**
 * Settings API
 */
export function useSettingsApi() {
  const apiMessage = useApiMessage()
  const loadingSettings = ref(false)
  const saving = ref(false)

  const fetchSettings = async (): Promise<Record<string, string>> => {
    loadingSettings.value = true
    try {
      const response = await apiFetch('/settings')
      if (!response.ok) throw new Error(apiMessage('settingsLoadFailed'))
      const data: SettingsResponse = await response.json()
      return data.settings
    } finally {
      loadingSettings.value = false
    }
  }

  const updateSettings = async (settings: Record<string, string>): Promise<Record<string, string>> => {
    saving.value = true
    try {
      const response = await apiFetch('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings })
      })
      if (!response.ok) throw new Error(apiMessage('settingsUpdateFailed'))
      const data: SettingsResponse = await response.json()
      return data.settings
    } finally {
      saving.value = false
    }
  }

  const fetchModels = async (): Promise<ModelConfigResponse> => {
    loadingSettings.value = true
    try {
      const response = await apiFetch('/models')
      if (!response.ok) throw new Error(apiMessage('modelsLoadFailed'))
      return await response.json()
    } finally {
      loadingSettings.value = false
    }
  }

  const updateModels = async (payload: ModelConfigResponse): Promise<ModelConfigResponse> => {
    saving.value = true
    try {
      const response = await apiFetch('/models', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('modelsSaveFailed')))
      }
      return await response.json()
    } finally {
      saving.value = false
    }
  }

  const testModelConnection = async (model: ModelConfig): Promise<ModelConnectivityTestResponse> => {
    const response = await apiFetch('/models/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(model)
    })
    if (!response.ok) {
      const data: unknown = await response.json().catch(() => ({}))
      throw new Error(messageFromResponse(data, apiMessage('modelsTestFailed')))
    }
    return await response.json()
  }

  return {
    loadingSettings,
    saving,
    fetchSettings,
    updateSettings,
    fetchModels,
    updateModels,
    testModelConnection
  }
}
