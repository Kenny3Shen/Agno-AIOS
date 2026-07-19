import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { listFailures, listRuns } from './api'

const evalRun = (overrides: Record<string, unknown> = {}) => ({
  id: 'eval-1',
  name: 'CVE baseline',
  eval_type: 'accuracy',
  passed: true,
  score: 0.9,
  agent_id: 'security-operations',
  created_at: '2026-07-18T00:00:00Z',
  eval_data: { overall_score: 0.9 },
  eval_input: { prompt: 'evaluate' },
  ...overrides,
})

describe('evaluations API', () => {
  it('uses the canonical paginated Agno eval-runs envelope', async () => {
    server.use(
      http.get('/api/agent-evals/agno-runs', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('page')).toBe('2')
        expect(url.searchParams.get('limit')).toBe('10')
        return HttpResponse.json({
          data: [evalRun({ id: 'eval-2', score: '0.8' })],
          meta: { page: 2, limit: 10, total_count: 12, total_pages: 2, search_time_ms: 0 },
        })
      }),
    )

    const result = await listRuns({ page: 2, limit: 10 })

    expect(result.data).toMatchObject([{ id: 'eval-2', score: 0.8 }])
    expect(result.meta).toMatchObject({ page: 2, total_count: 12 })
  })

  it('returns failure rows from their canonical data envelope', async () => {
    server.use(
      http.get('/api/agent-evals/failures', ({ request }) => {
        expect(new URL(request.url).searchParams.get('limit')).toBe('5')
        return HttpResponse.json({
          data: [evalRun({ id: 'failed-1', passed: false })],
          meta: { page: 1, limit: 5, total_count: 1, total_pages: 1, search_time_ms: 0 },
        })
      }),
    )

    await expect(listFailures({ limit: 5 })).resolves.toMatchObject([{ id: 'failed-1', passed: false }])
  })

  it('rejects malformed eval rows instead of silently dropping them', async () => {
    server.use(
      http.get('/api/agent-evals/agno-runs', () =>
        HttpResponse.json({
          data: [{ eval_type: 'accuracy' }],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listRuns()).rejects.toThrow('listRuns: invalid eval run payload')
  })
})
