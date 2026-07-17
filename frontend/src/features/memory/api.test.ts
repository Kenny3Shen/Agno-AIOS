import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { clearMemories, getMemories, normalizeMemory } from './api'

describe('normalizeMemory', () => {
  it('maps native memory_id rows', () => {
    expect(
      normalizeMemory({
        memory_id: 'mem-1',
        memory: 'Prefers short summaries',
        topics: ['preference'],
        user_id: 'u1',
        updated_at: '2026-07-05T00:00:00+00:00',
      }),
    ).toMatchObject({
      id: 'mem-1',
      memory_id: 'mem-1',
      memory: 'Prefers short summaries',
      topics: ['preference'],
      user_id: 'u1',
    })
  })

  it('ignores legacy id-only rows', () => {
    expect(
      normalizeMemory({
        id: 'legacy-1',
        memory: 'Legacy memory',
      }),
    ).toBeNull()
  })

  it('returns null when memory_id is missing', () => {
    expect(normalizeMemory({ memory: 'no id' })).toBeNull()
  })
})

describe('getMemories', () => {
  it('returns Agno data/meta after normalize', async () => {
    server.use(
      http.get('/api/memories', () =>
        HttpResponse.json({
          data: [
            {
              memory_id: 'mem-1',
              memory: 'Prefers short summaries',
              topics: ['preference'],
              user_id: 'u1',
            },
          ],
          meta: { page: 1, limit: 12, total_count: 1, total_pages: 1, search_time_ms: 2 },
        }),
      ),
    )
    const result = await getMemories({ page: 1, limit: 12 })
    expect(result.data).toHaveLength(1)
    expect(result.data[0]?.memory_id).toBe('mem-1')
    expect(result.meta.total_count).toBe(1)
    expect(result.meta.limit).toBe(12)
  })
})


describe('getMemories user filter', () => {
  it('forwards user_id query param', async () => {
    let seen = ''
    server.use(
      http.get('/api/memories', ({ request }) => {
        seen = new URL(request.url).searchParams.get('user_id') || ''
        return HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 12, total_count: 0, total_pages: 0, search_time_ms: 0 },
        })
      }),
    )
    await getMemories({ user_id: 'user-42', page: 1, limit: 12 })
    expect(seen).toBe('user-42')
  })
})

describe('clearMemories', () => {
  it('posts scoped clear body', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('/api/memories/clear', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ deleted: 3, user_id: 'u1', all_users: false })
      }),
    )
    const result = await clearMemories({ user_id: 'u1' })
    expect(body).toEqual({ user_id: 'u1', all_users: false })
    expect(result.deleted).toBe(3)
  })
})
