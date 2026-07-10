import type { McpConfig, McpServer } from './api'

export interface AvailableMcpService {
  key: string
  name: string
  source: string
  kind: 'built-in' | 'external'
}

export function manifestServiceNames(server: Pick<McpServer, 'manifest' | 'name'>): string[] {
  const manifestServers = server.manifest.mcpServers
  const names = manifestServers && typeof manifestServers === 'object' && !Array.isArray(manifestServers)
    ? Object.keys(manifestServers)
    : []
  return names.length > 0 ? names : [server.name]
}

export function getAvailableMcpServices(config?: McpConfig): AvailableMcpService[] {
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
