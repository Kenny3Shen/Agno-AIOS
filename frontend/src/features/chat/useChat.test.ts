import { describe, expect, it } from 'vitest'
import { isTeamCatalogItem } from './useChat'

describe('isTeamCatalogItem', () => {
  it('requires explicit team kind/category, not id naming', () => {
    expect(isTeamCatalogItem({ id: 'research-analysis-tasks' })).toBe(false)
    expect(isTeamCatalogItem({ id: 'research-analysis-tasks', kind: 'team' })).toBe(true)
    expect(isTeamCatalogItem({ id: 'research-analysis-tasks', category: 'team' })).toBe(true)
  })
})
