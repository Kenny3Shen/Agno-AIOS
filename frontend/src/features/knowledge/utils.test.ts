import { describe, expect, it } from 'vitest'
import {
  buildKnowledgeSearchPayload,
  buildMetadataUpdate,
  cleanIngestOptions,
  decideKnowledgeUpdate,
  effectiveKnowledgeIngestDefaults,
  inferKnowledgeReaderProfile,
  ingestOptionsFromMetadata,
  knowledgeIngestOptionsEqual,
  MAX_KNOWLEDGE_FILE_BYTES,
  replacementFileName,
  resolveRetrievalContent,
  validateKnowledgeFile,
} from './utils'
import type { Document } from './types'

const document: Document = {
  id: 'doc-1',
  title: 'Runbook',
  source: 'Papers',
  chunks: 3,
  created_at: '2026-01-01T00:00:00Z',
  visibility: 'private',
  metadata: { file_name: 'runbook.pdf' },
}

describe('knowledge document updates', () => {
  it('accepts supported binary documents while rejecting invalid uploads', () => {
    expect(validateKnowledgeFile({ name: 'guide.pdf', size: 1024 })).toBeNull()
    expect(validateKnowledgeFile({ name: 'payload.exe', size: 1024 })).toBe('unsupported')
    expect(validateKnowledgeFile({ name: 'empty.md', size: 0 })).toBe('empty')
    expect(validateKnowledgeFile({ name: 'large.md', size: MAX_KNOWLEDGE_FILE_BYTES + 1 })).toBe('too-large')
  })

  it('uses an editable text reader filename when replacing a structured document', () => {
    expect(replacementFileName(document)).toBe('runbook.md')
    expect(replacementFileName({ ...document, metadata: { file_name: 'runbook.json' } })).toBe('runbook.json')
  })

  it('sends only changed metadata fields', () => {
    expect(buildMetadataUpdate(document, { title: 'Runbook', source: 'Runbooks', visibility: 'public' })).toEqual({
      source: 'Runbooks',
      visibility: 'public',
    })
    expect(buildMetadataUpdate(document, { title: 'Runbook', source: 'Papers', visibility: 'private' })).toEqual({})
  })

  it('keeps only configured ingest options', () => {
    expect(
      cleanIngestOptions({
        chunk_size: 1500,
        chunk_overlap: 120,
        markdown_split_on_headings: 0,
        csv_skip_header: false,
        csv_clean_rows: true,
        code_chunk_size: 2200,
        code_tokenizer: ' gpt2 ',
        code_include_nodes: false,
        semantic_threshold: 0.61,
        semantic_similarity_window: 4,
        semantic_min_sentences_per_chunk: 2,
        semantic_min_characters_per_sentence: 12,
        reader_strategy: ' markdown ',
      })
    ).toEqual({
      chunk_size: 1500,
      chunk_overlap: 120,
      markdown_split_on_headings: 0,
      csv_skip_header: false,
      csv_clean_rows: true,
      code_chunk_size: 2200,
      code_tokenizer: 'gpt2',
      code_include_nodes: false,
      semantic_threshold: 0.61,
      semantic_similarity_window: 4,
      semantic_min_sentences_per_chunk: 2,
      semantic_min_characters_per_sentence: 12,
      reader_strategy: 'markdown',
    })
    expect(cleanIngestOptions({ reader_strategy: '   ' })).toBeUndefined()
  })

  it('infers reader profiles from supported suffixes and explicit overrides', () => {
    expect(inferKnowledgeReaderProfile('runbook.md').strategy).toBe('markdown')
    expect(inferKnowledgeReaderProfile('assets.csv').strategy).toBe('csv_row')
    expect(inferKnowledgeReaderProfile('agent.ts').strategy).toBe('code')
    expect(inferKnowledgeReaderProfile('notes.txt').strategy).toBe('semantic')
    expect(inferKnowledgeReaderProfile('report.pdf').strategy).toBe('document')
    expect(inferKnowledgeReaderProfile('alerts.json', 'semantic').strategy).toBe('semantic')
  })

  it('restores stored ingest options from document metadata', () => {
    expect(
      ingestOptionsFromMetadata({
        chunk_size: '1800',
        markdown_split_on_headings: '2',
        csv_clean_rows: 'false',
        code_tokenizer: 'gpt2',
        code_include_nodes: 'true',
        reader_strategy: 'markdown',
      })
    ).toEqual({
      chunk_size: 1800,
      markdown_split_on_headings: 2,
      csv_clean_rows: false,
      code_tokenizer: 'gpt2',
      code_include_nodes: true,
      reader_strategy: 'markdown',
    })
  })

  it('chooses the update transport from changed content', () => {
    expect(decideKnowledgeUpdate({ metadata: {}, hasFile: true })).toEqual({
      kind: 'upload',
      metadata: undefined,
      ingest_options: undefined,
    })
    expect(
      decideKnowledgeUpdate({ metadata: { title: 'Updated' }, ingest_options: { chunk_size: 1500 }, ingestOptionsChanged: true })
    ).toEqual({
      kind: 'rebuild',
      metadata: { title: 'Updated' },
      ingest_options: { chunk_size: 1500 },
    })
    expect(decideKnowledgeUpdate({ metadata: {}, ingest_options: { chunk_size: 1500 }, ingestOptionsChanged: true })).toEqual({
      kind: 'rebuild',
      metadata: undefined,
      ingest_options: { chunk_size: 1500 },
    })
    expect(
      decideKnowledgeUpdate({ metadata: { source: 'Updated' }, ingest_options: { chunk_size: 1500 }, ingestOptionsChanged: false })
    ).toEqual({
      kind: 'metadata',
      metadata: { source: 'Updated' },
    })
    expect(decideKnowledgeUpdate({ metadata: { visibility: 'public' } })).toEqual({
      kind: 'metadata',
      metadata: { visibility: 'public' },
    })
    expect(decideKnowledgeUpdate({ metadata: {} })).toEqual({ kind: 'noop' })
  })

  it('compares cleaned ingest options without treating stored defaults as changes', () => {
    expect(
      knowledgeIngestOptionsEqual({ chunk_size: 1500, reader_strategy: ' markdown ' }, { chunk_size: 1500, reader_strategy: 'markdown' })
    ).toBe(true)
    expect(knowledgeIngestOptionsEqual({ chunk_size: 1500 }, { chunk_size: 1600 })).toBe(false)
    expect(knowledgeIngestOptionsEqual(undefined, {})).toBe(true)
  })

  it('merges runtime ingest defaults with Agno fallback defaults', () => {
    expect(effectiveKnowledgeIngestDefaults({ chunk_size: 1600, search_type: 'vector' })).toMatchObject({
      chunk_size: 1600,
      chunk_overlap: 160,
      code_chunk_size: 1800,
      semantic_threshold: 0.52,
      semantic_similarity_window: 3,
      search_type: 'vector',
    })
  })

  it('cleans retrieval search payloads without accepting invalid methods', () => {
    expect(buildKnowledgeSearchPayload(' policy ', 5, 'keyword')).toEqual({ query: 'policy', limit: 5, search_type: 'keyword' })
    expect(buildKnowledgeSearchPayload('policy', 5, 'unknown')).toEqual({ query: 'policy', limit: 5 })
  })

  it('resolves retrieval result render mode from content and overrides', () => {
    expect(resolveRetrievalContent({ content: '{"risk":"high"}' }, 'auto')).toEqual({ kind: 'json', value: { risk: 'high' } })
    expect(resolveRetrievalContent({ content: '# Heading' }, 'auto')).toEqual({ kind: 'markdown', value: '# Heading' })
    expect(resolveRetrievalContent({ content: 'plain answer' }, 'auto')).toEqual({ kind: 'text', value: 'plain answer' })
    expect(resolveRetrievalContent({ content: '{"risk":"high"}' }, 'text')).toEqual({ kind: 'text', value: '{"risk":"high"}' })
  })
})
