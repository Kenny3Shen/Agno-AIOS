import { ref } from 'vue'
import type { CveSearchParams, CveSearchResponse, AssetSearchParams, AssetSearchResponse, Url2MdParseResponse, UpdateResponse, SettingsResponse, ChatSession, Message, TraceListResponse, TraceDetailResponse, TraceStatus, SkillListResponse, SkillToggleResponse } from '../types'

const API_BASE = '/api'

/**
 * CVE 搜索 API
 */
export function useCveApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const searchCve = async (params: CveSearchParams): Promise<CveSearchResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/cve/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(params)
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.message || '搜索失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '搜索失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  const updateDatabase = async (): Promise<UpdateResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/cve/update`, {
        method: 'POST'
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.message || '更新失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '更新失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    searchCve,
    updateDatabase
  }
}

/**
 * 资产搜索 API
 */
export function useAssetApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const searchAsset = async (params: AssetSearchParams): Promise<AssetSearchResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/asset/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(params)
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.message || '搜索失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '搜索失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    searchAsset
  }
}

/**
 * LLM 聊天 API
 */
export function useChatApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const sendMessageStream = async (
    message: string,
    sessionId: string | null,
    onChunk: (chunk: string) => void
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({ message, session_id: sessionId })
      })

      if (!response.ok || !response.body) {
        throw new Error(`请求失败: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const lines = part.split('\n')
          const isError = lines.some(line => line.startsWith('event: error'))
          const dataLines = lines
            .filter(line => line.startsWith('data: '))
            .map(line => line.slice(6))

          if (!dataLines.length) continue

          const data = dataLines.join('\n')
          if (data === '[DONE]') return
          if (isError) {
            throw new Error(data)
          }

          onChunk(data)
        }
      }
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || '发送失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    sendMessageStream
  }
}

/**
 * 聊天会话历史 API
 */
export function useChatHistory() {
  const loadingSessions = ref(false)

  const listSessions = async (): Promise<ChatSession[]> => {
    loadingSessions.value = true
    try {
      const response = await fetch(`${API_BASE}/chat/sessions`)
      if (!response.ok) throw new Error('获取会话列表失败')
      return await response.json()
    } finally {
      loadingSessions.value = false
    }
  }

  const getSessionHistory = async (sessionId: string): Promise<Message[]> => {
    const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}`)
    if (!response.ok) throw new Error('获取会话记录失败')
    return await response.json()
  }


  const deleteSession = async (sessionId: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error('删除会话失败')
  }

  return {
    loadingSessions,
    listSessions,
    getSessionHistory,
    deleteSession
  }
}


/**
 * URL2MD API
 */
export function useUrl2MdApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const parseUrl = async (url: string): Promise<Url2MdParseResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/url2md/parse`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url })
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.message || '解析失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '解析失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    parseUrl
  }
}

/**
 * Settings API
 */
export function useSettingsApi() {
  const loadingSettings = ref(false)
  const saving = ref(false)

  const fetchSettings = async (): Promise<Record<string, string>> => {
    loadingSettings.value = true
    try {
      const response = await fetch(`${API_BASE}/settings`)
      if (!response.ok) throw new Error('获取配置失败')
      const data: SettingsResponse = await response.json()
      return data.settings
    } finally {
      loadingSettings.value = false
    }
  }

  const updateSettings = async (settings: Record<string, string>): Promise<Record<string, string>> => {
    saving.value = true
    try {
      const response = await fetch(`${API_BASE}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings })
      })
      if (!response.ok) throw new Error('更新配置失败')
      const data: SettingsResponse = await response.json()
      return data.settings
    } finally {
      saving.value = false
    }
  }

  return {
    loadingSettings,
    saving,
    fetchSettings,
    updateSettings
  }
}

/**
 * Tracing API
 */
export function useTracingApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const listTraces = async (params: {
    page?: number
    limit?: number
    status?: TraceStatus | ''
    session_id?: string
    run_id?: string
    agent_id?: string
    start_time?: string
    end_time?: string
  }): Promise<TraceListResponse> => {
    loading.value = true
    error.value = null
    try {
      const qs = new URLSearchParams()
      if (params.page) qs.set('page', String(params.page))
      if (params.limit) qs.set('limit', String(params.limit))
      if (params.status) qs.set('status', String(params.status))
      if (params.session_id) qs.set('session_id', params.session_id)
      if (params.run_id) qs.set('run_id', params.run_id)
      if (params.agent_id) qs.set('agent_id', params.agent_id)
      if (params.start_time) qs.set('start_time', params.start_time)
      if (params.end_time) qs.set('end_time', params.end_time)

      const response = await fetch(`${API_BASE}/traces?${qs.toString()}`)
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || data.message || '获取 traces 失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '获取 traces 失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  const getTrace = async (traceId: string): Promise<TraceDetailResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(`${API_BASE}/traces/${encodeURIComponent(traceId)}`)
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || data.message || '获取 trace 详情失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '获取 trace 详情失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    listTraces,
    getTrace
  }
}

/**
 * Skills 管理 API
 */
export function useSkillsApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const toggling = ref(false)

  const fetchSkills = async (): Promise<SkillListResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(`${API_BASE}/skills`)
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '获取 Skills 列表失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '获取 Skills 列表失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  const toggleSkill = async (skillName: string, enabled: boolean): Promise<SkillToggleResponse> => {
    toggling.value = true
    error.value = null
    try {
      const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}/toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '切换 Skill 状态失败')
      }
      return await response.json()
    } catch (err: any) {
      error.value = err.message || '切换 Skill 状态失败'
      throw err
    } finally {
      toggling.value = false
    }
  }

  return {
    loading,
    error,
    toggling,
    fetchSkills,
    toggleSkill
  }
}
