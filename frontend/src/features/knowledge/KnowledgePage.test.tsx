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
  meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, search_time_ms: 0 },
  status: {
    rag_settings: { search_type: 'hybrid', chunk_size: 1200, chunk_overlap: 160, code_chunk_size: 1800, semantic_threshold: 0.52 },
  },
})

async function clickUpdateAction(user: ReturnType<typeof setupUser>) {
  const button = document.querySelector('button[aria-label="更新 Runbook"]')
  expect(button).toBeTruthy()
  await user.click(button as HTMLButtonElement)
}

describe('knowledge document workflow', () => {
  it('submits metadata-only changes from the update tab', async () => {
    const user = setupUser()
    const updated = { ...oldDocument, source: 'Runbooks' }
    let saved = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(saved ? updated : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(await request.json()).toEqual({ mode: 'metadata', metadata: { source: 'Runbooks' } })
        saved = true
        return HttpResponse.json(updated)
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    const source = await screen.findByLabelText('来源')
    await user.clear(source)
    await user.type(source, 'Runbooks')
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getAllByText('Runbooks').length).toBeGreaterThan(0))
  })

  it('keeps the document selected when text replacement revectorizes in place', async () => {
    const user = setupUser()
    const newDocument = { ...oldDocument, chunks: 4 }
    let replaced = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBeNull()
        expect(await request.json()).toEqual({ mode: 'replace_text', file_name: 'runbook.md', content: '# Updated runbook' })
        replaced = true
        return HttpResponse.json({ ...newDocument, status: 'processing' })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    await user.click(await screen.findByRole('tab', { name: '文本' }))
    fireEvent.change(screen.getByLabelText('新正文'), { target: { value: '# Updated runbook' } })
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('4')).toBeTruthy())
    expect(screen.getByText('doc-old')).toBeTruthy()
  })

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


  it('submits rebuild advanced chunking options from the update tab', async () => {
    const user = setupUser()
    const rebuilt = { ...oldDocument, chunks: 6, metadata: { file_name: 'runbook.md', chunk_size: '1800' } }
    let rebuiltDocument = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(rebuiltDocument ? rebuilt : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBeNull()
        expect(await request.json()).toEqual({ mode: 'rebuild', ingest_options: { chunk_size: 1800 } })
        rebuiltDocument = true
        return HttpResponse.json({ ...rebuilt, status: 'processing' })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    fireEvent.click(await screen.findByText('高级分块参数'))
    await user.type(screen.getByRole('spinbutton', { name: /章节上限/ }), '1800')
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('6')).toBeTruthy())
  })

  it('shows a single save action in the tab bar without an explicit rebuild switch', async () => {
    const user = setupUser()
    server.use(http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))))
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)

    expect(screen.getByRole('tab', { name: '更新' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '文本' })).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /保存/ })).toHaveLength(1)
    expect(screen.queryByRole('switch', { name: /重新生成向量索引/ })).toBeNull()
  })

  it('does not call update when the update tab has no changes', async () => {
    const user = setupUser()
    let updateCalls = 0
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', () => {
        updateCalls += 1
        return HttpResponse.json(oldDocument)
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    const [button] = screen.getAllByRole('button', { name: /保存/ })
    fireEvent.click(button)

    expect(updateCalls).toBe(0)
  })

  it('shows retrieval controls with runtime search defaults', async () => {
    server.use(http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))))
    renderWithQuery(<KnowledgePage />)

    fireEvent.click(await screen.findByRole('tab', { name: '检索试验台' }))

    expect(screen.getByPlaceholderText('测试检索查询')).toBeTruthy()
    expect(screen.getByRole('combobox', { name: '检索类型' })).toBeTruthy()
    expect(screen.getByText('hybrid')).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: 'Result render mode' })).toBeNull()
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


  it('shows concrete advanced chunking defaults from runtime settings', async () => {
    const user = setupUser()
    server.use(http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))))
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('添加文档'))
    fireEvent.click(await screen.findByText('高级分块参数'))

    expect(screen.getByPlaceholderText('1200')).toBeTruthy()
    expect(screen.getByPlaceholderText('0.52')).toBeTruthy()
  })
})
