import type { JsonRecord, ResourceVisibility } from '@/shared/types/common'

export interface Document {
  id: string
  title: string
  source: string
  chunks: number
  created_at: string
  status?: string
  visibility?: ResourceVisibility
  owner_user_id?: string
  can_manage?: boolean
  metadata?: Record<string, string>
}
export type KnowledgeSearchType = 'hybrid' | 'vector' | 'keyword'
export type RetrievalRenderMode = 'auto' | 'markdown' | 'json' | 'text'
export interface KnowledgeRagSettings {
  search_type?: KnowledgeSearchType
  chunk_size?: number
  chunk_overlap?: number
  code_chunk_size?: number
  semantic_threshold?: number
}
export interface KnowledgeStatus extends JsonRecord {
  rag_settings?: KnowledgeRagSettings
}
export interface KnowledgeResponse {
  status: KnowledgeStatus
  documents: Document[]
  pagination: { page: number; limit: number; total: number }
}
export interface SearchResult {
  content: string
  score: number
  doc_id: string
  title: string
  source: string
  chunk_index: number
  metadata?: JsonRecord
}

export interface KnowledgeIngestOptions {
  chunk_size?: number
  chunk_overlap?: number
  markdown_split_on_headings?: number
  csv_skip_header?: boolean
  csv_clean_rows?: boolean
  code_chunk_size?: number
  code_tokenizer?: string
  code_include_nodes?: boolean
  semantic_threshold?: number
  semantic_similarity_window?: number
  semantic_min_sentences_per_chunk?: number
  semantic_min_characters_per_sentence?: number
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

export interface UpdateDocumentMetadataPayload {
  title?: string
  source?: string
  visibility?: ResourceVisibility
  metadata?: Record<string, string>
}

export type UpdateDocumentMode = 'metadata' | 'rebuild' | 'replace_text'

export interface UpdateDocumentActionPayload {
  mode: UpdateDocumentMode
  metadata?: UpdateDocumentMetadataPayload
  ingest_options?: KnowledgeIngestOptions
  content?: string
  file_name?: string
}

export interface UpdateDocumentUploadPayload {
  file: File
  title?: string
  source?: string
  visibility?: ResourceVisibility
  ingest_options?: KnowledgeIngestOptions
}
