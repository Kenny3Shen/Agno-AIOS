import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { chatKeys, SESSION_PAGE_SIZE } from './queries'
import { markSessionActiveInCaches } from './sessionCache'
import type { SessionListResult } from './api'

describe('markSessionActiveInCaches', () => {
  it('seeds active recents and clears archived meta', () => {
    const client = new QueryClient()
    const session = {
      session_id: 's1',
      preview: 'hello',
      title: 'Case',
      created_at: 1,
      updated_at: 2,
      archived: true,
    }
    markSessionActiveInCaches(client, session)
    expect(client.getQueryData(chatKeys.sessionMeta('s1'))).toMatchObject({
      session_id: 's1',
      archived: false,
      title: 'Case',
    })
    const active = client.getQueryData<{ pages: SessionListResult[] }>(chatKeys.sessions({}))
    expect(active?.pages[0]?.data[0]).toMatchObject({ session_id: 's1', archived: false })
    expect(active?.pages[0]?.meta.limit).toBe(SESSION_PAGE_SIZE)
  })

  it('removes the session from archived-only lists', () => {
    const client = new QueryClient()
    const archivedKey = chatKeys.sessions({ archivedOnly: true })
    client.setQueryData(archivedKey, {
      pages: [
        {
          data: [
            {
              session_id: 's1',
              preview: 'old',
              created_at: 1,
              updated_at: 2,
              archived: true,
            },
            {
              session_id: 's2',
              preview: 'other',
              created_at: 1,
              updated_at: 2,
              archived: true,
            },
          ],
          meta: { page: 1, limit: 40, total_pages: 1, total_count: 2, search_time_ms: 0 },
        },
      ],
      pageParams: [1],
    })
    markSessionActiveInCaches(client, {
      session_id: 's1',
      preview: 'old',
      created_at: 1,
      updated_at: 3,
      archived: true,
    })
    const archived = client.getQueryData<{ pages: SessionListResult[] }>(archivedKey)
    expect(archived?.pages[0]?.data.map((item) => item.session_id)).toEqual(['s2'])
    expect(archived?.pages[0]?.meta.total_count).toBe(1)
  })
})
