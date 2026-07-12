import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { getRuntimeOverview } from './api'

describe('runtime overview API', () => {
  it('requests the selected observation range', async () => {
    server.use(
      http.get('/api/overview', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('range')).toBe('24h')
        return HttpResponse.json({
          range: '24h',
          generated_at: '',
          health: { status: 'ok' },
          metrics: {},
          series: [],
          distributions: {},
          snapshots: {},
          recent_failures: [],
        })
      })
    )
    await getRuntimeOverview({ range: '24h' })
  })

  it('requests a custom observation window with exact ISO boundaries', async () => {
    server.use(
      http.get('/api/overview', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('range')).toBe('custom')
        expect(url.searchParams.get('start_time')).toBe('2026-07-01T00:00:00.000Z')
        expect(url.searchParams.get('end_time')).toBe('2026-07-02T00:00:00.000Z')
        return HttpResponse.json({
          range: 'custom',
          generated_at: '',
          health: { status: 'ok' },
          metrics: {},
          series: [],
          distributions: {},
          snapshots: {},
          recent_failures: [],
        })
      })
    )
    await getRuntimeOverview({ startTime: '2026-07-01T00:00:00.000Z', endTime: '2026-07-02T00:00:00.000Z' })
  })
})
