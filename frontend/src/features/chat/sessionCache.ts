import type { QueryClient } from '@tanstack/react-query'
import { chatKeys, SESSION_PAGE_SIZE } from './queries'
import type { SessionListResult } from './api'
import type { ChatSession } from './types'

/** Seed active recents + session-meta as non-archived (after unarchive / continue-on-archive). */
export function markSessionActiveInCaches(queryClient: QueryClient, session: ChatSession) {
  const active: ChatSession = { ...session, archived: false }
  queryClient.setQueryData(chatKeys.sessionMeta(session.session_id), active)
  queryClient.setQueryData<{ pages: SessionListResult[]; pageParams: number[] }>(
    chatKeys.sessions({}),
    (current) => {
      const pages = current?.pages ?? []
      if (!pages.length) {
        return {
          pages: [
            {
              data: [active],
              meta: {
                page: 1,
                limit: SESSION_PAGE_SIZE,
                total_pages: 1,
                total_count: 1,
                search_time_ms: 0,
              },
            },
          ],
          pageParams: [1],
        }
      }
      const [first, ...rest] = pages
      const without = first.data.filter((item) => item.session_id !== active.session_id)
      return {
        pages: [
          {
            ...first,
            data: [active, ...without],
            meta: {
              ...first.meta,
              total_count:
                Math.max(first.meta.total_count, first.data.length) +
                (first.data.some((item) => item.session_id === active.session_id) ? 0 : 1),
            },
          },
          ...rest,
        ],
        pageParams: current?.pageParams ?? [1],
      }
    },
  )

  queryClient.setQueriesData<{ pages: SessionListResult[]; pageParams: number[] }>(
    {
      predicate: (query) => {
        const key = query.queryKey
        if (!Array.isArray(key) || key[0] !== 'chat' || key[1] !== 'sessions') return false
        const opts = key[2] as { archivedOnly?: boolean } | undefined
        return Boolean(opts?.archivedOnly)
      },
    },
    (current) => {
      if (!current?.pages?.length) return current
      let removed = 0
      const pages = current.pages.map((page) => {
        const nextData = page.data.filter((item) => {
          if (item.session_id !== active.session_id) return true
          removed += 1
          return false
        })
        return { ...page, data: nextData }
      })
      if (!removed) return current
      const first = pages[0]!
      pages[0] = {
        ...first,
        meta: {
          ...first.meta,
          total_count: Math.max(0, (first.meta.total_count || 0) - removed),
        },
      }
      return { ...current, pages }
    },
  )
  return active
}
