import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  McpServiceId,
  McpServiceStatusResponse,
  McpTokenInfo,
  McpTokenIssueResponse,
  ResourceVisibility,
  SkillListResponse,
  SkillToggleResponse,
  UploadResultResponse
} from '../types'

/**
 * Skills management API.
 */
export function useSkillsApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)
  const toggling = ref(false)

  const fetchSkills = async (): Promise<SkillListResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch('/skills')
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('skillsLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('skillsLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const toggleSkill = async (skillName: string, enabled: boolean): Promise<SkillToggleResponse> => {
    toggling.value = true
    error.value = null
    try {
      const response = await apiFetch(`/skills/${encodeURIComponent(skillName)}/toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('skillToggleFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('skillToggleFailed'))
      throw err
    } finally {
      toggling.value = false
    }
  }

  const uploadSkill = async (payload: { name: string; file: File; visibility: ResourceVisibility }): Promise<UploadResultResponse> => {
    loading.value = true
    error.value = null
    const form = new FormData()
    form.append('name', payload.name)
    form.append('visibility', payload.visibility)
    form.append('file', payload.file)
    try {
      const response = await apiFetch('/skills/upload', {
        method: 'POST',
        body: form
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('skillsLoadFailed')))
      }
      return await response.json()
    } finally {
      loading.value = false
    }
  }

  const updateSkillVisibility = async (skillName: string, visibility: ResourceVisibility): Promise<{ name: string; visibility: ResourceVisibility }> => {
    const response = await apiFetch(`/skills/${encodeURIComponent(skillName)}/visibility`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visibility })
    })
    if (!response.ok) {
      const data: unknown = await response.json().catch(() => ({}))
      throw new Error(messageFromResponse(data, apiMessage('skillToggleFailed')))
    }
    return await response.json()
  }

  return {
    loading,
    error,
    toggling,
    fetchSkills,
    toggleSkill,
    uploadSkill,
    updateSkillVisibility
  }
}

/**
 * MCP management API.
 */
export function useMcpApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const request = async <T>(path: string, options: RequestInit = {}, fallback = apiMessage('mcpRequestFailed')): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/mcp${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {})
        }
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, fallback))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, fallback)
      throw err
    } finally {
      loading.value = false
    }
  }

  const fetchConfig = () => request<McpServiceStatusResponse>('/config', {}, apiMessage('mcpConfigLoadFailed'))

  const updateConfig = (id: McpServiceId, enabled: boolean) => request<{ success: boolean; restart_required?: boolean }>('/config', {
    method: 'POST',
    body: JSON.stringify({ id, enabled })
  }, apiMessage('mcpConfigUpdateFailed'))

  const listTokens = () => request<McpTokenInfo[]>('/tokens', {}, apiMessage('mcpTokenLoadFailed'))

  const issueToken = (name: string, expiresIn: number) => request<McpTokenIssueResponse>('/tokens/issue', {
    method: 'POST',
    body: JSON.stringify({ name, expires_in: expiresIn })
  }, apiMessage('mcpTokenIssueFailed'))

  const deleteToken = (id: number) => request<{ success: boolean }>('/tokens/delete', {
    method: 'POST',
    body: JSON.stringify({ id })
  }, apiMessage('mcpTokenDeleteFailed'))

  const uploadMcp = (payload: { name: string; description?: string; manifest: string; visibility: ResourceVisibility }) => request<UploadResultResponse>('/upload', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('mcpRequestFailed'))

  const updateMcpServerVisibility = (serverName: string, visibility: ResourceVisibility) => request<{ success: boolean; name: string; visibility: ResourceVisibility }>(`/servers/${encodeURIComponent(serverName)}/visibility`, {
    method: 'PUT',
    body: JSON.stringify({ visibility })
  }, apiMessage('mcpRequestFailed'))

  return {
    loading,
    error,
    fetchConfig,
    updateConfig,
    listTokens,
    issueToken,
    deleteToken,
    uploadMcp,
    updateMcpServerVisibility
  }
}
