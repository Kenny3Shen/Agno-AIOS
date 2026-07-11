import { jsonInit, requestJson } from '@/shared/api/client'
import type { AddPathPayload, AddTextPayload, Document, KnowledgeIngestOptions, KnowledgeResponse, SearchResult, UpdateDocumentActionPayload, UpdateDocumentUploadPayload, UploadDocumentPayload } from './types'

export const getKnowledge = (query = '') => requestJson<KnowledgeResponse>(`/knowledge?limit=100${query ? `&query=${encodeURIComponent(query)}` : ''}`)
export const addText = (payload: AddTextPayload) => requestJson<Document>('/knowledge/documents/text', jsonInit('POST', payload))
export const addFilePath = (payload: AddPathPayload) => requestJson<Document>('/knowledge/documents/file', jsonInit('POST', payload))
const appendIngestOptions = (body: FormData, options?: KnowledgeIngestOptions) => {
  if (!options) return
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') body.append(key, String(value))
  })
}

export const uploadDocument = ({ file, title, source, visibility, ingest_options }: UploadDocumentPayload) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  return requestJson<Document>('/knowledge/documents/upload', { method: 'POST', body })
}
export const updateDocumentAction = (id: string, payload: UpdateDocumentActionPayload) => requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/update`, jsonInit('POST', payload))
export const updateDocumentUpload = (id: string, { file, title, source, visibility, ingest_options }: UpdateDocumentUploadPayload) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  if (visibility) body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  return requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/update/upload`, { method: 'POST', body })
}
export const deleteDocument = (id: string) => requestJson(`/knowledge/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const searchKnowledge = async (query: string, limit: number) => (await requestJson<{ results: SearchResult[] }>('/knowledge/search', jsonInit('POST', { query, limit }))).results
