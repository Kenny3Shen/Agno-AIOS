import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { AUTH_TOKEN_STORAGE_KEY } from '@/shared/auth/storage'
import { addText, searchKnowledge, updateDocumentAction, updateDocumentUpload, uploadDocument } from './api'
import type { Document } from './types'

const document: Document = {
  id: 'doc-1',
  title: 'Runbook',
  source: 'Papers',
  chunks: 3,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  visibility: 'private',
}

describe('knowledge document API', () => {
  it('uploads the selected document as authenticated multipart data', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(
      http.post('/api/knowledge/documents/upload', async ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Bearer token')
        expect(request.headers.get('content-type')).toContain('multipart/form-data')
        const body = await request.text()
        expect(body).toContain('name="file"')
        expect(body).toContain('Content-Type: text/markdown')
        expect(body).toContain('Security runbook')
        expect(body).toContain('SOC')
        expect(body).toContain('public')
        expect(body).toContain('name="chunk_size"')
        expect(body).toContain('1500')
        expect(body).toContain('name="markdown_split_on_headings"')
        expect(body).toContain('2')
        expect(body).toContain('name="reader_strategy"')
        expect(body).toContain('markdown')
        return HttpResponse.json(document)
      })
    )

    const result = await uploadDocument({
      file: new File(['# Runbook'], 'runbook.md', { type: 'text/markdown' }),
      title: ' Security runbook ',
      source: ' SOC ',
      visibility: 'public',
      ingest_options: { chunk_size: 1500, markdown_split_on_headings: 2, reader_strategy: 'markdown' },
    })

    expect(result.id).toBe('doc-1')
  })

  it('updates metadata without sending document content', async () => {
    server.use(
      http.post('/api/knowledge/documents/:id/update', async ({ params, request }) => {
        expect(params.id).toBe('doc/1')
        const body = await request.json()
        expect(body).toEqual({ mode: 'metadata', metadata: { title: 'Updated', source: 'Runbooks' } })
        expect(body).not.toHaveProperty('content')
        return HttpResponse.json({ ...document, title: 'Updated', source: 'Runbooks' })
      })
    )

    const result = await updateDocumentAction('doc/1', { mode: 'metadata', metadata: { title: 'Updated', source: 'Runbooks' } })

    expect(result.title).toBe('Updated')
  })

  it('uses update action when content must be revectorized', async () => {
    server.use(
      http.post('/api/knowledge/documents/:id/update', async ({ params, request }) => {
        expect(params.id).toBe('doc-1')
        expect(await request.json()).toEqual({
          mode: 'replace_text',
          file_name: 'runbook.md',
          content: '# New body',
          ingest_options: { chunk_overlap: 120, code_tokenizer: 'gpt2' },
        })
        return HttpResponse.json({ ...document, chunks: 4 })
      })
    )

    const result = await updateDocumentAction('doc-1', {
      mode: 'replace_text',
      file_name: 'runbook.md',
      content: '# New body',
      ingest_options: { chunk_overlap: 120, code_tokenizer: 'gpt2' },
    })

    expect(result.id).toBe('doc-1')
    expect(result.chunks).toBe(4)
  })

  it('sends rebuild ingest options only when advanced options are selected', async () => {
    server.use(
      http.post('/api/knowledge/documents/:id/update', async ({ params, request }) => {
        expect(params.id).toBe('doc-1')
        expect(await request.json()).toEqual({
          mode: 'rebuild',
          ingest_options: {
            chunk_size: 1800,
            markdown_split_on_headings: 2,
            reader_strategy: 'markdown',
          },
        })
        return HttpResponse.json({ ...document, chunks: 4 })
      })
    )

    const result = await updateDocumentAction('doc-1', {
      mode: 'rebuild',
      ingest_options: {
        chunk_size: 1800,
        markdown_split_on_headings: 2,
        reader_strategy: 'markdown',
      },
    })

    expect(result.chunks).toBe(4)
  })

  it('uploads a replacement file through the selected document endpoint', async () => {
    server.use(
      http.post('/api/knowledge/documents/:id/update/upload', async ({ params, request }) => {
        expect(params.id).toBe('doc/1')
        expect(request.headers.get('content-type')).toContain('multipart/form-data')
        const body = await request.text()
        expect(body).toContain('name="file"')
        expect(body).toContain('Content-Type: text/markdown')
        expect(body).toContain('name="title"')
        expect(body).toContain('Uploaded runbook')
        expect(body).toContain('name="source"')
        expect(body).toContain('IR')
        expect(body).toContain('name="visibility"')
        expect(body).toContain('public')
        expect(body).toContain('name="semantic_threshold"')
        expect(body).toContain('0.61')
        expect(body).toContain('name="csv_skip_header"')
        expect(body).toContain('true')
        return HttpResponse.json({ ...document, chunks: 4 })
      })
    )

    const result = await updateDocumentUpload('doc/1', {
      file: new File(['# Uploaded body'], 'uploaded.md', { type: 'text/markdown' }),
      title: ' Uploaded runbook ',
      source: ' IR ',
      visibility: 'public',
      ingest_options: { semantic_threshold: 0.61, csv_skip_header: true },
    })

    expect(result.id).toBe('doc-1')
    expect(result.chunks).toBe(4)
  })

  it('sends retrieval method in the search payload', async () => {
    server.use(
      http.post('/api/knowledge/search', async ({ request }) => {
        expect(await request.json()).toEqual({ query: 'policy', limit: 8, search_type: 'vector' })
        return HttpResponse.json({
          results: [{ content: '# Policy', score: 0.9, doc_id: 'doc-1', title: 'Policy', source: 'KB', chunk_index: 0 }],
        })
      })
    )

    const result = await searchKnowledge(' policy ', 8, 'vector')

    expect(result[0].doc_id).toBe('doc-1')
  })
})


describe('knowledge update progress stream', () => {
  it('streams progress events while replacing text', async () => {
    const seen: string[] = []
    const body = [
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
      'data: {"stage":"vectorize","status":"running","label":"向量化","message":"向量化中"}',
      '',
      'event: progress',
      'data: {"stage":"vectorize","status":"completed","label":"向量化","message":"已切换"}',
      '',
      'event: progress',
      'data: {"stage":"cleanup","status":"completed","label":"清理","message":"完成"}',
      '',
      'event: progress.completed',
      `data: ${JSON.stringify({ stage: 'done', status: 'completed', document })}`,
      '',
      '',
    ].join('\n')

    server.use(
      http.post('/api/knowledge/documents/:id/update', ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBe('true')
        return new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )

    const result = await updateDocumentAction(
      'doc-1',
      { mode: 'replace_text', file_name: 'runbook.md', content: '# body' },
      {
        stream: true,
        onProgress: (event) => {
          seen.push(`${event.stage}:${event.status}`)
        },
      }
    )

    expect(result.id).toBe('doc-1')
    expect(seen).toContain('parse:running')
    expect(seen).toContain('vectorize:completed')
    expect(seen).toContain('cleanup:completed')
  })
})


describe('knowledge create progress stream', () => {
  it('streams progress while creating an upload', async () => {
    const seen: string[] = []
    const body = [
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
      `data: ${JSON.stringify({ stage: 'done', status: 'completed', document })}`,
      '',
      '',
    ].join('\n')
    server.use(
      http.post('/api/knowledge/documents/upload', async ({ request }) => {
        const text = await request.text()
        expect(text).toContain('name="stream"')
        return new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    const result = await uploadDocument(
      { file: new File(['# Runbook'], 'runbook.md', { type: 'text/markdown' }), visibility: 'private' },
      { stream: true, onProgress: (event) => seen.push(`${event.stage}:${event.status}`) }
    )
    expect(result.id).toBe('doc-1')
    expect(seen).toContain('upload:running')
    expect(seen).toContain('vectorize:completed')
  })

  it('streams progress while creating text content', async () => {
    const seen: string[] = []
    const body = [
      'event: progress',
      'data: {"stage":"upload","status":"skipped","label":"上传","message":"跳过"}',
      '',
      'event: progress',
      'data: {"stage":"parse","status":"running","label":"解析","message":"解析中"}',
      '',
      'event: progress.completed',
      `data: ${JSON.stringify({ stage: 'done', status: 'completed', document })}`,
      '',
      '',
    ].join('\n')
    server.use(
      http.post('/api/knowledge/documents/text', ({ request }) => {
        expect(new URL(request.url).searchParams.get('stream')).toBe('true')
        return new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } })
      })
    )
    const result = await addText(
      { title: 'Note', content: 'hello', visibility: 'private' },
      { stream: true, onProgress: (event) => seen.push(`${event.stage}:${event.status}`) }
    )
    expect(result.id).toBe('doc-1')
    expect(seen).toContain('upload:skipped')
    expect(seen).toContain('parse:running')
  })
})
