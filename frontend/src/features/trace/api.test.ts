import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { getTrace, listTraceSessions, listTraces, normalizeTrace } from './api'
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
  it('keeps Agno-native duration strings without inventing duration_ms', async () => {
    server.use(
      http.get('/api/traces', () =>
        HttpResponse.json({
          data: [
            {
              trace_id: 't1',
              name: 'agent.run',
              status: 'OK',
              duration: '1.50s',
              input: 'hello',
              start_time: '2026-07-12T00:00:00Z',
              end_time: '2026-07-12T00:00:01.5Z',
              session_id: 's1',
              run_id: 'r1',
            },
          ],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 1.2 },
        }),
      ),
    )

    const result = await listTraces({ session_id: 's1' })
    expect(result.data).toHaveLength(1)
    expect(result.data[0]).toMatchObject({
      trace_id: 't1',
      duration: '1.50s',
      input: 'hello',
      session_id: 's1',
    })
    expect(result.data[0]).not.toHaveProperty('duration_ms')
    expect(result.meta.total_count).toBe(1)
  })

  it('defaults missing duration to 0ms', () => {
    expect(
      normalizeTrace({
        trace_id: 't2',
        name: 'agent.run',
        status: 'OK',
        start_time: '',
        end_time: '',
      }),
    ).toMatchObject({ trace_id: 't2', duration: '0ms' })
  })

  it('normalizes detail spans to duration strings', async () => {
    server.use(
      http.get('/api/traces/t1', () =>
        HttpResponse.json({
          trace: {
            trace_id: 't1',
            name: 'agent.run',
            status: 'OK',
            duration: '1.00s',
            start_time: '2026-07-12T00:00:00Z',
            end_time: '',
          },
          spans: [
            {
              span_id: 'root',
              name: 'agent.run',
              status_code: 'OK',
              duration: '1.00s',
              start_time: '2026-07-12T00:00:00Z',
            },
          ],
          tree: [
            {
              span: {
                span_id: 'root',
                name: 'agent.run',
                status_code: 'OK',
                duration: '1.00s',
                start_time: '2026-07-12T00:00:00Z',
              },
              children: [],
            },
          ],
        }),
      ),
    )
    const detail = await getTrace('t1')
    expect(detail.trace.duration).toBe('1.00s')
    expect(detail.spans[0]?.duration).toBe('1.00s')
    expect(detail.tree[0]?.span.duration).toBe('1.00s')
  })

  it('fetches all trace session pages from data/meta envelope', async () => {
    const requestedPages: string[] = []

    server.use(
      http.get('/api/traces/sessions', ({ request }) => {
        const url = new URL(request.url)
        requestedPages.push(`${url.searchParams.get('page')}:${url.searchParams.get('limit')}`)
        const page = Number(url.searchParams.get('page') ?? '1')
        const data =
          page === 1
            ? Array.from({ length: 200 }, (_, index) => summary(index + 1))
            : Array.from({ length: 5 }, (_, index) => summary(201 + index))
        return HttpResponse.json({
          data,
          meta: { page, limit: 200, total_count: 205, total_pages: 2, search_time_ms: 0 },
        })
      }),
    )

    const result = await listTraceSessions({ status: 'OK' })

    expect(requestedPages).toEqual(['1:200', '2:200'])
    expect(result.data).toHaveLength(205)
    expect(result.meta.total_count).toBe(205)
  })
  it('stops walking trace session pages after the client cap', async () => {
    const requestedPages: string[] = []
    server.use(
      http.get('/api/traces/sessions', ({ request }) => {
        const url = new URL(request.url)
        const page = Number(url.searchParams.get('page') ?? '1')
        requestedPages.push(String(page))
        return HttpResponse.json({
          data: Array.from({ length: 200 }, (_, index) => summary((page - 1) * 200 + index + 1)),
          meta: { page, limit: 200, total_count: 2000, total_pages: 10, search_time_ms: 0 },
        })
      }),
    )

    const result = await listTraceSessions({ status: 'OK' })
    expect(requestedPages).toEqual(['1', '2', '3', '4', '5'])
    expect(result.data).toHaveLength(1000)
    expect(result.meta.truncated).toBe(true)
    expect(result.meta.total_count).toBe(2000)
  })

})
