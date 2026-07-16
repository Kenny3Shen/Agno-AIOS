import type { UploadFile } from 'antd'
import type { ResourceVisibility } from '@/shared/types/common'
import type {
  Document,
  KnowledgeIngestOptions,
  KnowledgeRagSettings,
  KnowledgeSearchType,
  RetrievalRenderMode,
  SearchResult,
  UpdateDocumentMetadataPayload,
} from './types'

export const KNOWLEDGE_FILE_ACCEPT =
  '.md,.markdown,.mdown,.mkd,.csv,.tsv,.json,.jsonl,.py,.js,.mjs,.cjs,.jsx,.ts,.tsx,.vue,.go,.rs,.java,.c,.cc,.cpp,.h,.hpp,.cs,.php,.rb,.sh,.sql,.pdf,.docx,.txt,.log,.rst,.yaml,.yml,.toml'
export const MAX_KNOWLEDGE_FILE_BYTES = 50 * 1024 * 1024
export const SEARCH_TYPE_OPTIONS: KnowledgeSearchType[] = ['hybrid', 'vector', 'keyword']

export interface KnowledgeIngestDefaults {
  chunk_size: number
  chunk_overlap: number
  markdown_split_on_headings: string
  csv_skip_header: boolean
  csv_clean_rows: boolean
  code_chunk_size: number
  code_tokenizer: string
  code_include_nodes: boolean
  semantic_threshold: number
  semantic_similarity_window: number
  semantic_min_sentences_per_chunk: number
  semantic_min_characters_per_sentence: number
  search_type: KnowledgeSearchType
}

export const AGNO_INGEST_DEFAULTS: KnowledgeIngestDefaults = {
  chunk_size: 5000,
  chunk_overlap: 0,
  markdown_split_on_headings: '',
  csv_skip_header: false,
  csv_clean_rows: true,
  code_chunk_size: 2048,
  code_tokenizer: 'character',
  code_include_nodes: false,
  semantic_threshold: 0.5,
  semantic_similarity_window: 3,
  semantic_min_sentences_per_chunk: 1,
  semantic_min_characters_per_sentence: 24,
  search_type: 'hybrid',
}

const supportedSuffixes = new Set(KNOWLEDGE_FILE_ACCEPT.split(','))
const structuredSuffixes = new Set(['.pdf', '.docx'])
const markdownSuffixes = new Set(['.md', '.markdown', '.mdown', '.mkd'])
const csvSuffixes = new Set(['.csv', '.tsv'])
const jsonSuffixes = new Set(['.json', '.jsonl'])
const codeSuffixes = new Set([
  '.py',
  '.js',
  '.mjs',
  '.cjs',
  '.jsx',
  '.ts',
  '.tsx',
  '.vue',
  '.go',
  '.rs',
  '.java',
  '.c',
  '.cc',
  '.cpp',
  '.h',
  '.hpp',
  '.cs',
  '.php',
  '.rb',
  '.sh',
  '.sql',
])

export type KnowledgeReaderStrategy = 'markdown' | 'semantic' | 'code' | 'csv_row' | 'json' | 'document'

export interface KnowledgeReaderProfile {
  strategy: KnowledgeReaderStrategy
  labelKey: string
  descriptionKey: string
}

export const knowledgeReaderProfiles: Record<KnowledgeReaderStrategy, KnowledgeReaderProfile> = {
  markdown: { strategy: 'markdown', labelKey: 'strategyMarkdown', descriptionKey: 'profiles.markdown' },
  semantic: { strategy: 'semantic', labelKey: 'strategySemantic', descriptionKey: 'profiles.semantic' },
  code: { strategy: 'code', labelKey: 'strategyCode', descriptionKey: 'profiles.code' },
  csv_row: { strategy: 'csv_row', labelKey: 'strategyCsv', descriptionKey: 'profiles.csv_row' },
  json: { strategy: 'json', labelKey: 'strategyJson', descriptionKey: 'profiles.json' },
  document: { strategy: 'document', labelKey: 'strategyDocument', descriptionKey: 'profiles.document' },
}

export function effectiveKnowledgeIngestDefaults(ragSettings?: KnowledgeRagSettings): KnowledgeIngestDefaults {
  return {
    ...AGNO_INGEST_DEFAULTS,
    chunk_size: ragSettings?.chunk_size ?? 1200,
    chunk_overlap: ragSettings?.chunk_overlap ?? 160,
    code_chunk_size: ragSettings?.code_chunk_size ?? 1800,
    semantic_threshold: ragSettings?.semantic_threshold ?? 0.52,
    search_type: ragSettings?.search_type ?? 'hybrid',
  }
}

export function buildKnowledgeSearchPayload(query: string, limit: number, searchType?: string) {
  const payload: { query: string; limit: number; search_type?: KnowledgeSearchType } = {
    query: query.trim(),
    limit,
  }
  const normalized = searchType?.trim() as KnowledgeSearchType | undefined
  if (normalized && SEARCH_TYPE_OPTIONS.includes(normalized)) payload.search_type = normalized
  return payload
}

const parseJsonObjectOrArray = (value: string): unknown | undefined => {
  const text = value.trim()
  if (!(text.startsWith('{') || text.startsWith('['))) return undefined
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed : undefined
  } catch {
    return undefined
  }
}

const metadataSuggestsMarkdown = (metadata?: SearchResult['metadata']) => {
  if (!metadata) return false
  const values = ['format', 'content_type', 'mime_type', 'file_name', 'source'].map((key) => metadata[key])
  return values.some((value) => typeof value === 'string' && /markdown|text\/md|\.md(?:$|\?)/i.test(value))
}

const looksLikeMarkdown = (value: string) => /(^|\n)#{1,6}\s|```|\*\*[^*]+\*\*|(^|\n)\s*[-*]\s+|(^|\n)>\s+/m.test(value)

export function resolveRetrievalContent(
  result: Pick<SearchResult, 'content' | 'metadata'>,
  mode: RetrievalRenderMode
): { kind: Exclude<RetrievalRenderMode, 'auto'>; value: unknown } {
  if (mode === 'json') return { kind: 'json', value: parseJsonObjectOrArray(result.content) ?? result.content }
  if (mode === 'markdown') return { kind: 'markdown', value: result.content }
  if (mode === 'text') return { kind: 'text', value: result.content }
  const parsed = parseJsonObjectOrArray(result.content)
  if (parsed !== undefined) return { kind: 'json', value: parsed }
  if (metadataSuggestsMarkdown(result.metadata) || looksLikeMarkdown(result.content)) return { kind: 'markdown', value: result.content }
  return { kind: 'text', value: result.content }
}

export function fileSuffix(name: string) {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index).toLowerCase() : ''
}

export function inferKnowledgeReaderProfile(filename?: string, readerStrategy?: string): KnowledgeReaderProfile {
  const strategy = readerStrategy?.trim() as KnowledgeReaderStrategy | undefined
  if (strategy && strategy in knowledgeReaderProfiles) return knowledgeReaderProfiles[strategy]
  const suffix = fileSuffix(filename ?? '')
  if (markdownSuffixes.has(suffix)) return knowledgeReaderProfiles.markdown
  if (csvSuffixes.has(suffix)) return knowledgeReaderProfiles.csv_row
  if (jsonSuffixes.has(suffix)) return knowledgeReaderProfiles.json
  if (codeSuffixes.has(suffix)) return knowledgeReaderProfiles.code
  if (structuredSuffixes.has(suffix)) return knowledgeReaderProfiles.document
  return knowledgeReaderProfiles.semantic
}

export function validateKnowledgeFile(file: Pick<File, 'name' | 'size'>): string | null {
  if (!supportedSuffixes.has(fileSuffix(file.name))) return 'unsupported'
  if (file.size <= 0) return 'empty'
  if (file.size > MAX_KNOWLEDGE_FILE_BYTES) return 'too-large'
  return null
}

export const normalizeUploadFiles = (event: { fileList?: UploadFile[] } | UploadFile[]) => (Array.isArray(event) ? event : event?.fileList)

export const selectedUploadFile = (fileList?: UploadFile[]) => {
  const item = fileList?.[0]
  return (item?.originFileObj ?? item) as File | undefined
}

export type KnowledgeFileIssue = 'unsupported' | 'too-large' | 'empty'

export function knowledgeFileErrorKey(issue: string): 'errors.tooLarge' | 'errors.empty' | 'errors.unsupported' {
  if (issue === 'too-large') return 'errors.tooLarge'
  if (issue === 'empty') return 'errors.empty'
  return 'errors.unsupported'
}

export function replacementFileName(document: Document) {
  const original = document.metadata?.file_name?.trim() || `${document.title.trim() || 'document'}.md`
  if (!structuredSuffixes.has(fileSuffix(original))) return original
  const base = original.slice(0, -fileSuffix(original).length).trim() || 'document'
  return `${base}.md`
}

export function buildMetadataUpdate(
  document: Document,
  values: { title: string; source: string; visibility: ResourceVisibility }
): UpdateDocumentMetadataPayload {
  const title = values.title.trim()
  const source = values.source.trim()
  const payload: UpdateDocumentMetadataPayload = {}
  if (title !== document.title) payload.title = title
  if (source !== document.source) payload.source = source
  if (values.visibility !== (document.visibility ?? 'private')) payload.visibility = values.visibility
  return payload
}

export const hasMetadataUpdate = (payload: UpdateDocumentMetadataPayload) => Object.keys(payload).length > 0

export type KnowledgeUpdateDecision =
  | { kind: 'noop' }
  | { kind: 'metadata'; metadata: UpdateDocumentMetadataPayload }
  | { kind: 'rebuild'; metadata?: UpdateDocumentMetadataPayload; ingest_options?: KnowledgeIngestOptions }
  | { kind: 'upload'; metadata?: UpdateDocumentMetadataPayload; ingest_options?: KnowledgeIngestOptions }

export function knowledgeIngestOptionsEqual(left?: KnowledgeIngestOptions, right?: KnowledgeIngestOptions) {
  const leftOptions = cleanIngestOptions(left)
  const rightOptions = cleanIngestOptions(right)
  if (!leftOptions || !rightOptions) return leftOptions === rightOptions
  const leftKeys = Object.keys(leftOptions) as Array<keyof KnowledgeIngestOptions>
  const rightKeys = Object.keys(rightOptions) as Array<keyof KnowledgeIngestOptions>
  if (leftKeys.length !== rightKeys.length) return false
  return leftKeys.every((key) => leftOptions[key] === rightOptions[key])
}

export function decideKnowledgeUpdate({
  metadata,
  ingest_options,
  ingestOptionsChanged,
  hasFile,
}: {
  metadata: UpdateDocumentMetadataPayload
  ingest_options?: KnowledgeIngestOptions
  ingestOptionsChanged?: boolean
  hasFile?: boolean
}): KnowledgeUpdateDecision {
  const metadataPayload = hasMetadataUpdate(metadata) ? metadata : undefined
  if (hasFile) return { kind: 'upload', metadata: metadataPayload, ingest_options }
  if (ingestOptionsChanged) return { kind: 'rebuild', metadata: metadataPayload, ingest_options }
  if (metadataPayload) return { kind: 'metadata', metadata: metadataPayload }
  return { kind: 'noop' }
}

const numberOptionKeys = [
  'chunk_size',
  'chunk_overlap',
  'markdown_split_on_headings',
  'code_chunk_size',
  'semantic_threshold',
  'semantic_similarity_window',
  'semantic_min_sentences_per_chunk',
  'semantic_min_characters_per_sentence',
] as const

const boolOptionKeys = ['csv_skip_header', 'csv_clean_rows', 'code_include_nodes'] as const

function metadataNumber(value?: string) {
  if (value === undefined || value.trim() === '') return undefined
  const number = Number(value)
  return Number.isFinite(number) ? number : undefined
}

function metadataBool(value?: string) {
  if (value === undefined || value.trim() === '') return undefined
  const normalized = value.trim().toLowerCase()
  if (['true', '1', 'yes', 'on'].includes(normalized)) return true
  if (['false', '0', 'no', 'off'].includes(normalized)) return false
  return undefined
}

export function ingestOptionsFromMetadata(metadata?: Record<string, string>): KnowledgeIngestOptions | undefined {
  if (!metadata) return undefined
  const options: KnowledgeIngestOptions = {}
  numberOptionKeys.forEach((key) => {
    const value = metadataNumber(metadata[key])
    if (value !== undefined) options[key] = value
  })
  boolOptionKeys.forEach((key) => {
    const value = metadataBool(metadata[key])
    if (value !== undefined) options[key] = value
  })
  if (metadata.code_tokenizer?.trim()) options.code_tokenizer = metadata.code_tokenizer.trim()
  if (metadata.reader_strategy?.trim()) options.reader_strategy = metadata.reader_strategy.trim()
  return Object.keys(options).length > 0 ? options : undefined
}

export function cleanIngestOptions(values?: Partial<KnowledgeIngestOptions>): KnowledgeIngestOptions | undefined {
  if (!values) return undefined
  const options: KnowledgeIngestOptions = {}
  if (values.chunk_size != null) options.chunk_size = values.chunk_size
  if (values.chunk_overlap != null) options.chunk_overlap = values.chunk_overlap
  if (values.markdown_split_on_headings != null) options.markdown_split_on_headings = values.markdown_split_on_headings
  if (values.csv_skip_header != null) options.csv_skip_header = values.csv_skip_header
  if (values.csv_clean_rows != null) options.csv_clean_rows = values.csv_clean_rows
  if (values.code_chunk_size != null) options.code_chunk_size = values.code_chunk_size
  const codeTokenizer = values.code_tokenizer?.trim()
  if (codeTokenizer) options.code_tokenizer = codeTokenizer
  if (values.code_include_nodes != null) options.code_include_nodes = values.code_include_nodes
  if (values.semantic_threshold != null) options.semantic_threshold = values.semantic_threshold
  if (values.semantic_similarity_window != null) options.semantic_similarity_window = values.semantic_similarity_window
  if (values.semantic_min_sentences_per_chunk != null) options.semantic_min_sentences_per_chunk = values.semantic_min_sentences_per_chunk
  if (values.semantic_min_characters_per_sentence != null)
    options.semantic_min_characters_per_sentence = values.semantic_min_characters_per_sentence
  const readerStrategy = values.reader_strategy?.trim()
  if (readerStrategy) options.reader_strategy = readerStrategy
  return Object.keys(options).length > 0 ? options : undefined
}
