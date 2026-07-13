import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { SkillsPage } from './SkillsPage'

describe('SkillsPage', () => {
  it('shows the delete control only when the server grants admin delete permission', async () => {
    server.use(
      http.get('/api/skills', () =>
        HttpResponse.json({
          skills: [
            {
              name: 'web-search',
              description: 'Searches the web',
              enabled: true,
              has_scripts: false,
              scripts: [],
              skill_markdown: '# Web search',
              visibility: 'private',
              owner_user_id: 'admin-1',
              can_manage: true,
              can_delete: true,
            },
          ],
        })
      )
    )

    renderWithQuery(<SkillsPage />)
    expect(await screen.findByLabelText('删除技能 web-search')).toBeTruthy()
  })
})
