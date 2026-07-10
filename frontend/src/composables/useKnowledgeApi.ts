import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  KnowledgeDocument,
  KnowledgeDocumentUpdateRequest,
  KnowledgeFileRequest,
  KnowledgePagination,
  KnowledgeRagSettings,
  KnowledgeRagSettingsResponse,
  KnowledgeSearchResponse,
  KnowledgeSourceReplacementRequest,
  KnowledgeStatusResponse,
  KnowledgeTextRequest,
  ResourceVisibility
} from '../types'

/**
 * RAG knowledge management API.
 */
export function useKnowledgeApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const request = async <T>(path = '', options: RequestInit = {}, fallback = apiMessage('knowledgeRequestFailed')): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(`/knowledge${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {})
        }
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, fallback))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, fallback)
      throw err
    } finally {
      loading.value = false
    }
  }

  const fetchKnowledge = (params?: Partial<Pick<KnowledgePagination, 'page' | 'limit' | 'query' | 'sort_by' | 'sort_order'>>) => {
    const search = new URLSearchParams()
    if (params?.page) search.set('page', String(params.page))
    if (params?.limit) search.set('limit', String(params.limit))
    if (params?.query) search.set('query', params.query)
    if (params?.sort_by) search.set('sort_by', params.sort_by)
    if (params?.sort_order) search.set('sort_order', params.sort_order)
    const suffix = search.size ? `?${search.toString()}` : ''
    return request<KnowledgeStatusResponse>(suffix, {}, apiMessage('knowledgeLoadFailed'))
  }

  const addTextDocument = (payload: KnowledgeTextRequest) => request<KnowledgeDocument>('/documents/text', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeWriteFailed'))

  const addFileDocument = (payload: KnowledgeFileRequest) => request<KnowledgeDocument>('/documents/file', {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeImportFailed'))

  const deleteKnowledgeDocument = (docId: string) => request<{ success: boolean }>(`/documents/${encodeURIComponent(docId)}`, {
    method: 'DELETE'
  }, apiMessage('knowledgeDeleteFailed'))

  const rebuildKnowledgeDocument = (docId: string) => request<KnowledgeDocument>(`/documents/${encodeURIComponent(docId)}/rebuild`, {
    method: 'POST'
  }, apiMessage('knowledgeRequestFailed'))

  const replaceKnowledgeDocumentSource = (docId: string, payload: KnowledgeSourceReplacementRequest) => request<KnowledgeDocument>(`/documents/${encodeURIComponent(docId)}/source`, {
    method: 'POST',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeRequestFailed'))

  const updateKnowledgeDocumentMetadata = (docId: string, payload: KnowledgeDocumentUpdateRequest) => request<KnowledgeDocument>(`/documents/${encodeURIComponent(docId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeRequestFailed'))

  const updateKnowledgeDocumentVisibility = (docId: string, visibility: ResourceVisibility) => request<KnowledgeDocument>(`/documents/${encodeURIComponent(docId)}/visibility`, {
    method: 'PUT',
    body: JSON.stringify({ visibility })
  }, apiMessage('knowledgeRequestFailed'))

  const updateKnowledgeRagSettings = (payload: KnowledgeRagSettings) => request<KnowledgeRagSettingsResponse>('/settings/rag', {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }, apiMessage('knowledgeRequestFailed'))

  const clearKnowledge = () => request<{
    documents: number
    chunks: number
    deleted_documents: number
    deleted_ids: string[]
    failed_ids: string[]
  }>('', {
    method: 'DELETE'
  }, apiMessage('knowledgeClearFailed'))

  const searchKnowledge = (query: string, limit: number, searchType?: string) => request<KnowledgeSearchResponse>('/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit, search_type: searchType || undefined })
  }, apiMessage('knowledgeSearchFailed'))

  return {
    loading,
    error,
    fetchKnowledge,
    addTextDocument,
    addFileDocument,
    updateKnowledgeDocumentMetadata,
    updateKnowledgeDocumentVisibility,
    rebuildKnowledgeDocument,
    replaceKnowledgeDocumentSource,
    updateKnowledgeRagSettings,
    deleteKnowledgeDocument,
    clearKnowledge,
    searchKnowledge
  }
}
