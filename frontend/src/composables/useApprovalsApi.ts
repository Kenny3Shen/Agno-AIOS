import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  ApprovalListResponse,
  ApprovalListParams,
  ApprovalRecord,
  ApprovalResolveRequest
} from '../types'

/**
 * Agno approvals page API.
 */
export function useApprovalsApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const listApprovals = async (params: ApprovalListParams = {}): Promise<ApprovalListResponse> => {
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
      const response = await apiFetch(`/approvals${suffix}`)
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('pagePayloadLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('pagePayloadLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const getApproval = async (id: string): Promise<ApprovalRecord> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/approvals/${encodeURIComponent(id)}`)
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('pagePayloadLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('pagePayloadLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const resolveApproval = async (id: string, payload: ApprovalResolveRequest): Promise<ApprovalRecord> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/approvals/${encodeURIComponent(id)}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, apiMessage('pagePayloadLoadFailed')))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('pagePayloadLoadFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    listApprovals,
    getApproval,
    resolveApproval
  }
}
