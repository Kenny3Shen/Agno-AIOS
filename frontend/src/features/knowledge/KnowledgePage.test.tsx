import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { setupUser } from '@/test/user'
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
  updated_at: '2026-01-01T00:00:00Z',
  status: 'completed',
  visibility: 'private',
  owner_user_id: 'user-1',
  can_manage: true,
  metadata: { file_name: 'runbook.md' },
}

const response = (document: Document): KnowledgeResponse => ({
  data: [document],
  meta: {
    page: 1,
    limit: 100,
    total_pages: 1,
    total_count: 1,
    search_time_ms: 0,
    ingest_defaults: { search_type: 'hybrid', chunk_size: 1200, chunk_overlap: 160, code_chunk_size: 1800, semantic_threshold: 0.52 },
  },
})

async function clickUpdateAction(user: ReturnType<typeof setupUser>) {
  const button = document.querySelector('button[aria-label="更新 Runbook"]')
  expect(button).toBeTruthy()
  await user.click(button as HTMLButtonElement)
}

describe('knowledge document workflow', () => {
  it('keeps the document selected when uploaded replacement revectorizes in place', async () => {
    const user = setupUser()
    const newDocument = { ...oldDocument, chunks: 5, metadata: { file_name: 'uploaded.md' } }
    let replaced = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update/upload', async ({ request }) => {
        const body = await request.text()
        expect(body).toContain('name="file"')
        expect(body).toContain('Content-Type: text/markdown')
        replaced = true
        return HttpResponse.json({ ...newDocument, status: 'processing', id: 'processing:update-upload:doc-old' })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    const input = document.querySelector('input[type="file"]')
    expect(input).toBeTruthy()
    await user.upload(input as HTMLInputElement, new File(['# Uploaded runbook'], 'uploaded.md', { type: 'text/markdown' }))
    await user.click(screen.getByRole('button', { name: /保存/ }))

    // Drawer closes after queued ingest; list refreshes to completed document.
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /更新/ })).toBeNull())
    await waitFor(() => expect(screen.getByText('5')).toBeTruthy())
  })


  it('shows render mode controls inside each retrieval result', async () => {
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))),
      http.post('/api/knowledge/search', () =>
        HttpResponse.json({
          data: [
            { content: '{"risk":"high"}', score: 0.91, doc_id: 'doc-json', title: 'JSON result', source: 'KB', chunk_index: 0 },
            { content: '# Markdown result', score: 0.82, doc_id: 'doc-md', title: 'Markdown result', source: 'KB', chunk_index: 1 },
          ],
          meta: { page: 1, limit: 8, total_pages: 1, total_count: 2, search_time_ms: 0 },
        })
      )
    )
    renderWithQuery(<KnowledgePage />)

    fireEvent.click(await screen.findByRole('tab', { name: '检索试验台' }))
    fireEvent.change(screen.getByPlaceholderText('测试检索查询'), { target: { value: 'policy' } })
    fireEvent.click(screen.getByRole('button', { name: /检\s*索/ }))

    expect(await screen.findByRole('combobox', { name: '渲染 JSON result' })).toBeTruthy()
    expect(screen.getByRole('combobox', { name: '渲染 Markdown result' })).toBeTruthy()
    expect(screen.getByText(/risk/)).toBeTruthy()
    expect(screen.getByText(/high/)).toBeTruthy()
  })


})
