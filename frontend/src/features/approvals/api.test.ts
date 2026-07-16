import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { getApprovals } from './api'

const submission = (id: string) => ({
  id,
  kind: 'upload',
  status: 'pending',
  resource_type: 'skill',
  created_at: 1,
  submitted_by: { id: 'u1', email: 'a@b.c' },
})

describe('getApprovals', () => {
  it('pages upload submissions with data/meta totals', async () => {
    server.use(
      http.get('/api/approvals/submissions', ({ request }) => {
        const url = new URL(request.url)
        const page = Number(url.searchParams.get('page') ?? '1')
        const limit = Number(url.searchParams.get('limit') ?? '20')
        const start = (page - 1) * limit
        const rows = Array.from({ length: Math.min(limit, Math.max(0, 25 - start)) }, (_, i) =>
          submission(`s${start + i}`),
        )
        return HttpResponse.json({
          data: rows,
          meta: { page, limit, total_count: 25, total_pages: 3 },
        })
      }),
    )

    const first = await getApprovals({ status: 'pending', kind: 'upload', page: 1, limit: 10 })
    expect(first.data.map((item) => item.id)).toEqual(
      Array.from({ length: 10 }, (_, i) => `s${i}`),
    )
    expect(first.meta.total_count).toBe(25)

    const second = await getApprovals({ status: 'pending', kind: 'upload', page: 2, limit: 10 })
    expect(second.data.map((item) => item.id)).toEqual(
      Array.from({ length: 10 }, (_, i) => `s${10 + i}`),
    )
  })

  it('merges uploads before HITL on the all tab (page 1)', async () => {
    server.use(
      http.get('/api/approvals/submissions', () =>
        HttpResponse.json({
          data: [submission('u0'), submission('u1')],
          meta: { page: 1, limit: 10, total_count: 2, total_pages: 1 },
        }),
      ),
      http.get('/api/approvals', () =>
        HttpResponse.json({
          data: [
            {
              id: 'h0',
              kind: 'hitl',
              status: 'pending',
              source_type: 'agent',
              created_at: 1,
            },
            {
              id: 'h1',
              kind: 'hitl',
              status: 'pending',
              source_type: 'agent',
              created_at: 1,
            },
          ],
          meta: { page: 1, limit: 10, total_count: 2, total_pages: 1 },
        }),
      ),
    )

    const result = await getApprovals({ status: 'pending', kind: 'all', page: 1, limit: 10 })
    expect(result.data.map((item) => item.id)).toEqual(['u0', 'u1', 'h0', 'h1'])
    expect(result.meta.total_count).toBe(4)
  })
})
