import { describe, expect, it } from 'vitest'
import { buildMetadataUpdate, cleanIngestOptions, MAX_KNOWLEDGE_FILE_BYTES, replacementFileName, validateKnowledgeFile } from './utils'
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
    expect(cleanIngestOptions({ chunk_size: 1500, reader_strategy: ' markdown ' })).toEqual({
      chunk_size: 1500,
      reader_strategy: 'markdown',
    })
    expect(cleanIngestOptions({ reader_strategy: '   ' })).toBeUndefined()
  })
})
