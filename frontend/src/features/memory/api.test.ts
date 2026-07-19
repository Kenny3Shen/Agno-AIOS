import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { clearMemories, getMemories } from './api'

describe('getMemories', () => {
  it('forwards user_id and preserves the native envelope', async () => {
    let seen = ''
    server.use(
      http.get('/api/memories', ({ request }) => {
        seen = new URL(request.url).searchParams.get('user_id') || ''
        return HttpResponse.json({
          data: [{ memory_id: 'mem-1', memory: 'Prefers short summaries', topics: ['preference'], user_id: 'user-42' }],
          meta: { page: 1, limit: 12, total_count: 1, total_pages: 1, search_time_ms: 0 },
        })
      }),
    )
    const result = await getMemories({ user_id: 'user-42', page: 1, limit: 12 })
    expect(seen).toBe('user-42')
    expect(result.data[0]).toMatchObject({ memory_id: 'mem-1', topics: ['preference'], user_id: 'user-42' })
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
