import dayjs from 'dayjs'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/shared/i18n'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
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

describe('ChatTaskPanel', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('zh-CN')
  })

  it('renders the first page of conversations without load-more', async () => {
    server.use(
      http.get('/api/chat/sessions', () =>
        HttpResponse.json({
          data: [
            chatSessionFixture({
              session_id: 'session-1',
              preview: 'Recent chat',
              created_at: dayjs().unix(),
              updated_at: dayjs().unix(),
            }),
          ],
          meta: { page: 1, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
        }),
      ),
    )
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText('Recent chat')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('shows load failure when the sessions request fails', async () => {
    server.use(http.get('/api/chat/sessions', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText(i18n.t('shell:conversations.loadFailed'))).toBeTruthy()
  })
})
