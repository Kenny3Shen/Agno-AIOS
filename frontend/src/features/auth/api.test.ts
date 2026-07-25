import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { getCurrentUser, login, logout } from './api'
import { server } from '@/test/server'
import { getToken, setToken } from '@/shared/auth/storage'
import { hasScope, roleOf } from '@/shared/auth/permissions'

describe('authentication behavior', () => {
  it('submits FastAPI Users credentials as form data', async () => {
    server.use(
      http.post('/api/auth/jwt/login', async ({ request }) => {
        expect(request.headers.get('content-type')).toContain('application/x-www-form-urlencoded')
        const body = new URLSearchParams(await request.text())
        expect(body.get('username')).toBe('admin@example.com')
        expect(body.get('password')).toBe('secret')
        return HttpResponse.json({ access_token: 'token', token_type: 'bearer' })
      })
    )
    expect((await login('admin@example.com', 'secret')).access_token).toBe('token')
  })

  it('sends the stored bearer token when restoring the current user', async () => {
    setToken('stored')
    server.use(
      http.get('/api/auth/users/me', ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Bearer stored')
        return HttpResponse.json({ id: 'u1', email: 'admin@example.com', is_active: true })
      })
    )
    expect((await getCurrentUser()).id).toBe('u1')
  })

  it('clears an invalid token after a 401 response', async () => {
    setToken('expired')
    server.use(http.get('/api/auth/users/me', () => new HttpResponse(null, { status: 401 })))
    await expect(getCurrentUser()).rejects.toThrow('Request failed (401)')
    expect(getToken()).toBeNull()
  })

  it('clears local authentication even when remote logout fails', async () => {
    setToken('stored')
    server.use(http.post('/api/auth/logout', () => new HttpResponse(null, { status: 503 })))
    await logout()
    expect(getToken()).toBeNull()
  })

  it('grants all scopes to administrators and explicit scopes to users', () => {
    expect(hasScope({ id: 'a', email: 'a@x', is_active: true, role: 'admin' }, 'config:write')).toBe(true)
    expect(hasScope({ id: 'u', email: 'u@x', is_active: true, role: 'user', scopes: ['sessions:write'] }, 'sessions:write')).toBe(true)
    expect(roleOf(null)).toBe('user')
  })
})
