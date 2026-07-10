import { describe, expect, it } from 'vitest'
import { flattenMetadata } from './MetadataDescriptions'

describe('metadata descriptions', () => {
  it('does not create a placeholder row when no metadata is provided', () => {
    expect(flattenMetadata(undefined)).toEqual([])
  })

  it('flattens nested metadata into readable description paths', () => {
    expect(flattenMetadata({ visibility: 'public', owner: { user_id: 'u1' }, tags: ['paper', 'markdown'] }, 'Metadata')).toEqual([
      { key: 'Metadata / visibility', label: 'Metadata / Visibility', value: 'public' },
      { key: 'Metadata / owner', label: 'Metadata / Owner', value: { user_id: 'u1' } },
      { key: 'Metadata / tags', label: 'Metadata / Tags', value: ['paper', 'markdown'] },
    ])
  })
})
