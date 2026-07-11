import type { JsonRecord } from '@/shared/types/common'

export interface AvailableMcpService {
  key: string
  name: string
  source: string
  kind: 'built-in' | 'external'
}

export function manifestServiceNames(server: { manifest: JsonRecord; name: string }): string[] {
  const manifestServers = server.manifest.mcpServers
  const names = manifestServers && typeof manifestServers === 'object' && !Array.isArray(manifestServers)
    ? Object.keys(manifestServers)
    : []
  return names.length > 0 ? names : [server.name]
}

export function getAvailableMcpServices(config?: {
  services: Record<string, boolean>
  mcp_servers?: Array<{
    name: string
    enabled: boolean
    manifest: JsonRecord
    description?: string
    kind?: string
    visibility?: string
    owner_user_id?: string
    can_manage?: boolean
  }>
}): AvailableMcpService[] {
  if (!config) return []

  const builtIn = Object.entries(config.services)
    .filter(([, enabled]) => enabled)
    .map(([name]) => ({ key: `built-in:${name}`, name, source: 'T.A.I.S runtime', kind: 'built-in' as const }))

  const external = (config.mcp_servers ?? []).flatMap((server) => {
    if (!server.enabled) return []
    return manifestServiceNames(server).map((name) => ({
      key: `external:${server.name}:${name}`,
      name,
      source: server.name,
      kind: 'external' as const,
    }))
  })

  return [...builtIn, ...external]
}
