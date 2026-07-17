import { infiniteQueryOptions, keepPreviousData, queryOptions } from '@tanstack/react-query'
import { getHistory, getModels, listSessions } from './api'

export const SESSION_PAGE_SIZE = 40

export type SessionsQueryOptions = {
  /** Only archived sessions (SQL archived_only). */
  archivedOnly?: boolean
  /** Include archived among active (legacy include_archived). */
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
  models: ['settings', 'models'] as const,
}

/** Infinite session list. Prefer object form; boolean first arg is legacy includeArchived. */
export const sessionsQuery = (
  options: SessionsQueryOptions | boolean = {},
  userId?: string,
  q = '',
) => {
  const normalized: SessionsQueryOptions =
    typeof options === 'boolean'
      ? { includeArchived: options, userId, q }
      : options
  const archivedOnly = Boolean(normalized.archivedOnly)
  const includeArchived = Boolean(normalized.includeArchived)
  const scopedUserId = normalized.userId
  const query = normalized.q ?? ''
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
export const modelsQuery = () => queryOptions({ queryKey: chatKeys.models, queryFn: getModels, staleTime: 60_000 })
