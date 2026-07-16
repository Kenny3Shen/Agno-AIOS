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

  it('requests a single sessions page with page/limit', async () => {
    const requested: string[] = []
    server.use(
      http.get('/api/traces/sessions', ({ request }) => {
        const url = new URL(request.url)
        requested.push(`${url.searchParams.get('page')}:${url.searchParams.get('limit')}`)
        return HttpResponse.json({
          data: [summary(1), summary(2)],
          meta: { page: 2, limit: 8, total_count: 20, total_pages: 3, search_time_ms: 0 },
        })
      }),
    )

    const result = await listTraceSessions({ status: 'OK', page: 2, limit: 8 })
    expect(requested).toEqual(['2:8'])
    expect(result.data).toHaveLength(2)
    expect(result.meta).toMatchObject({ page: 2, limit: 8, total_count: 20, total_pages: 3 })
  })

  it('propagates truncated meta from a single sessions response', async () => {
    server.use(
      http.get('/api/traces/sessions', () =>
        HttpResponse.json({
          data: Array.from({ length: 8 }, (_, index) => summary(index + 1)),
          meta: {
            page: 1,
            limit: 8,
            total_count: 50,
            total_pages: 7,
            search_time_ms: 0,
            truncated: true,
            scanned_count: 200,
          },
        }),
      ),
    )
    const result = await listTraceSessions({ status: 'ERROR', page: 1, limit: 8 })
    expect(result.data).toHaveLength(8)
    expect(result.meta.truncated).toBe(true)
    expect(result.meta.scanned_count).toBe(200)
    expect(result.meta.total_count).toBe(50)
  })

})
