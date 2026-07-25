import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { SkillsPage } from './SkillsPage'

describe('SkillsPage', () => {
  it('shows the delete control only when the server grants admin delete permission', async () => {
    server.use(
      http.get('/api/skills', () =>
        HttpResponse.json({
          data: [
            {
              name: 'web-search',
              description: 'Searches the web',
              enabled: true,
              has_scripts: false,
              scripts: [],
              skill_markdown: '# Web search',
              visibility: 'private',
              capability_key: 'web-search',
              owner_user_id: 'admin-1',
              can_manage: true,
              can_delete: true,
            },
          ],
          meta: { page: 1, limit: 1, total_pages: 1, total_count: 1, search_time_ms: 0 },
        })
      ),
      http.get('/api/me/capabilities', () =>
        HttpResponse.json({
          data: [
            {
              kind: 'skill',
              capability_key: 'web-search',
              name: 'web-search',
              description: 'Searches the web',
              platform_enabled: true,
              preference: 'enabled',
              effective_enabled: true,
              unavailable_reason: null,
              visibility: 'private',
              owner_user_id: 'admin-1',
              server_id: null,
              namespace: null,
              risk: 'standard',
            },
          ],
        })
      )
    )

    renderWithQuery(<SkillsPage />)
    expect(await screen.findByLabelText('删除技能 web-search')).toBeTruthy()
  })

  it('keeps owner skills read-only without skill:write', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({
          id: 'owner-1',
          email: 'owner@example.com',
          role: 'user',
          scopes: ['skill:read', 'skill:submit'],
          is_active: true,
        })
      ),
      http.get('/api/skills', () =>
        HttpResponse.json({
          data: [
            {
              name: 'web-search',
              description: 'Searches the web',
              enabled: true,
              has_scripts: false,
              scripts: [],
              skill_markdown: '# Web search',
              visibility: 'private',
              capability_key: 'web-search',
              owner_user_id: 'owner-1',
              can_manage: true,
              can_delete: false,
            },
          ],
          meta: { page: 1, limit: 1, total_pages: 1, total_count: 1, search_time_ms: 0 },
        })
      ),
      http.get('/api/me/capabilities', () =>
        HttpResponse.json({
          data: [
            {
              kind: 'skill',
              capability_key: 'web-search',
              name: 'web-search',
              description: 'Searches the web',
              platform_enabled: true,
              preference: 'enabled',
              effective_enabled: true,
              unavailable_reason: null,
              visibility: 'private',
              owner_user_id: 'owner-1',
              server_id: null,
              namespace: null,
              risk: 'standard',
            },
          ],
        })
      )
    )

    renderWithQuery(<SkillsPage />)

    await screen.findByRole('button', { name: /上传技能/ })
    expect(await screen.findByText('web-search')).toBeTruthy()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.getByText('私有')).toBeTruthy()
  })
})
