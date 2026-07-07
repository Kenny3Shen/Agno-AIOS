import { ref } from 'vue'
import { apiFetch, agentOsFetch } from '../lib/apiClient'
import {
  agentOsScheduleRunsToScheduleRunsResponse,
  agentOsSchedulesToOsControlResponse,
  buildAgentOsScheduleCreateBody,
  buildAgentOsScheduleUpdateBody,
  normalizeAgentOsSchedule,
  normalizeAgentOsScheduleRun
} from '../modules/schedulerAgentOsApi'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  ApprovalControlResponse,
  ApprovalListParams,
  ApprovalRecord,
  ApprovalResolveRequest,
  MemoryControlResponse,
  MemoryDeleteResponse,
  MemoryQueryParams,
  MemoryUpdateRequest,
  MemoryUpdateResponse,
  OsControlModule,
  OsControlResponse,
  ScheduleCreateRequest,
  ScheduleCreateResponse,
  ScheduleRunsResponse,
  ScheduleUpdateRequest,
  SchedulerRun,
  SchedulerSchedule
} from '../types'

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
      if (module === 'scheduler') {
        const response = await agentOsFetch('/schedules?limit=100&page=1')
        if (!response.ok) {
          const data: unknown = await response.json().catch(() => ({}))
          throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
        }
        const data: unknown = await response.json()
        return agentOsSchedulesToOsControlResponse(data)
      }
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

  const deleteMemory = async (memoryId: string, userId?: string): Promise<MemoryDeleteResponse> => {
    loading.value = true
    error.value = null
    const query = new URLSearchParams()
    if (userId) query.set('user_id', userId)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    try {
      const response = await apiFetch(`/os/memory/${encodeURIComponent(memoryId)}${suffix}`, {
        method: 'DELETE',
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

  const updateMemory = async (memoryId: string, payload: MemoryUpdateRequest): Promise<MemoryUpdateResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/memory/${encodeURIComponent(memoryId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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

  const listApprovals = async (params: ApprovalListParams = {}): Promise<ApprovalControlResponse> => {
    loading.value = true
    error.value = null
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.source_type) query.set('source_type', params.source_type)
    if (params.approval_type) query.set('approval_type', params.approval_type)
    if (params.pause_type) query.set('pause_type', params.pause_type)
    if (params.agent_id) query.set('agent_id', params.agent_id)
    if (params.team_id) query.set('team_id', params.team_id)
    if (params.workflow_id) query.set('workflow_id', params.workflow_id)
    if (params.user_id) query.set('user_id', params.user_id)
    if (params.schedule_id) query.set('schedule_id', params.schedule_id)
    if (params.run_id) query.set('run_id', params.run_id)
    if (params.page) query.set('page', String(params.page))
    if (params.limit) query.set('limit', String(params.limit))
    try {
      const suffix = query.toString() ? `?${query.toString()}` : ''
      const response = await apiFetch(`/os/approvals${suffix}`)
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

  const getApproval = async (id: string): Promise<ApprovalRecord> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/approvals/${encodeURIComponent(id)}`)
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

  const resolveApproval = async (id: string, payload: ApprovalResolveRequest): Promise<ApprovalRecord> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/os/approvals/${encodeURIComponent(id)}/resolve`, {
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

  const createSchedule = async (payload: ScheduleCreateRequest): Promise<ScheduleCreateResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await agentOsFetch('/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildAgentOsScheduleCreateBody(payload))
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      let schedule = normalizeAgentOsSchedule(await response.json())
      if (payload.enabled === false && schedule.id) {
        const disabled = await agentOsFetch(`/schedules/${encodeURIComponent(schedule.id)}/disable`, { method: 'POST' })
        if (!disabled.ok) {
          const data: unknown = await disabled.json().catch(() => ({}))
          throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
        }
        schedule = normalizeAgentOsSchedule({ ...schedule, ...(await disabled.json()) })
      }
      return schedule
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
      const response = await agentOsFetch(`/schedules/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildAgentOsScheduleUpdateBody(payload))
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return normalizeAgentOsSchedule(await response.json())
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
      const response = await agentOsFetch(`/schedules/${encodeURIComponent(id)}/${action}`, { method: 'POST' })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      const state = await response.json()
      const detail = await agentOsFetch(`/schedules/${encodeURIComponent(id)}`)
      if (!detail.ok) {
        return normalizeAgentOsSchedule(state)
      }
      return normalizeAgentOsSchedule(await detail.json())
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
      const response = await agentOsFetch(`/schedules/${encodeURIComponent(id)}/trigger`, { method: 'POST' })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      return normalizeAgentOsScheduleRun(await response.json())
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
      const response = await agentOsFetch(`/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' })
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
      const response = await agentOsFetch(`/schedules/${encodeURIComponent(id)}/runs?limit=100&page=1`)
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      const data: unknown = await response.json()
      return agentOsScheduleRunsToScheduleRunsResponse(data)
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
    deleteMemory,
    updateMemory,
    listApprovals,
    getApproval,
    resolveApproval,
    createSchedule,
    updateSchedule,
    setScheduleEnabled,
    triggerSchedule,
    deleteSchedule,
    listScheduleRuns
  }
}
