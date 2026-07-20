import dayjs from 'dayjs'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/shared/i18n'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { setupUser } from '@/test/user'
import { ChatTaskPanel } from './ChatTaskPanel'
import { chatSessionFixture } from './testFixtures'

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({
    history: { push: vi.fn<(path: string) => void>(), replace: vi.fn<(path: string) => void>() },
  }),
  useRouterState: ({ select }: { select: (state: { location: { searchStr: string } }) => unknown }) =>
    select({ location: { searchStr: '' } }),
}))

describe('ChatTaskPanel load more', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('zh-CN')
  })

  it('loads the next page of conversations', async () => {
    const user = setupUser()
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get('page') || '1')
        if (page === 1) {
          return HttpResponse.json({
            data: [
              chatSessionFixture({
                session_id: 'session-1',
                preview: 'First page',
                created_at: dayjs().unix(),
                updated_at: dayjs().unix(),
              }),
            ],
            meta: { page: 1, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({
          data: [
            chatSessionFixture({
              session_id: 'session-2',
              preview: 'Second page',
              created_at: dayjs().unix(),
              updated_at: dayjs().unix(),
            }),
          ],
          meta: { page: 2, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
        })
      }),
    )
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText('First page')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText('Second page')).toBeTruthy()
  })

  it('keeps the first page when load-more fails', async () => {
    const user = setupUser()
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get('page') || '1')
        if (page === 1) {
          return HttpResponse.json({
            data: [
              chatSessionFixture({
                session_id: 'session-1',
                preview: 'First page stays',
                created_at: dayjs().unix(),
                updated_at: dayjs().unix(),
              }),
            ],
            meta: { page: 1, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({ detail: 'page 2 boom' }, { status: 500 })
      }),
    )
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText('First page stays')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText(i18n.t('shell:conversations.loadMoreFailed'))).toBeTruthy()
    expect(screen.getByText('First page stays')).toBeTruthy()
    expect(screen.queryByText(i18n.t('shell:conversations.loadFailed'))).toBeNull()
  })
})
