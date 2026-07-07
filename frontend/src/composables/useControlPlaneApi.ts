import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  OsControlModule,
  OsControlResponse
} from '../types'

export type ControlPlanePayloadModule = Exclude<OsControlModule, 'memory' | 'approvals' | 'scheduler'>

/**
 * AIOS/AgentOS read-only control-plane payload API.
 */
export function useControlPlaneApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchModule = async (module: ControlPlanePayloadModule): Promise<OsControlResponse> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch(`/os/${module}`)
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
    fetchModule
  }
}
