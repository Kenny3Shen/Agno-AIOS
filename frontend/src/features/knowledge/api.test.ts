import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { AUTH_TOKEN_STORAGE_KEY } from '@/shared/auth/storage'
import { replaceDocumentSource, replaceDocumentSourceFile, updateDocument, uploadDocument } from './api'
import type { Document } from './types'

const document: Document = {
  id: 'doc-1',
  title: 'Runbook',
  source: 'Papers',
  chunks: 3,
  created_at: '2026-01-01T00:00:00Z',
  visibility: 'private',
}

describe('knowledge document API', () => {
  it('uploads the selected document as authenticated multipart data', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(http.post('/api/knowledge/documents/upload', async ({ request }) => {
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
      expect(body).toContain('name="reader_strategy"')
      expect(body).toContain('markdown')
      return HttpResponse.json(document)
    }))

    const result = await uploadDocument({
      file: new File(['# Runbook'], 'runbook.md', { type: 'text/markdown' }),
      title: ' Security runbook ',
      source: ' SOC ',
      visibility: 'public',
      ingest_options: { chunk_size: 1500, reader_strategy: 'markdown' },
    })

    expect(result.id).toBe('doc-1')
  })

  it('updates metadata without sending document content', async () => {
    server.use(http.patch('/api/knowledge/documents/:id', async ({ params, request }) => {
      expect(params.id).toBe('doc/1')
      const body = await request.json()
      expect(body).toEqual({ title: 'Updated', source: 'Runbooks' })
      expect(body).not.toHaveProperty('content')
      return HttpResponse.json({ ...document, title: 'Updated', source: 'Runbooks' })
    }))

    const result = await updateDocument('doc/1', { title: 'Updated', source: 'Runbooks' })

    expect(result.title).toBe('Updated')
  })

  it('uses the source replacement endpoint when content must be revectorized', async () => {
    server.use(http.post('/api/knowledge/documents/:id/source', async ({ params, request }) => {
      expect(params.id).toBe('doc-1')
      expect(await request.json()).toEqual({
        file_name: 'runbook.md',
        content: '# New body',
        ingest_options: { chunk_overlap: 120 },
      })
      return HttpResponse.json({ ...document, id: 'doc-2' })
    }))

    const result = await replaceDocumentSource('doc-1', { file_name: 'runbook.md', content: '# New body', ingest_options: { chunk_overlap: 120 } })

    expect(result.id).toBe('doc-2')
  })

  it('uploads a replacement file through the selected document endpoint', async () => {
    server.use(http.post('/api/knowledge/documents/:id/source/upload', async ({ params, request }) => {
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
      return HttpResponse.json({ ...document, id: 'doc-2', chunks: 4 })
    }))

    const result = await replaceDocumentSourceFile('doc/1', {
      file: new File(['# Uploaded body'], 'uploaded.md', { type: 'text/markdown' }),
      title: ' Uploaded runbook ',
      source: ' IR ',
      visibility: 'public',
      ingest_options: { semantic_threshold: 0.61 },
    })

    expect(result.id).toBe('doc-2')
    expect(result.chunks).toBe(4)
  })
})
