import { jsonInit, requestJson } from '@/shared/api/client'
import type { ResourceVisibility } from '@/shared/types/common'
import type { AddPathPayload, AddTextPayload, Document, KnowledgeIngestOptions, KnowledgeResponse, ReplaceSourceFilePayload, ReplaceSourcePayload, SearchResult, UpdateDocumentPayload, UploadDocumentPayload } from './types'

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
export const updateDocument = (id: string, payload: UpdateDocumentPayload) => requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}`, jsonInit('PATCH', payload))
export const replaceDocumentSource = (id: string, payload: ReplaceSourcePayload) => requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/source`, jsonInit('POST', payload))
export const replaceDocumentSourceFile = (id: string, { file, title, source, visibility, ingest_options }: ReplaceSourceFilePayload) => {
  const body = new FormData()
  body.append('file', file, file.name)
  if (title?.trim()) body.append('title', title.trim())
  if (source?.trim()) body.append('source', source.trim())
  if (visibility) body.append('visibility', visibility)
  appendIngestOptions(body, ingest_options)
  return requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/source/upload`, { method: 'POST', body })
}
export const setVisibility = (id: string, visibility: ResourceVisibility) => requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/visibility`, jsonInit('PUT', { visibility }))
export const rebuildDocument = (id: string) => requestJson<Document>(`/knowledge/documents/${encodeURIComponent(id)}/rebuild`, { method: 'POST' })
export const deleteDocument = (id: string) => requestJson(`/knowledge/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const searchKnowledge = async (query: string, limit: number) => (await requestJson<{ results: SearchResult[] }>('/knowledge/search', jsonInit('POST', { query, limit }))).results
