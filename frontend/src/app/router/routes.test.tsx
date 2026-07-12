import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { App } from '@/app/App'
import { AppProviders } from '@/app/providers/AppProviders'
import { AUTH_TOKEN_STORAGE_KEY } from '@/shared/auth/storage'
import { server } from '@/test/server'
import { router } from './routes'

const user = {
  id: 'user-1',
  email: 'admin@example.com',
  role: 'admin',
  scopes: ['sessions:write'],
  is_active: true,
}

const overview = {
  range: '24h',
  generated_at: '2026-07-12T00:00:00.000Z',
  health: { status: 'ok' },
  metrics: { total_runs: 0, failure_rate: 0, p95_duration_ms: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0 },
  series: [],
  distributions: {},
  snapshots: { pending_approvals: 0, knowledge_documents: 0, memories: 0 },
  recent_failures: [],
}

const renderAppAt = (path: string) => {
  router.history.replace(path)
  return render(<AppProviders><App /></AppProviders>)
}

describe('app authentication routing', () => {
  beforeEach(() => {
    router.history.replace('/')
  })

  it('redirects anonymous root visits to the login route', async () => {
    renderAppAt('/')

    await waitFor(() => expect(window.location.hash).toBe('#/login'))
    expect(await screen.findByRole('heading', { name: '登录 T.A.I.S' })).toBeTruthy()
  })

  it('preserves the original protected target as login next', async () => {
    renderAppAt('/chat?session=abc')

    await waitFor(() => expect(decodeURIComponent(window.location.hash)).toBe('#/login?next=/chat?session=abc'))
  })

  it('redirects expired tokens to login and clears local auth', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'expired')
    server.use(http.get('/api/auth/users/me', () => new HttpResponse(null, { status: 401 })))

    renderAppAt('/dashboard')

    await waitFor(() => expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull())
    await waitFor(() => expect(decodeURIComponent(window.location.hash)).toBe('#/login?next=/dashboard'))
  })

  it('returns to a safe next route after successful login', async () => {
    const client = userEvent.setup()
    server.use(
      http.post('/api/auth/jwt/login', () => HttpResponse.json({ access_token: 'token' })),
      http.get('/api/auth/users/me', () => HttpResponse.json(user)),
      http.get('/api/overview', () => HttpResponse.json(overview)),
    )

    renderAppAt('/login?next=%2Fdashboard')
    await client.type(await screen.findByLabelText('密码'), 'AdminPass123!')
    await client.click(screen.getByRole('button', { name: /登\s*录/ }))

    await waitFor(() => expect(window.location.hash).toBe('#/dashboard'))
  })

  it('uses dashboard as the default successful login target', async () => {
    const client = userEvent.setup()
    server.use(
      http.post('/api/auth/jwt/login', () => HttpResponse.json({ access_token: 'token' })),
      http.get('/api/auth/users/me', () => HttpResponse.json(user)),
      http.get('/api/overview', () => HttpResponse.json(overview)),
    )

    renderAppAt('/login')
    await client.type(await screen.findByLabelText('密码'), 'AdminPass123!')
    await client.click(screen.getByRole('button', { name: /登\s*录/ }))

    await waitFor(() => expect(window.location.hash).toBe('#/dashboard'))
  })
})
