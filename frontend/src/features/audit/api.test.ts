import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { setToken } from '@/shared/auth/storage'
import { getAuditLogs } from './api'
import type { AuditLogResponse } from './types'

const emptyResponse: AuditLogResponse = { data: [], meta: { page: 2, limit: 25, total_pages: 0, total_count: 0, search_time_ms: 0 } }

describe('audit log API', () => {
  it('sends authenticated audit filters as query parameters', async () => {
    setToken('token')
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

    expect(result.meta.total_count).toBe(0)
  })

  it('normalizes canonical data/meta rows', async () => {
    setToken('token')
    server.use(
      http.get('/api/audit/logs', () =>
        HttpResponse.json({
          data: [
            {
              id: 9,
              actor_user_id: 'u1',
              actor_email: 'a@example.test',
              actor_role: 'admin',
              action: 'auth.login',
              resource_type: 'auth',
              resource_id: 's1',
              status: 'success',
              ip_address: '1.1.1.1',
              user_agent: 'vitest',
              metadata: { ok: true },
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    const result = await getAuditLogs({ page: 1, limit: 20 })
    expect(result.data).toHaveLength(1)
    expect(result.data[0]?.id).toBe(9)
    expect(result.data[0]?.metadata).toEqual({ ok: true })
    expect(result.meta.total_pages).toBe(1)
    expect(result.meta.search_time_ms).toBe(0)
  })

  it('rejects malformed audit rows instead of silently dropping them', async () => {
    server.use(
      http.get('/api/audit/logs', () =>
        HttpResponse.json({
          data: [{ not_an_audit: true }],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(getAuditLogs({ page: 1, limit: 20 })).rejects.toThrow('getAuditLogs: invalid audit log payload')
  })

  it('rejects malformed audit fields instead of coercing them to empty values', async () => {
    server.use(
      http.get('/api/audit/logs', () =>
        HttpResponse.json({
          data: [
            {
              id: 9,
              actor_user_id: 'u1',
              actor_email: 'a@example.test',
              actor_role: 'admin',
              action: 'auth.login',
              resource_type: 'auth',
              resource_id: 's1',
              status: 'success',
              ip_address: '1.1.1.1',
              user_agent: 'vitest',
              metadata: [],
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(getAuditLogs({ page: 1, limit: 20 })).rejects.toThrow('getAuditLogs: invalid audit log payload')
  })

})
