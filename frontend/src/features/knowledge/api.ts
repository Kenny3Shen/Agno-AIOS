import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { buildKnowledgeSearchPayload } from './utils'
import type {
  AddPathPayload,
  AddTextPayload,
  Document,
  KnowledgeIngestOptions,
  KnowledgeProgressEvent,
  KnowledgeResponse,
  KnowledgeSearchType,
  SearchResult,
  UpdateDocumentActionPayload,
  UpdateDocumentUploadPayload,
  UploadDocumentPayload,
} from './types'


const parseProgressData = (data: string): KnowledgeProgressEvent | null => {
  try {
    const value = JSON.parse(data) as KnowledgeProgressEvent
    if (!value || typeof value !== 'object' || typeof value.stage !== 'string') return null
    return value
  } catch {
    return null
  }
}

const consumeKnowledgeSse = async (
  stream: ReadableStream<Uint8Array>,
  onProgress: (event: KnowledgeProgressEvent) => void
): Promise<Document> => {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let document: Document | undefined
  let failed: Error | undefined

  const flush = (block: string) => {
    const lines = block.replace(/\r/g, '').split('\n')
    const event =
      lines
        .find((line) => line.startsWith('event:'))
        ?.slice(6)
        .trim() ?? 'message'
    const data = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (!data) return
    const payload = parseProgressData(data)
    if (!payload) return
    onProgress(payload)
    if (event === 'progress.completed' || (payload.stage === 'done' && payload.status === 'completed')) {
      if (payload.document) document = payload.document
    }
    if (event === 'progress.failed' || payload.status === 'failed') {
      if (payload.stage === 'done' || event === 'progress.failed') {
        failed = new Error(payload.error || payload.message || 'Document processing failed')
      }
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\n\n|\r\n\r\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(flush)
    if (done) break
  }
  if (buffer.trim()) flush(buffer)
  if (failed) throw failed
  if (!document) throw new Error('Stream ended without a document')
  return document
}

export type GetKnowledgeParams = {
  query?: string
  page?: number
  limit?: number
  sortBy?: 'updated_at' | 'created_at' | 'name' | 'status'
  sortOrder?: 'asc' | 'desc'
}

export const getKnowledge = (params: GetKnowledgeParams = {}) => {
  const search = new URLSearchParams()
  const query = (params.query || '').trim()
  if (query) search.set('query', query)
  search.set('page', String(Math.max(1, params.page ?? 1)))
  search.set('limit', String(Math.min(100, Math.max(1, params.limit ?? 12))))
  if (params.sortBy) search.set('sort_by', params.sortBy)
  if (params.sortOrder) search.set('sort_order', params.sortOrder)
  return requestJson<KnowledgeResponse>(`/knowledge?${search.toString()}`)
}
const readHttpError = async (response: Response) => {
  const payloadText = await response.text().catch(() => '')
  let message = `Request failed (${response.status})`
  try {
    const body = JSON.parse(payloadText) as { detail?: string; message?: string }
    message = body.detail || body.message || message
  } catch {
    if (payloadText) message = payloadText
  }
  return message
}

export const addText = (
  payload: AddTextPayload,
  options?: { stream?: boolean; onProgress?: (event: KnowledgeProgressEvent) => void }
) => {
  if (!options?.stream) {
    return requestJson<Document>('/knowledge/documents/text', jsonInit('POST', payload))
  }
  return (async () => {
    const response = await apiFetch('/knowledge/documents/text?stream=true', {
      ...jsonInit('POST', payload),
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    })
    if (!response.ok) throw new Error(await readHttpError(response))
    if (!response.body) throw new Error('Progress stream unavailable')
    return consumeKnowledgeSse(response.body, options?.onProgress ?? (() => undefined))
  })()
}
export const addFilePath = (
  payload: AddPathPayload,
  options?: { stream?: boolean; onProgress?: (event: KnowledgeProgressEvent) => void }
) => {
  if (!options?.stream) {
    return requestJson<Document>('/knowledge/documents/file', jsonInit('POST', payload))
  }
  return (async () => {
    const response = await apiFetch('/knowledge/documents/file?stream=true', {
      ...jsonInit('POST', payload),
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    })
    if (!response.ok) throw new Error(await readHttpError(response))
    if (!response.body) throw new Error('Progress stream unavailable')
    return consumeKnowledgeSse(response.body, options?.onProgress ?? (() => undefined))
  })()
}
const appendIngestOptions = (body: FormData, options?: KnowledgeIngestOptions) => {
  if (!options) return
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') body.append(key, String(value))
  })
}

export const uploadDocument = (
  { file, title, source, visibility, ingest_options }: UploadDocumentPayload,
  options?: { stream?: boolean; onProgress?: (event: KnowledgeProgressEvent) => void }
) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  if (!options?.stream) {
    return requestJson<Document>('/knowledge/documents/upload', { method: 'POST', body })
  }
  body.append('stream', 'true')
  return (async () => {
    const response = await apiFetch('/knowledge/documents/upload', {
      method: 'POST',
      body,
      headers: { Accept: 'text/event-stream' },
    })
    if (!response.ok) throw new Error(await readHttpError(response))
    if (!response.body) throw new Error('Progress stream unavailable')
    return consumeKnowledgeSse(response.body, options?.onProgress ?? (() => undefined))
  })()
}
export const updateDocumentAction = (
  id: string,
  payload: UpdateDocumentActionPayload,
  options?: { stream?: boolean; onProgress?: (event: KnowledgeProgressEvent) => void }
) => {
  const stream = Boolean(options?.stream && payload.mode !== 'metadata')
  if (!stream) {
    return requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/update`, jsonInit('POST', payload))
  }
  return (async () => {
    const response = await apiFetch(`/knowledge/documents/${encodeURIComponent(id)}/update?stream=true`, {
      ...jsonInit('POST', payload),
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    })
    if (!response.ok) {
      const payloadText = await response.text().catch(() => '')
      let message = `Request failed (${response.status})`
      try {
        const body = JSON.parse(payloadText) as { detail?: string; message?: string }
        message = body.detail || body.message || message
      } catch {
        if (payloadText) message = payloadText
      }
      throw new Error(message)
    }
    if (!response.body) throw new Error('Progress stream unavailable')
    return consumeKnowledgeSse(response.body, options?.onProgress ?? (() => undefined))
  })()
}
export const updateDocumentUpload = (
  id: string,
  { file, title, source, visibility, ingest_options }: UpdateDocumentUploadPayload,
  options?: { stream?: boolean; onProgress?: (event: KnowledgeProgressEvent) => void }
) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  if (visibility) body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  if (!options?.stream) {
    return requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/update/upload`, { method: 'POST', body })
  }
  body.append('stream', 'true')
  return (async () => {
    const response = await apiFetch(`/knowledge/documents/${encodeURIComponent(id)}/update/upload`, {
      method: 'POST',
      body,
      headers: { Accept: 'text/event-stream' },
    })
    if (!response.ok) {
      const payloadText = await response.text().catch(() => '')
      let message = `Request failed (${response.status})`
      try {
        const bodyJson = JSON.parse(payloadText) as { detail?: string; message?: string }
        message = bodyJson.detail || bodyJson.message || message
      } catch {
        if (payloadText) message = payloadText
      }
      throw new Error(message)
    }
    if (!response.body) throw new Error('Progress stream unavailable')
    return consumeKnowledgeSse(response.body, options?.onProgress ?? (() => undefined))
  })()
}
export const deleteDocument = (id: string) => requestJson(`/knowledge/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const searchKnowledge = async (query: string, limit: number, searchType?: KnowledgeSearchType) =>
  (
    await requestJson<{ results: SearchResult[] }>(
      '/knowledge/search',
      jsonInit('POST', buildKnowledgeSearchPayload(query, limit, searchType))
    )
  ).results
