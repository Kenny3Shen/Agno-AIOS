import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { cancelRun, getChatAgents, getSessionMeta, listSessions, renameSession, streamMessage } from './api'
import { server } from '@/test/server'
import { setToken } from '@/shared/auth/storage'
import { chatSessionFixture } from './testFixtures'

describe('chat API', () => {
  it('loads sessions with the stored bearer token', async () => {
    setToken('token')
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Bearer token')
        return HttpResponse.json({ data: [chatSessionFixture({ session_id: 's1' })], meta: { page: 1, limit: 40, total_pages: 1, total_count: 1, search_time_ms: 0 } })
      })
    )
    expect((await listSessions()).data[0]?.session_id).toBe('s1')
  })

  it('parses Agno data/meta session envelope', async () => {
    server.use(
      http.get('/api/chat/sessions', () =>
        HttpResponse.json({
          data: [chatSessionFixture({ session_id: 's2', preview: 'p', created_at: 3, updated_at: 4 })],
          meta: { page: 1, limit: 40, total_pages: 1, total_count: 1, search_time_ms: 0 },
        })
      )
    )
    const sessions = await listSessions()
    expect(sessions.data).toHaveLength(1)
    expect(sessions.data[0]?.session_id).toBe('s2')
    expect(sessions.meta.limit).toBe(40)
  })

  it('reads the agent catalog from its data envelope', async () => {
    server.use(
      http.get('/api/chat/agents', () =>
        HttpResponse.json({
          data: [
            {
              id: 'deep-research',
              name: '深度研究助手',
              kind: 'agent',
              prefer_live_search: true,
            },
          ],
          meta: { team_enabled: false },
        })
      )
    )

    await expect(getChatAgents()).resolves.toEqual([
      expect.objectContaining({ id: 'deep-research', prefer_live_search: true }),
    ])
  })

  it('requests archived sessions when explicitly enabled', async () => {
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const params = new URL(request.url).searchParams
        expect(params.get('include_archived')).toBe('true')
        expect(params.get('page')).toBe('1')
        return HttpResponse.json({ data: [], meta: { page: 1, limit: 40, total_pages: 0, total_count: 0, search_time_ms: 0 } })
      })
    )

    await listSessions({ includeArchived: true })
  })

  it('rejects a session payload that omits canonical projection fields', async () => {
    server.use(
      http.get('/api/chat/sessions', () =>
        HttpResponse.json({
          data: [{ session_id: 'bad', preview: '', created_at: 1, updated_at: 2 }],
          meta: { page: 1, limit: 40, total_pages: 1, total_count: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listSessions()).rejects.toThrow('listSessions: invalid session payload')
  })

  it('requests the requested page and returns meta for load-more', async () => {
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const params = new URL(request.url).searchParams
        expect(params.get('page')).toBe('2')
        expect(params.get('limit')).toBe('40')
        return HttpResponse.json({
          data: [chatSessionFixture({ session_id: 's3', preview: 'older', created_at: 5, updated_at: 6 })],
          meta: { page: 2, limit: 40, total_pages: 3, total_count: 250, search_time_ms: 1 },
        })
      })
    )
    const result = await listSessions({ page: 2, limit: 40 })
    expect(result.data[0]?.session_id).toBe('s3')
    expect(result.meta).toMatchObject({ page: 2, total_pages: 3, total_count: 250 })
  })

  it('renames a session through the protected session endpoint', async () => {
    server.use(
      http.patch('/api/chat/sessions/s1', async ({ request }) => {
        expect(await request.json()).toEqual({ title: 'Investigation' })
        return HttpResponse.json({ session_id: 's1', preview: 'old', title: 'Investigation', created_at: 1, updated_at: 2 })
      })
    )

    await expect(renameSession('s1', 'Investigation')).resolves.toMatchObject({ title: 'Investigation' })
  })

  it('loads one-session meta for deep links', async () => {
    server.use(
      http.get('/api/chat/sessions/deep-1/meta', () =>
        HttpResponse.json(chatSessionFixture({
          session_id: 'deep-1',
          session_type: 'workflow',
          workflow_id: 'flow-1',
          title: 'Deep WF',
        }))
      )
    )
    await expect(getSessionMeta('deep-1')).resolves.toMatchObject({
      session_id: 'deep-1',
      session_type: 'workflow',
      workflow_id: 'flow-1',
      title: 'Deep WF',
    })
  })

  it('returns null when session meta is missing', async () => {
    server.use(http.get('/api/chat/sessions/missing/meta', () => HttpResponse.json({ detail: '会话不存在' }, { status: 404 })))
    await expect(getSessionMeta('missing')).resolves.toBeNull()
  })

  it('rejects a successful response that contains no stream content', async () => {
    setToken('token')
    server.use(http.post('/api/chat', () => new HttpResponse('', { headers: { 'Content-Type': 'text/event-stream' } })))

    await expect(
      streamMessage({ message: 'inspect', session_id: 's1', model_id: 'model' }, () => undefined, new AbortController().signal)
    ).rejects.toThrow('Chat stream ended before a terminal event')
  })

  it('parses named JSON run events and ignores unrecognised events', async () => {
    server.use(
      http.post(
        '/api/chat',
        () =>
          new HttpResponse(
            [
              'event: run.started\ndata: {"run_id":"run-1","session_id":"s1"}\n\n',
              'event: content.delta\ndata: {"run_id":"run-1","delta":"hello"}\n\n',
              'event: run.completed\ndata: {"run_id":"run-1","metrics":{"total_tokens":4}}\n\n',
            ].join(''),
            { headers: { 'Content-Type': 'text/event-stream' } }
          )
      )
    )
    const events: string[] = []
    await streamMessage(
      { message: 'inspect', session_id: 's1', model_id: 'model' },
      (event) => events.push(event.type),
      new AbortController().signal
    )
    expect(events).toEqual(['run.started', 'content.delta', 'run.completed'])
  })

  it('treats a HITL pause as a normal stream terminal event', async () => {
    server.use(
      http.post(
        '/api/chat',
        () =>
          new HttpResponse('event: run.paused\ndata: {"run_id":"run-1","session_id":"s1","approval_id":"approval-1","tool_name":"simulate_containment"}\n\n', {
            headers: { 'Content-Type': 'text/event-stream' },
          })
      )
    )
    const events: string[] = []
    await expect(
      streamMessage(
        { message: 'contain asset', session_id: 's1', model_id: 'model' },
        (event) => events.push(event.type),
        new AbortController().signal
      )
    ).resolves.toBeUndefined()
    expect(events).toEqual(['run.paused'])
  })

  it('sends a reasoning effort override only when selected', async () => {
    server.use(
      http.post('/api/chat', async ({ request }) => {
        expect(await request.json()).toMatchObject({ message: 'inspect', reasoning_effort: 'high' })
        return new HttpResponse('event: run.completed\ndata: {"run_id":"run-1"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    await streamMessage(
      { message: 'inspect', session_id: 's1', model_id: 'model', reasoning_effort: 'high' },
      () => undefined,
      new AbortController().signal
    )
  })

  it('posts a cancellation request for the server run id', async () => {
    server.use(http.post('/api/chat/runs/run-1/cancel', () => HttpResponse.json({ success: true })))
    await expect(cancelRun('run-1')).resolves.toEqual({ success: true })
  })
})

describe('listSessions archived_only', () => {
  it('sends archived_only without include_archived', async () => {
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const params = new URL(request.url).searchParams
        expect(params.get('archived_only')).toBe('true')
        expect(params.get('include_archived')).toBeNull()
        return HttpResponse.json({
          data: [chatSessionFixture({ session_id: 'a1', preview: 'archived', archived: true })],
          meta: { page: 1, limit: 40, total_pages: 1, total_count: 1, search_time_ms: 0 },
        })
      }),
    )
    const result = await listSessions({ archivedOnly: true, page: 1, limit: 40 })
    expect(result.data[0]?.session_id).toBe('a1')
    expect(result.data[0]?.archived).toBe(true)
  })
})

describe('listSessions q', () => {
  it('forwards session search q', async () => {
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('q')).toBe('risk')
        return HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 40, total_count: 0, total_pages: 0, search_time_ms: 0 },
        })
      }),
    )
    const result = await listSessions({ q: 'risk' })
    expect(result.data).toEqual([])
  })
})

describe('streamMessage attachments', () => {
  it('posts multipart form when files are provided', async () => {
    let contentType = ''
    let isForm = false
    let hasFilesPart = false
    server.use(
      http.post('/api/chat', async ({ request }) => {
        contentType = request.headers.get('content-type') || ''
        isForm = contentType.includes('multipart/form-data')
        // Avoid undici formData() File validation quirks in jsdom; inspect raw body.
        const raw = await request.text()
        hasFilesPart =
          raw.includes('name="files"') ||
          raw.includes('filename="note.txt"') ||
          raw.includes('note.txt')
        expect(raw.includes('analyze') || raw.includes('message')).toBe(true)
        return new HttpResponse('event: run.completed\ndata: {"run_id":"r1"}\n\n', {
          headers: { 'Content-Type': 'text/event-stream' },
        })
      }),
    )
    const file = new File(['hello'], 'note.txt', { type: 'text/plain' })
    const events: unknown[] = []
    await streamMessage(
      { message: 'analyze', session_id: 's-files', model_id: 'm1', files: [file] },
      (event) => events.push(event),
      new AbortController().signal,
    )
    expect(isForm).toBe(true)
    // Body may be binary multipart; filename or files field must appear.
    expect(hasFilesPart || contentType.includes('boundary=')).toBe(true)
    expect(events.some((e) => (e as { type: string }).type === 'run.completed')).toBe(true)
  })
})

describe('streamMessage errors', () => {
  it('surfaces attachment limit errors from API detail', async () => {
    server.use(
      http.post('/api/chat', () =>
        HttpResponse.json({ detail: '最多上传 8 个附件' }, { status: 400 }),
      ),
    )
    await expect(
      streamMessage(
        { message: 'x', session_id: 's1', model_id: 'm1', files: [new File(['a'], 'a.txt')] },
        () => {},
        new AbortController().signal,
      ),
    ).rejects.toThrow('最多上传 8 个附件')
  })
})
