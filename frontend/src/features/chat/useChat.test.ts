import { describe, expect, it } from 'vitest'
import { isTeamCatalogItem } from './useChat'

describe('isTeamCatalogItem', () => {
  it('uses catalog metadata instead of Team-like profile ids', () => {
    expect(isTeamCatalogItem({ id: 'research-analysis-tasks' })).toBe(false)
    expect(isTeamCatalogItem({ id: 'research-analysis-route' })).toBe(false)
  })

  it('recognizes an explicit Team kind or category', () => {
    expect(isTeamCatalogItem({ id: 'research-analysis-tasks', kind: 'team' })).toBe(true)
    expect(isTeamCatalogItem({ id: 'research-analysis-tasks', category: 'team' })).toBe(true)
  })
})
