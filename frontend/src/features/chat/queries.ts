import { infiniteQueryOptions, keepPreviousData, queryOptions } from '@tanstack/react-query'
import { getHistory, getModels, getSessionMeta, listSessions } from './api'

export const SESSION_PAGE_SIZE = 40

export type SessionsQueryOptions = {
  /** Only archived sessions (SQL archived_only). */
  archivedOnly?: boolean
  /** Include archived among active sessions. */
  includeArchived?: boolean
  userId?: string
  q?: string
}

export const chatKeys = {
  all: ['chat'] as const,
  sessionLists: ['chat', 'sessions'] as const,
  sessions: (options: SessionsQueryOptions = {}) =>
    [
      'chat',
      'sessions',
      {
        archivedOnly: Boolean(options.archivedOnly),
        includeArchived: Boolean(options.includeArchived),
        userId: options.userId,
        q: options.q ?? '',
      },
    ] as const,
  history: (id: string) => ['chat', 'history', id] as const,
  sessionMeta: (id: string) => ['chat', 'session-meta', id] as const,
  models: ['settings', 'models'] as const,
}

/** Infinite session list (object options only). */
export const sessionsQuery = (options: SessionsQueryOptions = {}) => {
  const archivedOnly = Boolean(options.archivedOnly)
  const includeArchived = Boolean(options.includeArchived)
  const scopedUserId = options.userId
  const query = options.q ?? ''
  return infiniteQueryOptions({
    queryKey: chatKeys.sessions({
      archivedOnly,
      includeArchived,
      userId: scopedUserId,
      q: query,
    }),
    queryFn: ({ pageParam }) =>
      listSessions({
        archivedOnly,
        includeArchived: archivedOnly ? false : includeArchived,
        userId: scopedUserId,
        page: pageParam,
        limit: SESSION_PAGE_SIZE,
        q: query || undefined,
      }),
    initialPageParam: 1,
    placeholderData: keepPreviousData,
    getNextPageParam: (lastPage) => {
      const { page, total_pages } = lastPage.meta
      if (total_pages > 0 && page < total_pages) return page + 1
      if (total_pages <= 0 && lastPage.data.length >= SESSION_PAGE_SIZE) return page + 1
      return undefined
    },
  })
}

export const historyQuery = (id: string, enabled = true) =>
  queryOptions({
    queryKey: chatKeys.history(id),
    queryFn: () => getHistory(id),
    enabled: Boolean(id) && enabled,
  })

/** One-session list projection when the id is outside loaded recents pages. */
export const sessionMetaQuery = (id: string, enabled = true) =>
  queryOptions({
    queryKey: chatKeys.sessionMeta(id),
    queryFn: () => getSessionMeta(id),
    enabled: Boolean(id) && enabled,
    staleTime: 30_000,
  })
export const modelsQuery = () => queryOptions({ queryKey: chatKeys.models, queryFn: getModels, staleTime: 60_000 })
