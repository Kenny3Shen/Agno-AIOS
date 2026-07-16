import { jsonInit, requestJson } from '@/shared/api/client'
import type { JsonRecord, ResourceVisibility } from '@/shared/types/common'

export interface McpServer {
  id: number
  name: string
  namespace: string
  description: string
  server_type: 'builtin' | 'external'
  kind: 'builtin' | 'external'
  transport: string
  enabled: boolean
  visibility: ResourceVisibility
  owner_user_id: string
  can_manage: boolean
  can_delete?: boolean
  manifest: JsonRecord
}

export interface McpConfig {
  services: Record<string, boolean>
  mcp_servers: McpServer[]
  mcp_url: string
  fastmcp: string
  config_store: string
}

export interface McpComponent {
  key: string
  type: 'tool' | 'resource' | 'template' | 'prompt'
  name: string
  title?: string | null
  description?: string | null
  namespace?: string | null
  server_id?: number | null
  tags: string[]
  icons: JsonRecord[]
  annotations?: JsonRecord | null
  input_schema?: JsonRecord | null
  output_schema?: JsonRecord | null
  meta: JsonRecord
  enabled: boolean
}

export interface McpToken {
  id: number
  name: string
  created_at: number
  expires_at: number
}

/** The result of submitting an external MCP server for administrator review. */
export interface UploadApprovalSubmission {
  success?: boolean
  approval_id?: string
  id?: string
  status?: string
}

export const getConfig = () => requestJson<McpConfig>('/mcp/config')
export const listComponents = async (namespace?: string) =>
  (
    await requestJson<{ data: McpComponent[] }>(
      `/mcp/components${namespace ? `?namespace=${encodeURIComponent(namespace)}` : ''}`
    )
  ).data ?? []
export const updateConfig = (id: string, enabled: boolean) => requestJson('/mcp/config', jsonInit('POST', { id, enabled }))
export const setServerEnabled = (id: number, enabled: boolean) =>
  requestJson(`/mcp/servers/${id}/enabled`, jsonInit('PUT', { server_id: id, enabled }))
export const deleteServer = (id: number) => requestJson<{ success: boolean }>(`/mcp/servers/${id}`, { method: 'DELETE' })
export const setComponentEnabled = (component: McpComponent, enabled: boolean) =>
  requestJson(
    `/mcp/components/${component.type}/${encodeURIComponent(component.name)}/enabled`,
    jsonInit('PUT', { server_id: component.server_id, enabled })
  )
export const callTool = (name: string, argumentsValue: JsonRecord) =>
  requestJson(`/mcp/tools/${encodeURIComponent(name)}/call`, jsonInit('POST', { arguments: argumentsValue }))
export const listTokens = async () =>
  (await requestJson<{ data: McpToken[] }>('/mcp/tokens')).data ?? []
export const issueToken = (name: string, expires_in: number) =>
  requestJson<{ token: string }>('/mcp/tokens/issue', jsonInit('POST', { name, expires_in }))
export const deleteToken = (id: number) => requestJson('/mcp/tokens/delete', jsonInit('POST', { id }))
export const uploadServer = (payload: { name: string; description: string; manifest: string; visibility: ResourceVisibility }) =>
  requestJson<UploadApprovalSubmission>('/mcp/upload', jsonInit('POST', payload))
export const testServer = (payload: { name: string; description: string; manifest: string; visibility: ResourceVisibility }) =>
  requestJson<{ success: boolean; tools: string[] }>('/mcp/servers/test', jsonInit('POST', payload))
export const setServerVisibility = (name: string, visibility: ResourceVisibility) =>
  requestJson(`/mcp/servers/${encodeURIComponent(name)}/visibility`, jsonInit('PUT', { visibility }))
