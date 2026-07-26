import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { CollectPage } from './CollectPage'

const routerMock = vi.hoisted(() => ({ push: vi.fn<(path: string) => void>() }))

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({ history: { push: routerMock.push } }),
}))

const listMeta = { page: 1, limit: 20, total_pages: 0, total_count: 0 }

const installCollectHandlers = (role: 'admin' | 'user') => {
  server.use(
    http.get('/api/auth/users/me', () =>
      HttpResponse.json({
        id: `${role}-1`,
        email: `${role}@example.com`,
        role,
        scopes: ['collect:read', 'collect:write'],
        is_active: true,
        is_superuser: role === 'admin',
      })
    ),
    http.get('/api/collect/sources', () => HttpResponse.json({ data: [], meta: listMeta })),
    http.get('/api/collect/stats', () => HttpResponse.json({ ok: 7, error: 3, total: 10 })),
    http.post('/api/collect/articles/search', () => HttpResponse.json({ data: [], meta: listMeta }))
  )
}

describe('CollectPage bulk retry authorization', () => {
  beforeEach(() => {
    routerMock.push.mockClear()
  })

  it('does not render the bulk retry action for a non-admin writer', async () => {
    installCollectHandlers('user')
    renderWithQuery(<CollectPage />)

    expect(await screen.findByText('失败 3')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /重采失败/ })).toBeNull()
  })

  it('renders the bulk retry action for an administrator', async () => {
    installCollectHandlers('admin')
    renderWithQuery(<CollectPage />)

    expect(await screen.findByRole('button', { name: '重采失败（最多 3）' })).toBeTruthy()
  })

  it('does not offer arbitrary URL collection', async () => {
    installCollectHandlers('user')
    renderWithQuery(<CollectPage />)

    await screen.findByText('失败 3')
    expect(screen.queryByPlaceholderText('https://example.com/security-advisory')).toBeNull()
    expect(screen.queryByRole('button', { name: '采集 URL' })).toBeNull()
  })
})
