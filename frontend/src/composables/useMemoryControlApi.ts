import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  MemoryPayloadResponse,
  MemoryDeleteResponse,
  MemoryQueryParams,
  MemoryUpdateRequest,
  MemoryUpdateResponse
} from '../types'

/**
 * Agno user memory page API.
 */
export function useMemoryControlApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchMemory = async (params: MemoryQueryParams = {}): Promise<MemoryPayloadResponse> => {
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
      const response = await apiFetch(`/memory${suffix}`)
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

  const deleteMemory = async (memoryId: string, userId?: string): Promise<MemoryDeleteResponse> => {
    loading.value = true
    error.value = null
    const query = new URLSearchParams()
    if (userId) query.set('user_id', userId)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    try {
      const response = await apiFetch(`/memory/${encodeURIComponent(memoryId)}${suffix}`, {
        method: 'DELETE',
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

  const updateMemory = async (memoryId: string, payload: MemoryUpdateRequest): Promise<MemoryUpdateResponse> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/memory/${encodeURIComponent(memoryId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
    fetchMemory,
    deleteMemory,
    updateMemory
  }
}
