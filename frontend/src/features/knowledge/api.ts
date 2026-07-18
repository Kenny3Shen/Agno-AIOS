import { jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import { buildKnowledgeSearchPayload } from './utils'
import type {
  AddTextPayload,
  Document,
  KnowledgeIngestOptions,
  KnowledgeResponse,
  KnowledgeSearchType,
  SearchResult,
  UpdateDocumentActionPayload,
  UpdateDocumentUploadPayload,
  UploadDocumentPayload,
} from './types'

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

const appendIngestOptions = (body: FormData, options?: KnowledgeIngestOptions) => {
  if (!options) return
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') body.append(key, String(value))
  })
}

export const addText = (payload: AddTextPayload) =>
  requestJson<Document>('/knowledge/documents/text', jsonInit('POST', payload))

export const uploadDocument = ({
  file,
  title,
  source,
  visibility,
  ingest_options,
}: UploadDocumentPayload) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  return requestJson<Document>('/knowledge/documents/upload', { method: 'POST', body })
}

export const updateDocumentAction = (id: string, payload: UpdateDocumentActionPayload) =>
  requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/update`, jsonInit('POST', payload))

export const updateDocumentUpload = (
  id: string,
  { file, title, source, visibility, ingest_options }: UpdateDocumentUploadPayload,
) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  if (visibility) body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  return requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/update/upload`, {
    method: 'POST',
    body,
  })
}

export const deleteDocument = (id: string) =>
  requestJson(`/knowledge/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })

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
