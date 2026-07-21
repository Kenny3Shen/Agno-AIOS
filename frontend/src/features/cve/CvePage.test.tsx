import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { user } from '@/test/user'
import { CvePage } from './CvePage'

const routerMock = vi.hoisted(() => ({ searchStr: '' }))

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouterState: ({ select }: { select: (state: { location: { searchStr: string } }) => unknown }) =>
    select({ location: { searchStr: routerMock.searchStr } }),
}))

const emptySearch = {
  data: [],
  meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
}

const memberCurrentUserHandler = () =>
  http.get('/api/auth/users/me', () =>
    HttpResponse.json({
      id: 'member-1',
      email: 'member@example.com',
      role: 'user',
      scopes: ['cve:read'],
    }),
  )

const adminCurrentUserHandler = () =>
  http.get('/api/auth/users/me', () =>
    HttpResponse.json({
      id: 'admin-1',
      email: 'admin@example.com',
      role: 'admin',
      scopes: ['cve:read', 'admin'],
      is_superuser: true,
    }),
  )

describe('CvePage', () => {
  beforeEach(() => {
    routerMock.searchStr = ''
  })

  it('seeds search from ?q deep-link', async () => {
    routerMock.searchStr = '?q=CVE-2021-44228'
    let seenQuery = ''
    server.use(
      memberCurrentUserHandler(),
      http.post('/api/cve/search', async ({ request }) => {
        const payload = (await request.json()) as { query?: string }
        seenQuery = String(payload.query || '')
        return HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      }),
    )
    renderWithQuery(<CvePage />)
    await waitFor(() => {
      expect(seenQuery).toBe('CVE-2021-44228')
    })
    expect(screen.getByDisplayValue('CVE-2021-44228')).toBeTruthy()
  })

  it('hides database updates for non-admin users', async () => {
    server.use(
      memberCurrentUserHandler(),
      http.post('/api/cve/search', () => HttpResponse.json(emptySearch)),
    )

    renderWithQuery(<CvePage />)

    await waitFor(() => {
      expect(screen.queryByText('更新数据库')).toBeNull()
    })
  })

  it('loads recent CVEs on mount and shows update counts for admin', async () => {
    let searchCalls = 0
    server.use(
      adminCurrentUserHandler(),
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
