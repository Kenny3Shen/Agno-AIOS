import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '../lib/apiClient'
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
  MemoryControlResponse,
  MemoryQueryParams,
  McpServiceId,
  McpServiceStatusResponse,
  McpTokenInfo,
  McpTokenIssueResponse,
  Message,
  ModelConfig,
  ModelConnectivityTestResponse,
  ModelConfigResponse,
  OsControlModule,
  OsControlResponse,
  ScheduleCreateRequest,
  ScheduleCreateResponse,
  ScheduleRunsResponse,
  ScheduleUpdateRequest,
  SchedulerRun,
  SchedulerSchedule,
  SettingsResponse,
  SkillListResponse,
  SkillToggleResponse,
  TraceDetailResponse,
  TraceListResponse,
  TraceStatus,
  UpdateResponse,
  UploadResultResponse,
  Url2MdParseResponse,
} from '../types'

type ApiFallbackKey =
  | 'cveSearchFailed'
  | 'cveUpdateFailed'
  | 'assetSearchFailed'
  | 'chatHttpFailed'
  | 'chatSendFailed'
  | 'osControlLoadFailed'
  | 'chatSessionsLoadFailed'
  | 'chatHistoryLoadFailed'
  | 'chatArchiveFailed'
  | 'urlParseFailed'
  | 'settingsLoadFailed'
  | 'settingsUpdateFailed'
  | 'modelsLoadFailed'
  | 'modelsSaveFailed'
  | 'modelsTestFailed'
  | 'tracesLoadFailed'
  | 'traceDetailLoadFailed'
  | 'skillsLoadFailed'
  | 'skillToggleFailed'
  | 'knowledgeRequestFailed'
  | 'knowledgeLoadFailed'
  | 'knowledgeWriteFailed'
  | 'knowledgeImportFailed'
  | 'knowledgeDeleteFailed'
  | 'knowledgeClearFailed'
  | 'knowledgeSearchFailed'
  | 'mcpRequestFailed'
  | 'mcpConfigLoadFailed'
  | 'mcpConfigUpdateFailed'
  | 'mcpTokenLoadFailed'
  | 'mcpTokenIssueFailed'
  | 'mcpTokenDeleteFailed'
  | 'mcpHiAgentLoadFailed'
  | 'mcpHiAgentAddFailed'
  | 'mcpHiAgentUpdateFailed'
  | 'mcpHiAgentDeleteFailed'

const useApiMessage = () => {
  const { t } = useI18n()
  return (key: ApiFallbackKey, params?: Record<string, string | number>) => {
    return params ? t(`api.errors.${key}`, params) : t(`api.errors.${key}`)
  }
}

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

const cleanParam = (value: string | null | undefined) => {
  return (value ?? '').trim()
}

/**
 * CVE search API.
 */
export function useCveApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const searchCve = async (params: CveSearchParams): Promise<CveSearchResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch('/cve/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(params)
      })
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, apiMessage('cveSearchFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('cveSearchFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const updateDatabase = async (): Promise<UpdateResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch('/cve/update', {
        method: 'POST'
      })
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, apiMessage('cveUpdateFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('cveUpdateFailed'))
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
 * Asset search API.
 */
export function useAssetApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const searchAsset = async (params: AssetSearchParams): Promise<AssetSearchResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch('/asset/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(params)
      })
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, apiMessage('assetSearchFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('assetSearchFailed'))
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
 * LLM chat API.
 */
export function useChatApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const sendMessageStream = async (
    message: string,
    sessionId: string | null,
    modelId: string | null,
    onChunk: (chunk: string) => void
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          model_id: modelId,
        })
      })

      if (!response.ok || !response.body) {
        throw new Error(apiMessage('chatHttpFailed', { status: response.status }))
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
      error.value = messageFromUnknown(err, apiMessage('chatSendFailed'))
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
 * AgentOS control-plane API.
 */
export function useOsControlApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchModule = async (module: OsControlModule): Promise<OsControlResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch(`/os/${module}`)
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const fetchMemory = async (params: MemoryQueryParams = {}): Promise<MemoryControlResponse> => {
    loading.value = true
    error.value = null

    const query = new URLSearchParams()
    if (params.user_id) query.set('user_id', params.user_id)
    if (params.topic) query.set('topic', params.topic)
    if (params.search) query.set('search', params.search)
    if (params.page) query.set('page', String(params.page))
    if (params.limit) query.set('limit', String(params.limit))

    try {
      const suffix = query.toString() ? `?${query.toString()}` : ''
      const response = await apiFetch(`/os/memory${suffix}`)
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const createSchedule = async (payload: ScheduleCreateRequest): Promise<ScheduleCreateResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch('/os/scheduler', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const updateSchedule = async (id: string, payload: ScheduleUpdateRequest): Promise<SchedulerSchedule> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/scheduler/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const setScheduleEnabled = async (id: string, enabled: boolean): Promise<SchedulerSchedule> => {
    loading.value = true
    error.value = null
    try {
      const action = enabled ? 'enable' : 'disable'
      const response = await apiFetch(`/os/scheduler/${encodeURIComponent(id)}/${action}`, { method: 'POST' })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const triggerSchedule = async (id: string): Promise<SchedulerRun> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/scheduler/${encodeURIComponent(id)}/trigger`, { method: 'POST' })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const deleteSchedule = async (id: string): Promise<void> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/scheduler/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const listScheduleRuns = async (id: string): Promise<ScheduleRunsResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/scheduler/${encodeURIComponent(id)}/runs`)
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('osControlLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    fetchModule,
    fetchMemory,
    createSchedule,
    updateSchedule,
    setScheduleEnabled,
    triggerSchedule,
    deleteSchedule,
    listScheduleRuns
  }
}

/**
 * Chat session history API.
 */
export function useChatHistory() {
  const apiMessage = useApiMessage()
  const loadingSessions = ref(false)

  const listSessions = async (options: { includeRuns?: boolean } = {}): Promise<ChatSession[]> => {
    loadingSessions.value = true
    try {
      const qs = new URLSearchParams()
      if (options.includeRuns) qs.set('include_runs', 'true')
      const response = await apiFetch(`/chat/sessions${qs.size ? `?${qs.toString()}` : ''}`)
      if (!response.ok) throw new Error(apiMessage('chatSessionsLoadFailed'))
      return await response.json()
    } finally {
      loadingSessions.value = false
    }
  }

  const getSessionHistory = async (sessionId: string): Promise<Message[]> => {
    const response = await apiFetch(`/chat/sessions/${sessionId}`)
    if (!response.ok) throw new Error(apiMessage('chatHistoryLoadFailed'))
    return await response.json()
  }


  const archiveSession = async (sessionId: string): Promise<void> => {
    const response = await apiFetch(`/chat/sessions/${sessionId}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error(apiMessage('chatArchiveFailed'))
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
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const parseUrl = async (url: string): Promise<Url2MdParseResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch('/url2md/parse', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url })
      })
      if (!response.ok) {
        const data: unknown = await response.json()
        throw new Error(messageFromResponse(data, apiMessage('urlParseFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('urlParseFailed'))
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

/**
 * Tracing API
 */
export function useTracingApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const listTraces = async (params: {
    page?: number
    limit?: number
    status?: TraceStatus | ''
    session_id?: string
    run_id?: string
    agent_id?: string
    team_id?: string
    workflow_id?: string
    user_id?: string
    start_time?: string
    end_time?: string
  }): Promise<TraceListResponse> => {
    loading.value = true
    error.value = null
    try {
      const qs = new URLSearchParams()
      if (params.page) qs.set('page', String(params.page))
      if (params.limit) qs.set('limit', String(params.limit))
      const status = cleanParam(params.status)
      const sessionId = cleanParam(params.session_id)
      const runId = cleanParam(params.run_id)
      const agentId = cleanParam(params.agent_id)
      const teamId = cleanParam(params.team_id)
      const workflowId = cleanParam(params.workflow_id)
      const userId = cleanParam(params.user_id)
      const startTime = cleanParam(params.start_time)
      const endTime = cleanParam(params.end_time)
      if (status) qs.set('status', status)
      if (sessionId) qs.set('session_id', sessionId)
      if (runId) qs.set('run_id', runId)
      if (agentId) qs.set('agent_id', agentId)
      if (teamId) qs.set('team_id', teamId)
      if (workflowId) qs.set('workflow_id', workflowId)
      if (userId) qs.set('user_id', userId)
      if (startTime) qs.set('start_time', startTime)
      if (endTime) qs.set('end_time', endTime)

      const response = await apiFetch(`/traces?${qs.toString()}`)
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('tracesLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('tracesLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const getTrace = async (traceId: string): Promise<TraceDetailResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/traces/${encodeURIComponent(traceId)}`)
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('traceDetailLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('traceDetailLoadFailed'))
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

  const uploadSkill = async (payload: { name: string; file: File }): Promise<UploadResultResponse> => {
    loading.value = true
    error.value = null
    const form = new FormData()
    form.append('name', payload.name)
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

  return {
    loading,
    error,
    toggling,
    fetchSkills,
    toggleSkill,
    uploadSkill
  }
}

/**
 * RAG knowledge management API.
 */
export function useKnowledgeApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const request = async <T>(path = '', options: RequestInit = {}, fallback = apiMessage('knowledgeRequestFailed')): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/knowledge${path}`, {
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

  const fetchKnowledge = () => request<KnowledgeStatusResponse>('', {}, apiMessage('knowledgeLoadFailed'))

  const addTextDocument = (payload: KnowledgeTextRequest) => request<KnowledgeDocument>('/documents/text', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeWriteFailed'))

  const addFileDocument = (payload: KnowledgeFileRequest) => request<KnowledgeDocument>('/documents/file', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeImportFailed'))

  const deleteKnowledgeDocument = (docId: string) => request<{ success: boolean }>(`/documents/${encodeURIComponent(docId)}`, {
    method: 'DELETE'
  }, apiMessage('knowledgeDeleteFailed'))

  const clearKnowledge = () => request<{ documents: number; chunks: number }>('', {
    method: 'DELETE'
  }, apiMessage('knowledgeClearFailed'))

  const searchKnowledge = (query: string, limit: number, searchType?: string) => request<KnowledgeSearchResponse>('/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit, search_type: searchType || undefined })
  }, apiMessage('knowledgeSearchFailed'))

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

  const listHiAgents = () => request<HiAgentEntry[]>('/hiagent', {}, apiMessage('mcpHiAgentLoadFailed'))

  const addHiAgent = (entry: HiAgentEntry) => request<{ success: boolean }>('/hiagent/add', {
    method: 'POST',
    body: JSON.stringify(entry)
  }, apiMessage('mcpHiAgentAddFailed'))

  const updateHiAgent = (payload: Partial<HiAgentEntry> & { target_url?: string; url: string }) => request<{ success: boolean }>('/hiagent/update', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('mcpHiAgentUpdateFailed'))

  const deleteHiAgent = (url: string) => request<{ success: boolean }>('/hiagent/delete', {
    method: 'POST',
    body: JSON.stringify({ url })
  }, apiMessage('mcpHiAgentDeleteFailed'))

  const uploadMcp = (payload: { name: string; url?: string; description?: string; manifest?: string }) => request<UploadResultResponse>('/upload', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('mcpRequestFailed'))

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
    deleteHiAgent,
    uploadMcp
  }
}
