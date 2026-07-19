import { jsonInit, requestJson } from '@/shared/api/client'
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

type GetKnowledgeParams = {
  query?: string
  page?: number
  limit?: number
  sortBy?: 'updated_at' | 'created_at' | 'name' | 'status'
  sortOrder?: 'asc' | 'desc'
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
  return requestJson<KnowledgeResponse>(`/knowledge?${search.toString()}`)
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
  const payload = await requestJson<{ data: SearchResult[] }>(
    '/knowledge/search',
    jsonInit('POST', buildKnowledgeSearchPayload(query, limit, searchType)),
  )
  return payload.data
}
