import {
  infiniteQueryOptions,
  keepPreviousData,
  queryOptions,
  type InfiniteData,
  type QueryClient,
} from '@tanstack/react-query'
import { ApiError } from '@/shared/api/client'
import {
  getChatAgents,
  getHistoryPage,
  getModels,
  getSessionMeta,
  listSessions,
  type ChatHistoryPage,
} from './api'
import type { Message } from './types'

/** Single-page recents size for conversation management (no load-more). */
export const SESSION_PAGE_SIZE = 40
/** Recent completed turns loaded before users explicitly request older history. */
export const HISTORY_PAGE_SIZE = 40

/** Serialize cache mutations whose query library operations snapshot prior data. */
export class SerialAsyncQueue {
  private tail: Promise<void> = Promise.resolve()

  enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.tail.then(operation, operation)
    this.tail = result.then(
      () => undefined,
      () => undefined,
    )
    return result
  }
}

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
  // Kept separate from the infinite-query key so a background newest-page
  // refresh does not make React Query replay every already loaded page.
  historyLatest: (id: string) => ['chat', 'history-latest', id] as const,
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
  infiniteQueryOptions({
    queryKey: chatKeys.history(id),
    queryFn: ({ pageParam }) =>
      getHistoryPage(id, {
        before: pageParam,
        limit: HISTORY_PAGE_SIZE,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.meta.next_cursor ?? undefined,
    enabled: Boolean(id) && enabled,
    retry: shouldRetryQuery,
    // Older pages are immutable transcript windows.  Newest-page refreshes are
    // coordinated explicitly below; allowing focus/mount invalidation to replay
    // every loaded cursor page would defeat the bounded-history hot path.
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

/**
 * Reconcile a fresh newest page without dropping the tail displaced from the
 * previously loaded window.  A newly completed run shifts the page boundary;
 * retaining that tail keeps the transcript gap-free without refetching all
 * older pages.
 */
export const mergeLatestHistoryPage = (
  previous: ChatHistoryPage,
  latest: ChatHistoryPage,
): ChatHistoryPage => {
  const latestIds = new Set(latest.data.map((message) => message.id))
  const displaced = previous.data.filter((message) => !latestIds.has(message.id))
  return {
    ...latest,
    data: [...displaced, ...latest.data],
    meta: {
      ...latest.meta,
      has_more: previous.meta.has_more || latest.meta.has_more,
      next_cursor: previous.meta.next_cursor ?? latest.meta.next_cursor,
    },
  }
}

/**
 * A server page is limited by top-level runs, while the client renders one or
 * two Message rows for each run. Keep those rows together whenever a newest
 * page refresh changes the cursor boundary.
 */
const historyTurnKey = (message: Message): string => {
  const id = message.id.trim()
  // History user/assistant rows deliberately share this stable base id. Prefer
  // it over run_id because imported Agno data can contain duplicate run ids.
  if (id) return id.endsWith(':user') ? `turn:${id.slice(0, -':user'.length)}` : `turn:${id}`
  const runId = message.run_id?.trim()
  return runId ? `run:${runId}` : 'message:missing-id'
}

const historyTurnCursor = (turn: readonly Message[]): string | null => {
  for (const message of turn) {
    const cursor = message.history_cursor?.trim()
    if (cursor) return cursor
  }
  for (const message of turn) {
    const runId = message.run_id?.trim()
    if (runId) return runId
  }
  for (const message of turn) {
    const id = message.id.trim()
    if (id.endsWith(':user')) return id.slice(0, -':user'.length) || null
    if (id) return id
  }
  return null
}

const splitHistoryTurns = (messages: readonly Message[]): Message[][] => {
  const turns: Message[][] = []
  let previousKey: string | null = null
  for (const message of messages) {
    const key = historyTurnKey(message)
    if (key !== previousKey) {
      turns.push([message])
      previousKey = key
    } else {
      turns[turns.length - 1]?.push(message)
    }
  }
  return turns
}

/**
 * Repartition cached newest→older pages after a newest-page refresh.
 *
 * A new completed run shifts the page boundary. Appending displaced rows to
 * page zero preserves content but lets that page grow without bound. Instead
 * we rebuild bounded turn windows, cascading displaced turns into later pages
 * and deriving fresh cursors for every boundary. This keeps an already loaded
 * transcript gap-free without refetching its older pages.
 */
export const reconcileLatestHistoryPages = (
  current: InfiniteData<ChatHistoryPage, string | null>,
  latest: ChatHistoryPage,
): InfiniteData<ChatHistoryPage, string | null> => {
  if (!current.pages.length) return { pages: [latest], pageParams: [null] }

  const latestIds = new Set(latest.data.map((message) => message.id))
  const prior = flattenHistoryPages(current.pages) ?? []
  const mergedMessages = [
    ...prior.filter((message) => !latestIds.has(message.id)),
    ...latest.data,
  ]
  const turns = splitHistoryTurns(mergedMessages)
  if (!turns.length) return { pages: [latest], pageParams: [null] }

  const pageLimit = Math.max(1, latest.meta.limit)
  const chunks: Message[][] = []
  for (let end = turns.length; end > 0; end -= pageLimit) {
    chunks.push(turns.slice(Math.max(0, end - pageLimit), end).flat())
  }
  const cursors = chunks.map((chunk) => historyTurnCursor(splitHistoryTurns(chunk)[0] ?? []))
  // Do not invent a cursor for malformed/legacy data. The existing first-page
  // merge remains safe (although less compact) until a normal API response can
  // replace it on the next session visit.
  if (cursors.some((cursor) => !cursor)) {
    const [previous, ...olderPages] = current.pages
    return {
      pages: [mergeLatestHistoryPage(previous, latest), ...olderPages],
      pageParams: [null, ...current.pageParams.slice(1)],
    }
  }

  const finalHasMore = current.pages[current.pages.length - 1]?.meta.has_more ?? latest.meta.has_more
  const pages = chunks.map((data, index): ChatHistoryPage => {
    const hasOlderLoadedPage = index < chunks.length - 1
    const hasMore = hasOlderLoadedPage || finalHasMore
    return {
      ...latest,
      data,
      meta: {
        ...latest.meta,
        has_more: hasMore,
        next_cursor: hasMore ? cursors[index] : null,
      },
    }
  })
  return {
    pages,
    pageParams: pages.map((_, index) => (index === 0 ? null : pages[index - 1]?.meta.next_cursor ?? null)),
  }
}

/** Convert newest → older pages into one chronological, newest-preferred list. */
export const flattenHistoryPages = (
  pages: readonly ChatHistoryPage[] | undefined,
): Message[] | undefined => {
  if (!pages) return undefined
  const seen = new Set<string>()
  const chronologicalPages: Message[][] = []
  // Visit current → old pages so a freshly reconciled first page wins any
  // overlap, then restore chronological page order for the transcript.
  for (const page of pages) {
    const unique = page.data.filter((message) => {
      if (seen.has(message.id)) return false
      seen.add(message.id)
      return true
    })
    chronologicalPages.unshift(unique)
  }
  return chronologicalPages.flat()
}

/** Refresh only the newest page of an active transcript. */
export const refreshLatestHistoryPage = async (
  queryClient: QueryClient,
  sessionId: string,
): Promise<ChatHistoryPage> => {
  const latest = await queryClient.fetchQuery({
    queryKey: chatKeys.historyLatest(sessionId),
    queryFn: () => getHistoryPage(sessionId, { limit: HISTORY_PAGE_SIZE }),
    retry: shouldRetryQuery,
    staleTime: 0,
  })
  // A just-enabled infinite query may still be fetching its first page from
  // before the completed run was persisted. Prevent that stale in-flight
  // snapshot from committing after this authoritative newest-page refresh.
  await queryClient.cancelQueries({
    queryKey: chatKeys.history(sessionId),
    exact: true,
  })
  queryClient.setQueryData<InfiniteData<ChatHistoryPage, string | null>>(
    chatKeys.history(sessionId),
    (current) => {
      return current ? reconcileLatestHistoryPages(current, latest) : { pages: [latest], pageParams: [null] }
    },
  )
  return latest
}

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
