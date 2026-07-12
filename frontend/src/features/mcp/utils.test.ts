import { describe, expect, it } from 'vitest'
import { getAvailableMcpServices, manifestServiceNames } from './utils'

describe('available MCP services', () => {
  it('keeps enabled built-ins and expands enabled external manifests', () => {
    const services = getAvailableMcpServices({
      services: { basic: true, playbook: false },
      mcp_servers: [
        {
          name: 'local-tools',
          description: '',
          kind: 'mcp-json',
          enabled: true,
          visibility: 'private',
          owner_user_id: 'u1',
          can_manage: true,
          manifest: { mcpServers: { filesystem: {}, browser: {} } },
        },
      ],
    })

    expect(services.map((service) => service.name)).toEqual(['basic', 'filesystem', 'browser'])
  })

  it('falls back to the server name when a manifest has no explicit service map', () => {
    expect(
      manifestServiceNames({
        name: 'uploaded-server',
        manifest: {},
      })
    ).toEqual(['uploaded-server'])
  })
})
