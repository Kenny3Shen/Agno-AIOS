import { describe, expect, it } from 'vitest'
import { normalizeMemory } from './api'

describe('normalizeMemory', () => {
  it('maps native memory_id rows', () => {
    expect(
      normalizeMemory({
        memory_id: 'mem-1',
        memory: 'Prefers short summaries',
        topics: ['preference'],
        user_id: 'u1',
        updated_at: '2026-07-05T00:00:00+00:00',
      }),
    ).toMatchObject({
      id: 'mem-1',
      memory_id: 'mem-1',
      memory: 'Prefers short summaries',
      topics: ['preference'],
      user_id: 'u1',
    })
  })

  it('ignores legacy id-only rows', () => {
    expect(
      normalizeMemory({
        id: 'legacy-1',
        memory: 'Legacy memory',
      }),
    ).toBeNull()
  })

  it('returns null when memory_id is missing', () => {
    expect(normalizeMemory({ memory: 'no id' })).toBeNull()
  })
})
