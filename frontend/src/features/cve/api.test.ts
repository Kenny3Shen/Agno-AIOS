import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { searchCves } from './api'

const cve = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  cve_id: 'CVE-2026-0001',
  github_url: 'https://github.com/example/cve-1',
  description: 'Example CVE',
  source: 'github',
  create_time: '2026-07-18T00:00:00Z',
  ...overrides,
})

describe('CVE API', () => {
  it('uses the canonical data/meta search envelope', async () => {
    server.use(
      http.post('/api/cve/search', async ({ request }) => {
        expect(await request.json()).toEqual({ query: 'CVE-2026-0001', source: 'github', page: 2, size: 10 })
        return HttpResponse.json({
          data: [cve({ id: 2, create_time: null })],
          meta: { page: 2, limit: 10, total_count: 11, total_pages: 2, search_time_ms: 0 },
        })
      }),
    )

    const result = await searchCves({ query: 'CVE-2026-0001', source: 'github', page: 2, size: 10 })

    expect(result.data).toMatchObject([{ id: 2, cve_id: 'CVE-2026-0001', create_time: null }])
    expect(result.meta).toMatchObject({ page: 2, total_count: 11 })
  })

  it('rejects malformed CVE rows instead of silently dropping them', async () => {
    server.use(
      http.post('/api/cve/search', () =>
        HttpResponse.json({
          data: [{ id: 1 }],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(searchCves({ query: '', page: 1, size: 20 })).rejects.toThrow('searchCves: invalid CVE payload')
  })

  it('rejects string identifiers instead of coercing them to database IDs', async () => {
    server.use(
      http.post('/api/cve/search', () =>
        HttpResponse.json({
          data: [cve({ id: '2' })],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(searchCves({ query: '', page: 1, size: 20 })).rejects.toThrow('searchCves: invalid CVE payload')
  })
})
