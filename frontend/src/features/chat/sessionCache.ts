import type { QueryClient } from '@tanstack/react-query'
import { chatKeys, SESSION_PAGE_SIZE } from './queries'
import type { SessionListResult } from './api'
import type { ChatSession } from './types'

/** Seed active recents + session-meta as non-archived (after unarchive / continue-on-archive). */
export function markSessionActiveInCaches(queryClient: QueryClient, session: ChatSession) {
  const active: ChatSession = { ...session, archived: false }
  queryClient.setQueryData(chatKeys.sessionMeta(session.session_id), active)
  queryClient.setQueryData<SessionListResult>(chatKeys.sessions({}), (current) => {
    if (!current) {
      return {
        data: [active],
        meta: {
          page: 1,
          limit: SESSION_PAGE_SIZE,
          total_pages: 1,
          total_count: 1,
          search_time_ms: 0,
        },
      }
    }
    const without = current.data.filter((item) => item.session_id !== active.session_id)
    const existed = current.data.some((item) => item.session_id === active.session_id)
    return {
      ...current,
      data: [active, ...without],
      meta: {
        ...current.meta,
        total_count: Math.max(current.meta.total_count, current.data.length) + (existed ? 0 : 1),
      },
    }
  })

  queryClient.setQueriesData<SessionListResult>(
    {
      predicate: (query) => {
        const key = query.queryKey
        if (!Array.isArray(key) || key[0] !== 'chat' || key[1] !== 'sessions') return false
        const opts = key[2] as { archivedOnly?: boolean } | undefined
        return Boolean(opts?.archivedOnly)
      },
    },
    (current) => {
      if (!current?.data?.length) return current
      const nextData = current.data.filter((item) => item.session_id !== active.session_id)
      if (nextData.length === current.data.length) return current
      return {
        ...current,
        data: nextData,
        meta: {
          ...current.meta,
          total_count: Math.max(0, (current.meta.total_count || 0) - 1),
        },
      }
    },
  )
  return active
}
