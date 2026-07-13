import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
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
  status: {
    rag_settings: { search_type: 'hybrid', chunk_size: 1200, chunk_overlap: 160, code_chunk_size: 1800, semantic_threshold: 0.52 },
  },
  documents: [document],
  pagination: { page: 1, limit: 100, total: 1 },
})

async function clickUpdateAction(user: ReturnType<typeof userEvent.setup>) {
  const button = document.querySelector('button[aria-label="更新 Runbook"]')
  expect(button).toBeTruthy()
  await user.click(button as HTMLButtonElement)
}

describe('knowledge document workflow', () => {
  it('submits metadata-only changes from the update tab', async () => {
    const user = userEvent.setup()
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
    const source = await screen.findByLabelText('Source')
    await user.clear(source)
    await user.type(source, 'Runbooks')
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('Runbooks')).toBeTruthy())
  })

  it('keeps the document selected when text replacement revectorizes in place', async () => {
    const user = userEvent.setup()
    const newDocument = { ...oldDocument, chunks: 4 }
    let replaced = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBe('true')
        expect(await request.json()).toEqual({ mode: 'replace_text', file_name: 'runbook.md', content: '# Updated runbook' })
        replaced = true
        const streamBody = [
          'event: progress.completed',
          `data: ${JSON.stringify({ stage: 'done', status: 'completed', document: newDocument })}`,
          '',
          '',
        ].join('\n')
        return new HttpResponse(streamBody, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    await user.click(await screen.findByRole('tab', { name: 'Text' }))
    fireEvent.change(screen.getByLabelText('新正文'), { target: { value: '# Updated runbook' } })
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('4')).toBeTruthy())
    expect(screen.getByText('doc-old')).toBeTruthy()
  })

  it('keeps the document selected when uploaded replacement revectorizes in place', async () => {
    const user = userEvent.setup()
    const newDocument = { ...oldDocument, chunks: 5, metadata: { file_name: 'uploaded.md' } }
    let replaced = false
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update/upload', async ({ request }) => {
        const body = await request.text()
        expect(body).toContain('name="file"')
        expect(body).toContain('Content-Type: text/markdown')
        expect(body).toContain('name="stream"')
        await gate
        replaced = true
        const streamBody = [
          'event: progress',
          'data: {"stage":"upload","status":"running","label":"上传","message":"上传中"}',
          '',
          'event: progress',
          'data: {"stage":"upload","status":"completed","label":"上传","message":"已上传"}',
          '',
          'event: progress',
          'data: {"stage":"parse","status":"completed","label":"解析","message":"已解析"}',
          '',
          'event: progress',
          'data: {"stage":"vectorize","status":"completed","label":"向量化","message":"已切换"}',
          '',
          'event: progress',
          'data: {"stage":"cleanup","status":"completed","label":"清理","message":"完成"}',
          '',
          'event: progress.completed',
          `data: ${JSON.stringify({ stage: 'done', status: 'completed', document: newDocument })}`,
          '',
          '',
        ].join('\n')
        return new HttpResponse(streamBody, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    const input = document.querySelector('input[type="file"]')
    expect(input).toBeTruthy()
    await user.upload(input as HTMLInputElement, new File(['# Uploaded runbook'], 'uploaded.md', { type: 'text/markdown' }))
    await user.click(screen.getByRole('button', { name: /保存/ }))

    expect(await screen.findByText('上传')).toBeTruthy()
    expect(screen.getByText('解析')).toBeTruthy()
    expect(screen.getByText('向量化')).toBeTruthy()
    expect(screen.getByText('清理')).toBeTruthy()
    release()

    await waitFor(() => expect(screen.getByText('5')).toBeTruthy())
    expect(screen.getByText('doc-old')).toBeTruthy()
  })

  it('shows four-stage progress while replacing text content', async () => {
    const user = userEvent.setup()
    const newDocument = { ...oldDocument, chunks: 4 }
    let replaced = false
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBe('true')
        await gate
        replaced = true
        const streamBody = [
          'event: progress',
          'data: {"stage":"upload","status":"skipped","label":"上传","message":"跳过"}',
          '',
          'event: progress',
          'data: {"stage":"parse","status":"running","label":"解析","message":"解析中"}',
          '',
          'event: progress',
          'data: {"stage":"parse","status":"completed","label":"解析","message":"已解析"}',
          '',
          'event: progress',
          'data: {"stage":"vectorize","status":"completed","label":"向量化","message":"已切换"}',
          '',
          'event: progress',
          'data: {"stage":"cleanup","status":"completed","label":"清理","message":"完成"}',
          '',
          'event: progress.completed',
          `data: ${JSON.stringify({ stage: 'done', status: 'completed', document: newDocument })}`,
          '',
          '',
        ].join('\n')
        return new HttpResponse(streamBody, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    await user.click(await screen.findByRole('tab', { name: 'Text' }))
    fireEvent.change(screen.getByLabelText('新正文'), { target: { value: '# Updated runbook' } })
    await user.click(screen.getByRole('button', { name: /保存/ }))

    expect(await screen.findByText('解析')).toBeTruthy()
    expect(screen.getByText('向量化')).toBeTruthy()
    expect(screen.getByText('清理')).toBeTruthy()
    release()
    await waitFor(() => expect(screen.getByText('4')).toBeTruthy())
  })

  it('submits rebuild advanced chunking options from the update tab', async () => {
    const user = userEvent.setup()
    const rebuilt = { ...oldDocument, chunks: 6, metadata: { file_name: 'runbook.md', chunk_size: '1800' } }
    let rebuiltDocument = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(rebuiltDocument ? rebuilt : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBe('true')
        expect(await request.json()).toEqual({ mode: 'rebuild', ingest_options: { chunk_size: 1800 } })
        rebuiltDocument = true
        const streamBody = [
          'event: progress.completed',
          `data: ${JSON.stringify({ stage: 'done', status: 'completed', document: rebuilt })}`,
          '',
          '',
        ].join('\n')
        return new HttpResponse(streamBody, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    fireEvent.click(await screen.findByText('高级分块参数'))
    await user.type(screen.getByRole('spinbutton', { name: /Section max size/ }), '1800')
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('6')).toBeTruthy())
  })

  it('shows a single save action in the tab bar without an explicit rebuild switch', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))))
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)

    expect(screen.getByRole('tab', { name: 'Update' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Text' })).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /保存/ })).toHaveLength(1)
    expect(screen.queryByRole('switch', { name: /重新生成向量索引/ })).toBeNull()
  })

  it('does not call update when the update tab has no changes', async () => {
    const user = userEvent.setup()
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

    fireEvent.click(await screen.findByRole('tab', { name: 'Retrieval playground' }))

    expect(screen.getByPlaceholderText('测试检索查询')).toBeTruthy()
    expect(screen.getByRole('combobox', { name: 'Search type' })).toBeTruthy()
    expect(screen.getByText('hybrid')).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: 'Result render mode' })).toBeNull()
  })

  it('shows render mode controls inside each retrieval result', async () => {
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))),
      http.post('/api/knowledge/search', () =>
        HttpResponse.json({
          results: [
            { content: '{"risk":"high"}', score: 0.91, doc_id: 'doc-json', title: 'JSON result', source: 'KB', chunk_index: 0 },
            { content: '# Markdown result', score: 0.82, doc_id: 'doc-md', title: 'Markdown result', source: 'KB', chunk_index: 1 },
          ],
        })
      )
    )
    renderWithQuery(<KnowledgePage />)

    fireEvent.click(await screen.findByRole('tab', { name: 'Retrieval playground' }))
    fireEvent.change(screen.getByPlaceholderText('测试检索查询'), { target: { value: 'policy' } })
    fireEvent.click(screen.getByRole('button', { name: /检\s*索/ }))

    expect(await screen.findByRole('combobox', { name: 'Render JSON result' })).toBeTruthy()
    expect(screen.getByRole('combobox', { name: 'Render Markdown result' })).toBeTruthy()
    expect(screen.getByText(/risk/)).toBeTruthy()
    expect(screen.getByText(/high/)).toBeTruthy()
  })

  it('shows four-stage progress while creating an upload', async () => {
    const user = userEvent.setup()
    const created = { ...oldDocument, id: 'doc-new', chunks: 2 }
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let createdDocument = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(createdDocument ? created : oldDocument))),
      http.post('/api/knowledge/documents/upload', async ({ request }) => {
        const body = await request.text()
        expect(body).toContain('name="stream"')
        await gate
        createdDocument = true
        const streamBody = [
          'event: progress',
          'data: {"stage":"upload","status":"running","label":"上传","message":"上传中"}',
          '',
          'event: progress',
          'data: {"stage":"parse","status":"completed","label":"解析","message":"已解析"}',
          '',
          'event: progress',
          'data: {"stage":"vectorize","status":"completed","label":"向量化","message":"已写入"}',
          '',
          'event: progress',
          'data: {"stage":"cleanup","status":"completed","label":"清理","message":"完成"}',
          '',
          'event: progress.completed',
          `data: ${JSON.stringify({ stage: 'done', status: 'completed', document: created })}`,
          '',
          '',
        ].join('\n')
        return new HttpResponse(streamBody, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('添加文档'))
    const input = document.querySelector('input[type="file"]')
    expect(input).toBeTruthy()
    await user.upload(input as HTMLInputElement, new File(['# New'], 'new.md', { type: 'text/markdown' }))
    await user.click(screen.getByRole('button', { name: /上传并入库/ }))

    expect(await screen.findByText('上传')).toBeTruthy()
    expect(screen.getByText('解析')).toBeTruthy()
    expect(screen.getByText('向量化')).toBeTruthy()
    expect(screen.getByText('清理')).toBeTruthy()
    release()
    await waitFor(() => expect(screen.queryByText('添加知识文档')).toBeNull())
  })

  it('shows concrete advanced chunking defaults from runtime settings', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/knowledge', () => HttpResponse.json(response(oldDocument))))
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('添加文档'))
    fireEvent.click(await screen.findByText('高级分块参数'))

    expect(screen.getByPlaceholderText('1200')).toBeTruthy()
    expect(screen.getByPlaceholderText('0.52')).toBeTruthy()
  })
})
