import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import { buildKnowledgeSearchPayload } from './utils'
import type {
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

const normalizeDocument = (value: unknown): Document | null => {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const id = String(row.id ?? '').trim()
  if (!id) return null
  return {
    id,
    title: String(row.title ?? ''),
    source: String(row.source ?? ''),
    chunks: Number(row.chunks ?? 0) || 0,
    created_at: String(row.created_at ?? ''),
    updated_at: row.updated_at != null ? String(row.updated_at) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    visibility: row.visibility as Document['visibility'],
    owner_user_id: row.owner_user_id != null ? String(row.owner_user_id) : undefined,
    can_manage: row.can_manage === true,
    metadata:
      row.metadata && typeof row.metadata === 'object' && !Array.isArray(row.metadata)
        ? (row.metadata as Document['metadata'])
        : undefined,
  }
}

export const getKnowledge = async (params: GetKnowledgeParams = {}): Promise<KnowledgeResponse> => {
  const page = Math.max(1, params.page ?? 1)
  const limit = Math.min(100, Math.max(1, params.limit ?? 12))
  const search = new URLSearchParams()
  const query = (params.query || '').trim()
  if (query) search.set('query', query)
  search.set('page', String(page))
  search.set('limit', String(limit))
  if (params.sortBy) search.set('sort_by', params.sortBy)
  if (params.sortOrder) search.set('sort_order', params.sortOrder)
  const raw = await requestJson<unknown>(`/knowledge?${search.toString()}`)
  const envelope = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const list = normalizePaginatedList(raw, {
    page,
    limit,
    mapItem: normalizeDocument,
  })
  const metaRaw = envelope.meta && typeof envelope.meta === 'object' ? (envelope.meta as Record<string, unknown>) : {}
  return {
    data: list.data,
    meta: {
      ...list.meta,
      query: metaRaw.query != null ? String(metaRaw.query) : undefined,
      sort_by: metaRaw.sort_by != null ? String(metaRaw.sort_by) : undefined,
      sort_order: metaRaw.sort_order != null ? String(metaRaw.sort_order) : undefined,
    },
    status:
      envelope.status && typeof envelope.status === 'object'
        ? (envelope.status as KnowledgeResponse['status'])
        : {},
  }
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
export const searchKnowledge = async (
  query: string,
  limit: number,
  searchType?: KnowledgeSearchType,
): Promise<SearchResult[]> => {
  const raw = await requestJson<unknown>(
    '/knowledge/search',
    jsonInit('POST', buildKnowledgeSearchPayload(query, limit, searchType)),
  )
  const { data } = normalizePaginatedList(raw, {
    limit,
    mapItem: (row) => {
      if (!row || typeof row !== 'object') return null
      return row as SearchResult
    },
  })
  return data
}
