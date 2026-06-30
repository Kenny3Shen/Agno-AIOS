import { ref } from 'vue'
import type {
  AssetSearchParams,
  AssetSearchResponse,
  ChatSession,
  CveSearchParams,
  CveSearchResponse,
  HiAgentEntry,
  KnowledgeDocument,
  KnowledgeFileRequest,
  KnowledgeSearchResponse,
  KnowledgeStatusResponse,
  KnowledgeTextRequest,
  McpServiceId,
  McpServiceStatusResponse,
  McpTokenInfo,
  McpTokenIssueResponse,
  Message,
  ModelConfigResponse,
  OsControlModule,
  OsControlResponse,
  SettingsResponse,
  SkillListResponse,
  SkillToggleResponse,
  TraceDetailResponse,
  TraceListResponse,
  TraceStatus,
  UpdateResponse,
  Url2MdParseResponse,
} from '../types'

const API_BASE = '/api'

const messageFromUnknown = (err: unknown, fallback: string) => {
  if (err instanceof Error && err.message) return err.message
  return fallback
}

const messageFromResponse = (data: unknown, fallback: string) => {
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    const detail = record.detail
    const message = record.message
    if (typeof detail === 'string' && detail) return detail
    if (typeof message === 'string' && message) return message
    if (detail && typeof detail === 'object') {
      const detailRecord = detail as Record<string, unknown>
      const detailError = detailRecord.error
      const detailMessage = detailRecord.message
      if (typeof detailError === 'string' && detailError) return detailError
      if (typeof detailMessage === 'string' && detailMessage) return detailMessage
    }
  }
  return fallback
}

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
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, '搜索失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '搜索失败')
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
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, '更新失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '更新失败')
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
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, '搜索失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '搜索失败')
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
    modelId: string | null,
    userId: string | null,
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
        body: JSON.stringify({
          message,
          session_id: sessionId,
          model_id: modelId,
          user_id: userId,
        })
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
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '发送失败')
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
 * AgentOS 控制面 API
 */
export function useOsControlApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchModule = async (module: OsControlModule): Promise<OsControlResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/os/${module}`)
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, '加载控制面失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '加载控制面失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    fetchModule
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


  const archiveSession = async (sessionId: string, userId: string | null = null): Promise<void> => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
    const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}${query}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error('归档会话失败')
  }

  return {
    loadingSessions,
    listSessions,
    getSessionHistory,
    archiveSession
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
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, '解析失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '解析失败')
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

  const fetchModels = async (): Promise<ModelConfigResponse> => {
    loadingSettings.value = true
    try {
      const response = await fetch(`${API_BASE}/models`)
      if (!response.ok) throw new Error('获取模型配置失败')
      return await response.json()
    } finally {
      loadingSettings.value = false
    }
  }

  const updateModels = async (payload: ModelConfigResponse): Promise<ModelConfigResponse> => {
    saving.value = true
    try {
      const response = await fetch(`${API_BASE}/models`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, '保存模型配置失败'))
      }
      return await response.json()
    } finally {
      saving.value = false
    }
  }

  return {
    loadingSettings,
    saving,
    fetchSettings,
    updateSettings,
    fetchModels,
    updateModels
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
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, '获取 traces 失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '获取 traces 失败')
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
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, '获取 trace 详情失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '获取 trace 详情失败')
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
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, '获取 Skills 列表失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '获取 Skills 列表失败')
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
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, '切换 Skill 状态失败'))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, '切换 Skill 状态失败')
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

/**
 * RAG 知识库管理 API
 */
export function useKnowledgeApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const request = async <T>(path = '', options: RequestInit = {}, fallback = '知识库请求失败'): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(`${API_BASE}/knowledge${path}`, {
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

  const fetchKnowledge = () => request<KnowledgeStatusResponse>('', {}, '获取知识库状态失败')

  const addTextDocument = (payload: KnowledgeTextRequest) => request<KnowledgeDocument>('/documents/text', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, '写入知识文档失败')

  const addFileDocument = (payload: KnowledgeFileRequest) => request<KnowledgeDocument>('/documents/file', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, '导入本地文件失败')

  const deleteKnowledgeDocument = (docId: string) => request<{ success: boolean }>(`/documents/${encodeURIComponent(docId)}`, {
    method: 'DELETE'
  }, '删除知识文档失败')

  const clearKnowledge = () => request<{ documents: number; chunks: number }>('', {
    method: 'DELETE'
  }, '清空知识库失败')

  const searchKnowledge = (query: string, limit: number) => request<KnowledgeSearchResponse>('/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit })
  }, '检索知识库失败')

  return {
    loading,
    error,
    fetchKnowledge,
    addTextDocument,
    addFileDocument,
    deleteKnowledgeDocument,
    clearKnowledge,
    searchKnowledge
  }
}

/**
 * MCP 管理 API
 */
export function useMcpApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const request = async <T>(path: string, options: RequestInit = {}, fallback = 'MCP 请求失败'): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(`${API_BASE}/mcp${path}`, {
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

  const fetchConfig = () => request<McpServiceStatusResponse>('/config', {}, '获取 MCP 配置失败')

  const updateConfig = (id: McpServiceId, enabled: boolean) => request<{ success: boolean; restart_required?: boolean }>('/config', {
    method: 'POST',
    body: JSON.stringify({ id, enabled })
  }, '更新 MCP 配置失败')

  const listTokens = () => request<McpTokenInfo[]>('/tokens', {}, '获取 MCP Token 失败')

  const issueToken = (name: string, expiresIn: number) => request<McpTokenIssueResponse>('/tokens/issue', {
    method: 'POST',
    body: JSON.stringify({ name, expires_in: expiresIn })
  }, '签发 MCP Token 失败')

  const deleteToken = (id: number) => request<{ success: boolean }>('/tokens/delete', {
    method: 'POST',
    body: JSON.stringify({ id })
  }, '删除 MCP Token 失败')

  const listHiAgents = () => request<HiAgentEntry[]>('/hiagent', {}, '获取 Hi-Agent 失败')

  const addHiAgent = (entry: HiAgentEntry) => request<{ success: boolean }>('/hiagent/add', {
    method: 'POST',
    body: JSON.stringify(entry)
  }, '添加 Hi-Agent 失败')

  const updateHiAgent = (payload: Partial<HiAgentEntry> & { target_url?: string; url: string }) => request<{ success: boolean }>('/hiagent/update', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, '更新 Hi-Agent 失败')

  const deleteHiAgent = (url: string) => request<{ success: boolean }>('/hiagent/delete', {
    method: 'POST',
    body: JSON.stringify({ url })
  }, '删除 Hi-Agent 失败')

  return {
    loading,
    error,
    fetchConfig,
    updateConfig,
    listTokens,
    issueToken,
    deleteToken,
    listHiAgents,
    addHiAgent,
    updateHiAgent,
    deleteHiAgent
  }
}
