import { describe, expect, it } from 'vitest'
import { createClientId } from './clientId'

describe('createClientId', () => {
  it('uses the native UUID function when available', () => {
    expect(createClientId(() => 'native-id')).toBe('native-id')
  })

  it('falls back to a UUID-shaped value when randomUUID is unavailable or throws', () => {
    expect(createClientId(null)).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(
      createClientId(() => {
        throw new Error('randomUUID unavailable')
      }),
    ).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
})
