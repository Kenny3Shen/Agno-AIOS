import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import type { ChatHistoryPage } from './api'
import {
  chatKeys,
  flattenHistoryPages,
  mergeLatestHistoryPage,
  reconcileLatestHistoryPages,
  refreshLatestHistoryPage,
  SerialAsyncQueue,
} from './queries'
import type { Message } from './types'

const message = (id: string, content = id): Message => ({
  id,
  role: 'assistant',
  content,
  final: true,
  status: 'completed',
  run_id: id,
})

const page = (ids: string[], nextCursor: string | null, hasMore = Boolean(nextCursor)): ChatHistoryPage => ({
  data: ids.map((id) => message(id)),
  meta: {
    limit: 2,
    has_more: hasMore,
    next_cursor: nextCursor,
    total_runs: 5,
  },
})

describe('chat history newest-page refresh', () => {
  it('serializes older-page fetches and newest reconciliation cache mutations', async () => {
    const queue = new SerialAsyncQueue()
    const order: string[] = []
    const olderGate = new AbortController()
    const older = queue.enqueue(
      () =>
        new Promise<void>((resolve) => {
          order.push('older:start')
          olderGate.signal.addEventListener(
            'abort',
            () => {
              order.push('older:end')
              resolve()
            },
            { once: true }
          )
        })
    )
    const latest = queue.enqueue(async () => {
      order.push('latest')
    })

    await Promise.resolve()
    expect(order).toEqual(['older:start'])
    olderGate.abort()
    await Promise.all([older, latest])
    expect(order).toEqual(['older:start', 'older:end', 'latest'])
  })

  it('keeps the displaced tail so a new run cannot create a page-boundary gap', () => {
    const previous = page(['run-2', 'run-3'], 'run-2')
    const latest = page(['run-3', 'run-4'], 'run-3')

    const merged = mergeLatestHistoryPage(previous, latest)

    expect(merged.data.map((item) => item.id)).toEqual(['run-2', 'run-3', 'run-4'])
    expect(merged.meta).toMatchObject({ has_more: true, next_cursor: 'run-2' })
  })

  it('keeps chronological order while preferring a refreshed newest-page copy', () => {
    const newest = page(['run-2', 'run-3'], 'run-2')
    newest.data[0] = message('run-2', 'fresh')
    const older = page(['run-0', 'run-1', 'run-2'], null, false)
    older.data[2] = message('run-2', 'stale')
    const messages = flattenHistoryPages([newest, older])

    expect(messages?.map((item) => item.id)).toEqual(['run-0', 'run-1', 'run-2', 'run-3'])
    expect(messages?.find((item) => item.id === 'run-2')?.content).toBe('fresh')
  })

  it('cascades a shifted newest boundary into bounded older pages without gaps', () => {
    const current = {
      pages: [page(['run-2', 'run-3'], 'run-2'), page(['run-0', 'run-1'], null, false)],
      pageParams: [null, 'run-2'],
    }
    const latest = page(['run-3', 'run-4'], 'run-3')

    const reconciled = reconcileLatestHistoryPages(current, latest)

    expect(reconciled.pages.map((item) => item.data.map((row) => row.id))).toEqual([['run-3', 'run-4'], ['run-1', 'run-2'], ['run-0']])
    expect(reconciled.pages.map((item) => item.meta.next_cursor)).toEqual(['run-3', 'run-1', null])
    expect(reconciled.pageParams).toEqual([null, 'run-3', 'run-1'])
    expect(flattenHistoryPages(reconciled.pages)?.map((row) => row.id)).toEqual(['run-0', 'run-1', 'run-2', 'run-3', 'run-4'])
  })

  it('preserves opaque server cursors while repartitioning refreshed pages', () => {
    const withCursor = (id: string, cursor: string): Message => ({
      ...message(id),
      history_cursor: cursor,
    })
    const current = {
      pages: [
        {
          ...page(['run-2', 'run-3'], 'turn:2'),
          data: [withCursor('run-2', 'turn:2'), withCursor('run-3', 'turn:3')],
        },
        {
          ...page(['run-0', 'run-1'], null, false),
          data: [withCursor('run-0', 'turn:0'), withCursor('run-1', 'turn:1')],
        },
      ],
      pageParams: [null, 'turn:2'],
    }
    const latest = {
      ...page(['run-3', 'run-4'], 'turn:3'),
      data: [withCursor('run-3', 'turn:3'), withCursor('run-4', 'turn:4')],
    }

    const reconciled = reconcileLatestHistoryPages(current, latest)

    expect(reconciled.pages.map((item) => item.meta.next_cursor)).toEqual(['turn:3', 'turn:1', null])
    expect(reconciled.pageParams).toEqual([null, 'turn:3', 'turn:1'])
  })

  it('fetches only the newest page and leaves previously loaded older pages intact', async () => {
    const requestedBefore: Array<string | null> = []
    server.use(
      http.get('/api/chat/sessions/session-1', ({ request }) => {
        requestedBefore.push(new URL(request.url).searchParams.get('before'))
        return HttpResponse.json({
          data: [
            { id: 'run-3', role: 'assistant', content: 'new copy', status: 'completed' },
            { id: 'run-4', role: 'assistant', content: 'newest', status: 'completed' },
          ],
          meta: { limit: 2, has_more: true, next_cursor: 'run-3', total_runs: 5 },
        })
      })
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const cancelHistory = vi.spyOn(queryClient, 'cancelQueries')
    queryClient.setQueryData(chatKeys.history('session-1'), {
      pages: [page(['run-2', 'run-3'], 'run-2'), page(['run-0', 'run-1'], null, false)],
      pageParams: [null, 'run-2'],
    })

    await refreshLatestHistoryPage(queryClient, 'session-1')

    expect(requestedBefore).toEqual([null])
    expect(cancelHistory).toHaveBeenCalledWith({
      queryKey: chatKeys.history('session-1'),
      exact: true,
    })
    const refreshed = queryClient.getQueryData<{
      pages: ChatHistoryPage[]
      pageParams: Array<string | null>
    }>(chatKeys.history('session-1'))
    expect(refreshed?.pages).toHaveLength(3)
    expect(refreshed?.pages[0]?.data.map((item) => item.id)).toEqual(['run-3', 'run-4'])
    expect(refreshed?.pages[1]?.data.map((item) => item.id)).toEqual(['run-1', 'run-2'])
    expect(refreshed?.pages[2]?.data.map((item) => item.id)).toEqual(['run-0'])
    expect(refreshed?.pages.map((item) => item.meta.next_cursor)).toEqual(['run-3', 'run-1', null])
  })
})
