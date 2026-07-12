import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { listTraceSessions } from './api'
import type { TraceSessionSummary } from './types'

const summary = (index: number): TraceSessionSummary => ({
  session_id: `session-${index}`,
  name: `Session ${index}`,
  latest_start_time: `2026-07-12T${String(index % 24).padStart(2, '0')}:00:00Z`,
  trace_count: 1,
  run_count: 1,
  error_count: 0,
  status: 'OK',
})

describe('trace API', () => {
  it('fetches all trace session pages for client-side archive filtering and pagination', async () => {
    const requestedPages: string[] = []

    server.use(http.get('/api/traces/sessions', ({ request }) => {
      const url = new URL(request.url)
      requestedPages.push(`${url.searchParams.get('page')}:${url.searchParams.get('limit')}`)
      const page = Number(url.searchParams.get('page') ?? '1')
      const items = page === 1
        ? Array.from({ length: 200 }, (_, index) => summary(index + 1))
        : Array.from({ length: 5 }, (_, index) => summary(201 + index))
      return HttpResponse.json({ items, total_count: 205, page, limit: 200 })
    }))

    const result = await listTraceSessions({ status: 'OK' })

    expect(requestedPages).toEqual(['1:200', '2:200'])
    expect(result.items).toHaveLength(205)
    expect(result.total_count).toBe(205)
  })
})
