import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { AUTH_TOKEN_STORAGE_KEY } from '@/shared/auth/storage'
import { getAuditLogs } from './api'
import type { AuditLogResponse } from './types'

const emptyResponse: AuditLogResponse = { items: [], total: 0, page: 2, limit: 25 }

describe('audit log API', () => {
  it('sends authenticated audit filters as query parameters', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(
      http.get('/api/audit/logs', ({ request }) => {
        const url = new URL(request.url)
        expect(request.headers.get('authorization')).toBe('Bearer token')
        expect(url.searchParams.get('page')).toBe('2')
        expect(url.searchParams.get('limit')).toBe('25')
        expect(url.searchParams.get('actor_user_id')).toBe('u1')
        expect(url.searchParams.get('actor_email')).toBe('u1@example.test')
        expect(url.searchParams.get('action')).toBe('auth.login')
        expect(url.searchParams.get('resource_type')).toBe('auth')
        expect(url.searchParams.get('resource_id')).toBe('session-1')
        expect(url.searchParams.get('status')).toBe('success')
        expect(url.searchParams.get('ip_address')).toBe('10.0.0.8')
        expect(url.searchParams.get('created_from')).toBe('2026-01-01T00:00:00.000Z')
        expect(url.searchParams.get('created_to')).toBe('2026-01-02T00:00:00.000Z')
        return HttpResponse.json(emptyResponse)
      })
    )

    const result = await getAuditLogs({
      page: 2,
      limit: 25,
      actor_user_id: ' u1 ',
      actor_email: 'u1@example.test',
      action: 'auth.login',
      resource_type: 'auth',
      resource_id: 'session-1',
      status: 'success',
      ip_address: '10.0.0.8',
      created_from: '2026-01-01T00:00:00.000Z',
      created_to: '2026-01-02T00:00:00.000Z',
    })

    expect(result.total).toBe(0)
  })
})
