import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { cancelRun, listSessions, renameSession, streamMessage } from './api'
import { server } from '@/test/server'
import { AUTH_TOKEN_STORAGE_KEY } from '@/shared/auth/storage'

describe('chat API', () => {
  it('loads sessions with the stored bearer token', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(http.get('/api/chat/sessions', ({ request }) => {
      expect(request.headers.get('authorization')).toBe('Bearer token')
      return HttpResponse.json([{ session_id: 's1', preview: 'run', created_at: 1, updated_at: 2 }])
    }))
    expect((await listSessions())[0]?.session_id).toBe('s1')
  })

  it('requests archived sessions when explicitly enabled', async () => {
    server.use(http.get('/api/chat/sessions', ({ request }) => {
      expect(new URL(request.url).searchParams.get('include_archived')).toBe('true')
      return HttpResponse.json([])
    }))

    await listSessions(true)
  })

  it('renames a session through the protected session endpoint', async () => {
    server.use(http.patch('/api/chat/sessions/s1', async ({ request }) => {
      expect(await request.json()).toEqual({ title: 'Investigation' })
      return HttpResponse.json({ session_id: 's1', preview: 'old', title: 'Investigation', created_at: 1, updated_at: 2 })
    }))

    await expect(renameSession('s1', 'Investigation')).resolves.toMatchObject({ title: 'Investigation' })
  })

  it('rejects a successful response that contains no stream content', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(http.post('/api/chat', () => new HttpResponse('', { headers: { 'Content-Type': 'text/event-stream' } })))

    await expect(streamMessage(
      { message: 'inspect', session_id: 's1', model_id: 'model' },
      () => undefined,
      new AbortController().signal,
    )).rejects.toThrow()
  })

  it('parses named JSON run events and ignores unrecognised events', async () => {
    server.use(http.post('/api/chat', () => new HttpResponse([
      'event: run.started\ndata: {"run_id":"run-1","session_id":"s1"}\n\n',
      'event: content.delta\ndata: {"run_id":"run-1","delta":"hello"}\n\n',
      'event: run.completed\ndata: {"run_id":"run-1","metrics":{"total_tokens":4}}\n\n',
    ].join(''), { headers: { 'Content-Type': 'text/event-stream' } })))
    const events: string[] = []
    await streamMessage({ message: 'inspect', session_id: 's1', model_id: 'model' }, (event) => events.push(event.type), new AbortController().signal)
    expect(events).toEqual(['run.started', 'content.delta', 'run.completed'])
  })

  it('sends a reasoning effort override only when selected', async () => {
    server.use(http.post('/api/chat', async ({ request }) => {
      expect(await request.json()).toMatchObject({ message: 'inspect', reasoning_effort: 'high' })
      return new HttpResponse('event: run.completed\ndata: {"run_id":"run-1"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
    }))
    await streamMessage({ message: 'inspect', session_id: 's1', model_id: 'model', reasoning_effort: 'high' }, () => undefined, new AbortController().signal)
  })

  it('posts a cancellation request for the server run id', async () => {
    server.use(http.post('/api/chat/runs/run-1/cancel', () => HttpResponse.json({ success: true })))
    await expect(cancelRun('run-1')).resolves.toEqual({ success: true })
  })
})
