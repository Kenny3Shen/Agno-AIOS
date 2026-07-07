import { ref } from 'vue'
import { agentOsFetch } from '../lib/apiClient'
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
  OsControlResponse,
  ScheduleCreateRequest,
  ScheduleCreateResponse,
  ScheduleRunsResponse,
  ScheduleUpdateRequest,
  SchedulerRun,
  SchedulerSchedule
} from '../types'

/**
 * Direct AgentOS scheduler API.
 */
export function useSchedulerApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchSchedules = async (): Promise<OsControlResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await agentOsFetch('/schedules?limit=100&page=1')
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('osControlLoadFailed')))
      }
      const data: unknown = await response.json()
      return agentOsSchedulesToOsControlResponse(data)
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
    fetchSchedules,
    createSchedule,
    updateSchedule,
    setScheduleEnabled,
    triggerSchedule,
    deleteSchedule,
    listScheduleRuns
  }
}
