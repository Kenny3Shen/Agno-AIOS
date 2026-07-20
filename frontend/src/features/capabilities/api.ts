import { jsonInit, requestJson } from '@/shared/api/client'
import type { ResourceVisibility } from '@/shared/types/common'

export type CapabilityKind = 'skill' | 'mcp_server'
export type CapabilityPreference = 'enabled' | 'disabled'
export type CapabilityUnavailableReason = 'platform_disabled' | 'user_disabled' | null

export interface CapabilityItem {
  kind: CapabilityKind
  capability_key: string
  name: string
  description: string
  platform_enabled: boolean
  preference: CapabilityPreference
  effective_enabled: boolean
  unavailable_reason: CapabilityUnavailableReason
  visibility: ResourceVisibility
  owner_user_id: string
  server_id: number | null
  namespace: string | null
  risk: 'standard' | 'script' | 'builtin' | 'external' | string
}

export const listCapabilities = async () =>
  (await requestJson<{ data: CapabilityItem[] }>('/me/capabilities')).data

export const setCapabilityPreference = (
  item: Pick<CapabilityItem, 'kind' | 'capability_key'>,
  state: CapabilityPreference,
) =>
  requestJson<CapabilityItem>(
    `/me/capabilities/${item.kind}/${encodeURIComponent(item.capability_key)}/preference`,
    jsonInit('PUT', { state }),
  )
