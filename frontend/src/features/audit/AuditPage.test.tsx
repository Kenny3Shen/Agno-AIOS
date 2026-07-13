import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { setupUser } from '@/test/user'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { renderWithQuery } from '@/test/render'
import { AuditPage } from './AuditPage'
import type { AuditLog, AuditLogResponse } from './types'

const auditEvent = (page: number): AuditLog => ({
  id: `audit-${page}`,
  actor_user_id: 'u1',
  actor_email: 'u1@example.test',
  actor_role: 'admin',
  action: 'auth.login',
  resource_type: 'auth',
  resource_id: 'session-1',
  status: 'success',
  ip_address: '10.0.0.8',
  user_agent: 'pytest-browser',
  metadata: { risk: 'low', page },
  created_at: '2026-01-01T00:00:00Z',
})

const response = (page: number, limit: number): AuditLogResponse => ({
  items: [auditEvent(page)],
  total: 40,
  page,
  limit,
})

describe('audit page workflow', () => {
  it('queries by user, paginates results and opens row details', async () => {
    const user = setupUser()
    const requests: URL[] = []
    server.use(
      http.get('/api/audit/logs', ({ request }) => {
        const url = new URL(request.url)
        requests.push(url)
        const page = Number(url.searchParams.get('page') ?? 1)
        const limit = Number(url.searchParams.get('limit') ?? 25)
        return HttpResponse.json(response(page, limit))
      })
    )

    renderWithQuery(<AuditPage />)

    await screen.findByText('u1@example.test')
    await user.type(screen.getByLabelText('User ID'), 'target-user')
    await user.click(screen.getByRole('button', { name: /查询/ }))

    await waitFor(() => expect(requests.some((url) => url.searchParams.get('actor_user_id') === 'target-user')).toBe(true))

    await user.click(screen.getByTitle('Next Page'))
    await waitFor(() => expect(requests.some((url) => url.searchParams.get('page') === '2')).toBe(true))

    await user.click(await screen.findByText('auth.login'))

    expect(await screen.findByLabelText('Copy Metadata')).toBeTruthy()
    expect(screen.getByText(/"risk": "low"/)).toBeTruthy()
  })
})
