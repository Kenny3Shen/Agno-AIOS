import type { UploadFile } from 'antd'
import type { ResourceVisibility } from '@/shared/types/common'
import type { Document, KnowledgeIngestOptions, UpdateDocumentPayload } from './types'

export const KNOWLEDGE_FILE_ACCEPT = '.md,.markdown,.mdown,.mkd,.csv,.tsv,.json,.jsonl,.py,.js,.mjs,.cjs,.jsx,.ts,.tsx,.vue,.go,.rs,.java,.c,.cc,.cpp,.h,.hpp,.cs,.php,.rb,.sh,.sql,.pdf,.docx,.txt,.log,.rst,.yaml,.yml,.toml'
export const MAX_KNOWLEDGE_FILE_BYTES = 50 * 1024 * 1024

const supportedSuffixes = new Set(KNOWLEDGE_FILE_ACCEPT.split(','))
const structuredSuffixes = new Set(['.pdf', '.docx'])

export function fileSuffix(name: string) {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index).toLowerCase() : ''
}

export function validateKnowledgeFile(file: Pick<File, 'name' | 'size'>): string | null {
  if (!supportedSuffixes.has(fileSuffix(file.name))) return 'unsupported'
  if (file.size <= 0) return 'empty'
  if (file.size > MAX_KNOWLEDGE_FILE_BYTES) return 'too-large'
  return null
}

export const normalizeUploadFiles = (event: { fileList?: UploadFile[] } | UploadFile[]) => Array.isArray(event) ? event : event?.fileList

export const selectedUploadFile = (fileList?: UploadFile[]) => {
  const item = fileList?.[0]
  return (item?.originFileObj ?? item) as File | undefined
}

export function knowledgeFileErrorMessage(issue: string) {
  if (issue === 'too-large') return '文件不能超过 50 MB'
  if (issue === 'empty') return '不能上传空文件'
  return '暂不支持该文件类型'
}

export function replacementFileName(document: Document) {
  const original = document.metadata?.file_name?.trim() || `${document.title.trim() || 'document'}.md`
  if (!structuredSuffixes.has(fileSuffix(original))) return original
  const base = original.slice(0, -fileSuffix(original).length).trim() || 'document'
  return `${base}.md`
}

export function buildMetadataUpdate(
  document: Document,
  values: { title: string; source: string; visibility: ResourceVisibility },
): UpdateDocumentPayload {
  const title = values.title.trim()
  const source = values.source.trim()
  const payload: UpdateDocumentPayload = {}
  if (title !== document.title) payload.title = title
  if (source !== document.source) payload.source = source
  if (values.visibility !== (document.visibility ?? 'private')) payload.visibility = values.visibility
  return payload
}

export const hasMetadataUpdate = (payload: UpdateDocumentPayload) => Object.keys(payload).length > 0

export function cleanIngestOptions(values?: Partial<KnowledgeIngestOptions>): KnowledgeIngestOptions | undefined {
  if (!values) return undefined
  const options: KnowledgeIngestOptions = {}
  if (values.chunk_size != null) options.chunk_size = values.chunk_size
  if (values.chunk_overlap != null) options.chunk_overlap = values.chunk_overlap
  if (values.code_chunk_size != null) options.code_chunk_size = values.code_chunk_size
  if (values.semantic_threshold != null) options.semantic_threshold = values.semantic_threshold
  const readerStrategy = values.reader_strategy?.trim()
  if (readerStrategy) options.reader_strategy = readerStrategy
  return Object.keys(options).length > 0 ? options : undefined
}
