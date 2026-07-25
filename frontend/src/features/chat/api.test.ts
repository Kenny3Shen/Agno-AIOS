import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { streamMessage } from './api'

describe('chat SSE resume cursor', () => {
  it('flushes a queued visual event before an ignored frame advances its cursor', async () => {
    server.use(
      http.post(
        '/api/chat',
        () =>
          new HttpResponse(
            [
              'event: content.delta',
              'data: {"run_id":"run-1","delta":"queued","event_index":7}',
              '',
              'event: server.internal',
              'data: {"event_index":8}',
              '',
              'event: run.completed',
              'data: {"run_id":"run-1","event_index":9}',
              '',
            ].join('\n'),
            { headers: { 'Content-Type': 'text/event-stream' } }
          )
      )
    )
    let visualQueued = false
    let visualCommitted = false
    const cursor = {
      current: null as number | null,
      flushPendingEvents: () => {
        expect(visualQueued).toBe(true)
        expect(visualCommitted).toBe(false)
        visualCommitted = true
        cursor.current = 7
      },
    }

    await streamMessage(
      { message: 'hello', session_id: 'session-1', model_id: 'model-1' },
      (event) => {
        if (event.type === 'content.delta') visualQueued = true
      },
      new AbortController().signal,
      cursor
    )

    expect(visualCommitted).toBe(true)
    expect(cursor.current).toBe(8)
  })
})
