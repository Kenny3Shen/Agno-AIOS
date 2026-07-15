import { describe, expect, it } from 'vitest'
import { celHintsFor, filterCelHints } from './celHints'

describe('celHints', () => {
  it('filters by mode', () => {
    const loop = celHintsFor('loop')
    expect(loop.some((h) => h.value.includes('last_step_content'))).toBe(true)
    expect(loop.every((h) => h.kind === 'any' || h.kind === 'loop')).toBe(true)
  })

  it('filters by query', () => {
    const all = celHintsFor('condition')
    const hit = filterCelHints(all, 'critical')
    expect(hit.length).toBeGreaterThan(0)
    expect(hit.every((h) => h.value.includes('critical') || h.label.includes('critical'))).toBe(true)
  })
})
