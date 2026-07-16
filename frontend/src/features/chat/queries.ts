import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query'
import { getHistory, getModels, listSessions } from './api'

export const SESSION_PAGE_SIZE = 40

export const chatKeys = {
  all: ['chat'] as const,
  sessionLists: ['chat', 'sessions'] as const,
  sessions: (includeArchived = false, userId?: string, q = '') =>
    ['chat', 'sessions', { includeArchived, userId, q }] as const,
  history: (id: string) => ['chat', 'history', id] as const,
  models: ['settings', 'models'] as const,
}

export const sessionsQuery = (includeArchived = false, userId?: string, q = '') =>
  infiniteQueryOptions({
    queryKey: chatKeys.sessions(includeArchived, userId, q),
    queryFn: ({ pageParam }) =>
      listSessions({ includeArchived, userId, page: pageParam, limit: SESSION_PAGE_SIZE, q: q || undefined }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const { page, total_pages } = lastPage.meta
      if (total_pages > 0 && page < total_pages) return page + 1
      if (total_pages <= 0 && lastPage.data.length >= SESSION_PAGE_SIZE) return page + 1
      return undefined
    },
  })

export const historyQuery = (id: string) =>
  queryOptions({ queryKey: chatKeys.history(id), queryFn: () => getHistory(id), enabled: Boolean(id) })
export const modelsQuery = () => queryOptions({ queryKey: chatKeys.models, queryFn: getModels, staleTime: 60_000 })
