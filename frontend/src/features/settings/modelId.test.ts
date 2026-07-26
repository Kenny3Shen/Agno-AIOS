import { describe, expect, it } from 'vitest'
import { createModelId } from './modelId'

describe('createModelId', () => {
  it('uses a UUID when one is available', () => {
    expect(createModelId(() => 'test-uuid')).toBe('test-uuid')
  })

  it('falls back when randomUUID is unavailable or fails', () => {
    expect(createModelId(null)).toMatch(/^model-/)
    expect(
      createModelId(() => {
        throw new Error('randomUUID unavailable')
      })
    ).toMatch(/^model-/)
  })
})
