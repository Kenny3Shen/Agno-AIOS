import type { JsonRecord, ResourceVisibility } from '@/shared/types/common'

export interface Document { id: string; title: string; source: string; chunks: number; created_at: string; status?: string; visibility?: ResourceVisibility; owner_user_id?: string; can_manage?: boolean; metadata?: Record<string, string> }
export interface KnowledgeResponse { status: JsonRecord; documents: Document[]; pagination: { page: number; limit: number; total: number } }
export interface SearchResult { content: string; score: number; doc_id: string; title: string; source: string; chunk_index: number; metadata?: JsonRecord }

export interface KnowledgeIngestOptions {
  chunk_size?: number
  chunk_overlap?: number
  code_chunk_size?: number
  semantic_threshold?: number
  reader_strategy?: string
}

export interface AddTextPayload {
  title: string
  content: string
  source?: string
  visibility: ResourceVisibility
  metadata?: Record<string, string>
  ingest_options?: KnowledgeIngestOptions
}

export interface AddPathPayload {
  path: string
  title?: string
  source?: string
  visibility: ResourceVisibility
  ingest_options?: KnowledgeIngestOptions
}

export interface UploadDocumentPayload {
  file: File
  title?: string
  source?: string
  visibility: ResourceVisibility
  ingest_options?: KnowledgeIngestOptions
}

export interface UpdateDocumentPayload {
  title?: string
  source?: string
  visibility?: ResourceVisibility
  metadata?: Record<string, string>
}

export interface ReplaceSourcePayload {
  content: string
  file_name: string
  ingest_options?: KnowledgeIngestOptions
}

export interface ReplaceSourceFilePayload {
  file: File
  title?: string
  source?: string
  visibility?: ResourceVisibility
  ingest_options?: KnowledgeIngestOptions
}
