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
  status: {},
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
      }),
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
        expect(await request.json()).toEqual({ mode: 'replace_text', file_name: 'runbook.md', content: '# Updated runbook' })
        replaced = true
        return HttpResponse.json(newDocument)
      }),
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    await user.click(await screen.findByRole('tab', { name: 'Text' }))
    await user.type(screen.getByLabelText('新正文'), '# Updated runbook')
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('4')).toBeTruthy())
    expect(screen.getByText('doc-old')).toBeTruthy()
  })

  it('keeps the document selected when uploaded replacement revectorizes in place', async () => {
    const user = userEvent.setup()
    const newDocument = { ...oldDocument, chunks: 5, metadata: { file_name: 'uploaded.md' } }
    let replaced = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(replaced ? newDocument : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update/upload', async ({ request }) => {
        const body = await request.text()
        expect(body).toContain('name="file"')
        expect(body).toContain('Content-Type: text/markdown')
        replaced = true
        return HttpResponse.json(newDocument)
      }),
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    const input = document.querySelector('input[type="file"]')
    expect(input).toBeTruthy()
    await user.upload(input as HTMLInputElement, new File(['# Uploaded runbook'], 'uploaded.md', { type: 'text/markdown' }))
    await user.click(screen.getByRole('button', { name: /保存/ }))

    await waitFor(() => expect(screen.getByText('5')).toBeTruthy())
    expect(screen.getByText('doc-old')).toBeTruthy()
  })

  it('submits rebuild advanced chunking options from the update tab', async () => {
    const user = userEvent.setup()
    const rebuilt = { ...oldDocument, chunks: 6, metadata: { file_name: 'runbook.md', chunk_size: '1800' } }
    let rebuiltDocument = false
    server.use(
      http.get('/api/knowledge', () => HttpResponse.json(response(rebuiltDocument ? rebuilt : oldDocument))),
      http.post('/api/knowledge/documents/doc-old/update', async ({ request }) => {
        expect(await request.json()).toEqual({ mode: 'rebuild', ingest_options: { chunk_size: 1800 } })
        rebuiltDocument = true
        return HttpResponse.json(rebuilt)
      }),
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    await user.click(await screen.findByText('高级分块参数'))
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
      }),
    )
    renderWithQuery(<KnowledgePage />)

    await user.click(await screen.findByText('Runbook'))
    await clickUpdateAction(user)
    const [button] = screen.getAllByRole('button', { name: /保存/ })
    fireEvent.click(button)

    expect(updateCalls).toBe(0)
  })
})
