import { jsonInit, requestJson } from '@/shared/api/client'
import type { JsonRecord, ResourceVisibility } from '@/shared/types/common'
export interface McpServer { name: string; description: string; kind: string; enabled: boolean; visibility: ResourceVisibility; owner_user_id: string; can_manage: boolean; manifest: JsonRecord }
export interface McpConfig { services: Record<string, boolean>; mcp_servers?: McpServer[]; mcp_url?: string; fastmcp?: string }
export interface McpToken { id: number; name: string; token: string; created_at: number; expires_at: number }
export const getConfig = () => requestJson<McpConfig>('/mcp/config')
export const updateConfig = (id: string, enabled: boolean) => requestJson('/mcp/config', jsonInit('POST', { id, enabled }))
export const listTokens = () => requestJson<McpToken[]>('/mcp/tokens')
export const issueToken = (name: string, expires_in: number) => requestJson<{ token: string }>('/mcp/tokens/issue', jsonInit('POST', { name, expires_in }))
export const deleteToken = (id: number) => requestJson('/mcp/tokens/delete', jsonInit('POST', { id }))
export const uploadServer = (payload: { name: string; description: string; manifest: string; visibility: ResourceVisibility }) => requestJson('/mcp/upload', jsonInit('POST', payload))
export const setServerVisibility = (name: string, visibility: ResourceVisibility) => requestJson(`/mcp/servers/${encodeURIComponent(name)}/visibility`, jsonInit('PUT', { visibility }))
