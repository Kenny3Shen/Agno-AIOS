import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchCurrentUser,
  fetchOAuthProviders,
  loginWithPassword,
  registerWithPassword,
  requestOAuthAuthorization,
} from './auth.ts'

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
    ...init,
  })
}

describe('auth client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('submits JWT login as FastAPI Users form data', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({ access_token: 'jwt-token', token_type: 'bearer' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const token = await loginWithPassword({
      email: 'secops@example.com',
      password: 'Passw0rd!',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/jwt/login')
    expect(init?.method).toBe('POST')
    expect(init?.headers).toMatchObject({
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
    })
    expect(init?.body).toBeInstanceOf(URLSearchParams)
    expect((init?.body as URLSearchParams).get('username')).toBe(
      'secops@example.com',
    )
    expect((init?.body as URLSearchParams).get('password')).toBe('Passw0rd!')
    expect(token.access_token).toBe('jwt-token')
  })

  it('submits registration as JSON to FastAPI Users register endpoint', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({
          email: 'secops@example.com',
          id: 'user-1',
          is_active: true,
          is_superuser: false,
          is_verified: false,
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await registerWithPassword({
      email: 'secops@example.com',
      password: 'Passw0rd!',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/register')
    expect(init?.method).toBe('POST')
    expect(init?.headers).toMatchObject({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    })
    expect(JSON.parse(String(init?.body))).toEqual({
      email: 'secops@example.com',
      password: 'Passw0rd!',
    })
  })

  it('loads the current user with a bearer token', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({
          email: 'secops@example.com',
          id: 'user-1',
          is_active: true,
          is_superuser: false,
          is_verified: true,
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const user = await fetchCurrentUser('jwt-token')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/users/me')
    expect(init?.headers).toMatchObject({
      Accept: 'application/json',
      Authorization: 'Bearer jwt-token',
    })
    expect(user.email).toBe('secops@example.com')
  })

  it('loads OAuth providers and authorization URLs from backend routes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ providers: ['github', 'google'] }))
      .mockResolvedValueOnce(
        jsonResponse({ authorization_url: 'https://github.com/login/oauth' }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const providers = await fetchOAuthProviders()
    const authorizationUrl = await requestOAuthAuthorization('github')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/oauth/providers')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/github/authorize')
    expect(providers).toEqual(['github', 'google'])
    expect(authorizationUrl).toBe('https://github.com/login/oauth')
  })
})
