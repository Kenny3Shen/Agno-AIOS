import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { user } from '@/test/user'
import { CvePage } from './CvePage'

const emptySearch = {
  data: [],
  meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
}

describe('CvePage', () => {
  it('disables database updates for non-admin users', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({
          id: 'member-1',
          email: 'member@example.com',
          role: 'user',
          scopes: ['cve:read'],
        }),
      ),
      http.post('/api/cve/search', () => HttpResponse.json(emptySearch)),
    )

    renderWithQuery(<CvePage />)

    expect((await screen.findByText('更新数据库')).closest('button')?.disabled).toBe(true)
  })

  it('loads recent CVEs on mount and shows update counts for admin', async () => {
    let searchCalls = 0
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({
          id: 'admin-1',
          email: 'admin@example.com',
          role: 'admin',
          scopes: ['cve:read', 'admin'],
          is_superuser: true,
        }),
      ),
      http.post('/api/cve/search', async () => {
        searchCalls += 1
        return HttpResponse.json({
          data: [
            {
              id: 1,
              cve_id: 'CVE-2026-0001',
              github_url: 'https://github.com/example/1',
              description: 'sample',
              source: 'github',
              create_time: '2026-01-01T00:00:00Z',
            },
          ],
          meta: { page: 1, limit: 20, total_pages: 1, total_count: 1, search_time_ms: 1 },
        })
      }),
      http.post('/api/cve/update', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('stream')).toBe('true')
        const body = [
          'event: progress',
          'data: {"stage":"start","status":"running","message":"start"}',
          '',
          'event: progress.completed',
          'data: {"stage":"done","status":"completed","add_count":3,"del_count":1,"message":"done"}',
          '',
        ].join('\n')
        return new HttpResponse(body, {
          headers: { 'Content-Type': 'text/event-stream' },
        })
      }),
    )

    renderWithQuery(<CvePage />)

    expect(await screen.findByText('CVE-2026-0001')).toBeTruthy()
    await waitFor(() => expect(searchCalls).toBeGreaterThan(0))

    await user.click(screen.getByText('更新数据库'))
    await waitFor(() => expect(searchCalls).toBeGreaterThan(1))
  })
})
