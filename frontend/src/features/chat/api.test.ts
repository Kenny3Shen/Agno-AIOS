import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { listSessions, streamMessage } from './api'
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

  it('rejects a successful response that contains no stream content', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(http.post('/api/chat', () => new HttpResponse('', { headers: { 'Content-Type': 'text/event-stream' } })))

    await expect(streamMessage(
      { message: 'inspect', session_id: 's1', model_id: 'model' },
      () => undefined,
      new AbortController().signal,
    )).rejects.toThrow()
  })
})
