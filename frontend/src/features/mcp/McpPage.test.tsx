import { screen } from '@testing-library/react'
import { user } from '@/test/user'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { McpPage } from './McpPage'

describe('McpPage component permissions', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/mcp/config', () =>
        HttpResponse.json({
          services: {},
          mcp_servers: [
            {
              id: 1,
              name: 'Shared MCP',
              namespace: 'shared',
              description: '',
              server_type: 'external',
              kind: 'external',
              transport: 'stdio',
              enabled: true,
              visibility: 'public',
              owner_user_id: 'owner-1',
              can_manage: false,
              can_delete: false,
              manifest: {},
            },
          ],
          mcp_url: '',
          fastmcp: '',
          config_store: 'postgresql',
        })
      ),
      http.get('/api/mcp/components', () =>
        HttpResponse.json({
          data: [
            {
              key: 'tool:shared.inspect',
              type: 'tool',
              name: 'shared.inspect',
              title: 'Inspect',
              namespace: 'shared',
              server_id: 1,
              tags: [],
              icons: [],
              meta: {},
              enabled: true,
            },
          ],
          meta: { page: 1, limit: 1, total_pages: 1, total_count: 1, search_time_ms: 0 },
        })
      ),
      http.get('/api/mcp/tokens', () =>
        HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 1, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      ),
      http.get('/api/me/capabilities', () =>
        HttpResponse.json({
          data: [
            {
              kind: 'mcp_tool',
              capability_key: 'tool:shared.inspect',
              name: 'shared.inspect',
              description: '',
              platform_enabled: true,
              preference: 'enabled',
              effective_enabled: true,
              unavailable_reason: null,
              visibility: 'private',
              owner_user_id: 'owner-1',
              server_id: 1,
              namespace: 'shared',
              risk: 'standard',
            },
          ],
        })
      )
    )
  })

  it('keeps owner MCP controls read-only without mcp:write', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({
          id: 'owner-1',
          email: 'owner@example.com',
          role: 'user',
          scopes: ['mcp:read', 'mcp:submit'],
          is_active: true,
        })
      ),
      http.get('/api/mcp/config', () =>
        HttpResponse.json({
          services: {},
          mcp_servers: [
            {
              id: 1,
              name: 'Shared MCP',
              namespace: 'shared',
              description: '',
              server_type: 'external',
              kind: 'external',
              transport: 'stdio',
              enabled: true,
              visibility: 'private',
              owner_user_id: 'owner-1',
              can_manage: true,
              can_delete: false,
              manifest: {},
            },
          ],
          mcp_url: '',
          fastmcp: '',
          config_store: 'postgresql',
        })
      )
    )
    renderWithQuery(<McpPage />)

    await screen.findByRole('button', { name: /添加 Server/ })
    expect(await screen.findByLabelText('shared.inspect enabled')).toBeTruthy()
    expect(screen.queryByRole('switch', { name: 'shared.inspect enabled' })).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()

    await user.click(screen.getByRole('button', { name: /添加 Server/ }))
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '连接测试' })).toBeNull()
  })
})

describe('McpPage token issue failures', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/mcp/config', () =>
        HttpResponse.json({
          services: {},
          mcp_servers: [],
          mcp_url: '',
          fastmcp: '',
          config_store: 'postgresql',
        })
      ),
      http.get('/api/mcp/components', () =>
        HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 1, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      ),
      http.get('/api/mcp/tokens', () =>
        HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 1, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      )
    )
  })

  it('surfaces issue-token API failures to the operator', async () => {
    server.use(http.post('/api/mcp/tokens/issue', () => HttpResponse.json({ detail: 'token mint denied' }, { status: 500 })))

    renderWithQuery(<McpPage />)
    await user.click(await screen.findByRole('button', { name: /签发令牌|Issue token/i }))
    const dialog = await screen.findByRole('dialog')
    const nameInput = dialog.querySelector('input') as HTMLInputElement
    await user.clear(nameInput)
    await user.type(nameInput, 'ops-token')
    // Modal form uses htmlType=submit with i18n key issue ("签发" / "Issue")
    await user.click(dialog.querySelector('button[type="submit"]') as HTMLButtonElement)
    expect(await screen.findByText('token mint denied')).toBeTruthy()
  })
})
