import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { getRuntimeOverview } from './api'

describe('runtime overview API', () => {
  it('requests the selected observation range', async () => {
    server.use(http.get('/api/overview', ({ request }) => {
      const url = new URL(request.url)
      expect(url.searchParams.get('range')).toBe('24h')
      return HttpResponse.json({ range: '24h', generated_at: '', health: { status: 'ok' }, metrics: {}, series: [], distributions: {}, snapshots: {}, recent_failures: [] })
    }))
    await getRuntimeOverview('24h')
  })
})
