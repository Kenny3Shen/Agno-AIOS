import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse, cleanParam } from './useApiCore'
import type {
  TraceDetailResponse,
  TraceListResponse,
  TraceStatus
} from '../types'

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
