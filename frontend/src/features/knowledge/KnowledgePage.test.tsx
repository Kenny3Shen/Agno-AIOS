import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { renderWithQuery } from '@/test/render'
import { KnowledgePage } from './KnowledgePage'
import type { Document, KnowledgeResponse } from './types'

const oldDocument: Document = {
  id: 'doc-old',
  title: 'Runbook',
  source: 'Papers',
  chunks: 3,
  created_at: '2026-01-01T00:00:00Z',
  status: 'completed',
  visibility: 'private',
  owner_user_id: 'user-1',
  can_manage: true,
  metadata: { file_name: 'runbook.md' },
}

const response = (document: Document): KnowledgeResponse => ({
  status: {},
  documents: [document],
  pagination: { page: 1, limit: 100, total: 1 },
})

describe('knowledge document workflow', () => {
  it('keeps the replacement document selected when revectorization changes its ID', async () => {
    const user = userEvent.setup()
    const newDocument = { ...oldDocument, id: 'doc-new', chunks: 4 }
    let replaced = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/source', async ({ request }) => {
        expect(await request.json()).toEqual({ file_name: 'runbook.md', content: '# Updated runbook' })
        replaced = true
        return HttpResponse.json(newDocument)
      }),
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await user.click(screen.getByRole('button', { name: /更新/ }))
    await user.click(await screen.findByRole('tab', { name: 'Text' }))
    await user.type(screen.getByLabelText('新正文'), '# Updated runbook')
    await user.click(screen.getByRole('button', { name: /重新向量化/ }))

    await waitFor(() => expect(screen.getByText('doc-new')).toBeTruthy())
    expect(screen.queryByText('doc-old')).toBeNull()
  })

  it('keeps the uploaded replacement selected when revectorization changes its ID', async () => {
    const user = userEvent.setup()
    const newDocument = { ...oldDocument, id: 'doc-uploaded', chunks: 5, metadata: { file_name: 'uploaded.md' } }
    let replaced = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/source/upload', async ({ request }) => {
        const body = await request.text()
        expect(body).toContain('name="file"')
        expect(body).toContain('Content-Type: text/markdown')
        replaced = true
        return HttpResponse.json(newDocument)
      }),
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await user.click(screen.getByRole('button', { name: /更新/ }))
    await user.click(await screen.findByRole('tab', { name: 'Upload' }))
    const input = document.querySelector('input[type="file"]')
    expect(input).toBeTruthy()
    await user.upload(input as HTMLInputElement, new File(['# Uploaded runbook'], 'uploaded.md', { type: 'text/markdown' }))
    await user.click(screen.getByRole('button', { name: /重新向量化/ }))

    await waitFor(() => expect(screen.getByText('doc-uploaded')).toBeTruthy())
    expect(screen.queryByText('doc-old')).toBeNull()
  })
})
