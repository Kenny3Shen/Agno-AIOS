import { ref } from 'vue'
import type { CveSearchParams, CveSearchResponse, AssetSearchParams, AssetSearchResponse, Url2MdParseResponse, UpdateResponse, SettingsResponse, ChatSession, Message } from '../types'

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
