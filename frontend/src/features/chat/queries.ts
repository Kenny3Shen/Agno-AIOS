import { keepPreviousData, queryOptions } from '@tanstack/react-query'
import { ApiError } from '@/shared/api/client'
import { getChatAgents, getHistory, getModels, getSessionMeta, listSessions } from './api'

/** Single-page recents size for conversation management (no load-more). */
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
  agents: ['chat', 'agents'] as const,
}

/** Recent sessions list (first page only; conversation panel has no load-more). */
export const sessionsQuery = (options: SessionsQueryOptions = {}) => {
  const archivedOnly = Boolean(options.archivedOnly)
  const includeArchived = Boolean(options.includeArchived)
  const scopedUserId = options.userId
  const query = options.q ?? ''
  return queryOptions({
    queryKey: chatKeys.sessions({
      archivedOnly,
      includeArchived,
      userId: scopedUserId,
      q: query,
    }),
    queryFn: () =>
      listSessions({
        archivedOnly,
        includeArchived: archivedOnly ? false : includeArchived,
        userId: scopedUserId,
        page: 1,
        limit: SESSION_PAGE_SIZE,
        q: query || undefined,
      }),
    placeholderData: keepPreviousData,
  })
}

const shouldRetryQuery = (failureCount: number, error: unknown) => {
  if (error instanceof ApiError && (error.status === 404 || error.status === 403)) return false
  return failureCount < 2
}

export const historyQuery = (id: string, enabled = true) =>
  queryOptions({
    queryKey: chatKeys.history(id),
    queryFn: () => getHistory(id),
    enabled: Boolean(id) && enabled,
    retry: shouldRetryQuery,
  })

/** One-session list projection when the id is outside loaded recents pages. */
export const sessionMetaQuery = (id: string, enabled = true) =>
  queryOptions({
    queryKey: chatKeys.sessionMeta(id),
    queryFn: () => getSessionMeta(id),
    enabled: Boolean(id) && enabled,
    staleTime: 30_000,
    retry: shouldRetryQuery,
  })
export const modelsQuery = () => queryOptions({ queryKey: chatKeys.models, queryFn: getModels, staleTime: 60_000 })
export const agentsQuery = () =>
  queryOptions({ queryKey: chatKeys.agents, queryFn: getChatAgents, staleTime: 300_000 })
