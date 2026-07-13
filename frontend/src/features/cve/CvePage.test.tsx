import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { CvePage } from './CvePage'

describe('CvePage', () => {
  it('disables database updates for non-admin users', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'member-1', email: 'member@example.com', role: 'user', scopes: ['cve:read'] })
      )
    )

    renderWithQuery(<CvePage />)

    expect((await screen.findByText('更新数据库')).closest('button')?.disabled).toBe(true)
  })
})
