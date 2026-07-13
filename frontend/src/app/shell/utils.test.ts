import { describe, expect, it, vi } from 'vitest'
import {
  RECENT_CONVERSATIONS_STORAGE_KEY,
  defaultOpenNavigationGroupKeys,
  filterNavigationGroups,
  navigationGroupMenuKey,
  readRecentConversationsExpanded,
  writeRecentConversationsExpanded,
  type NavigationGroup,
} from './utils'

describe('shell navigation groups', () => {
  const groups: NavigationGroup<{ key: string; scope?: string }>[] = [
    {
      key: 'workspace',
      labelKey: 'workspace',
      items: [
        { key: '/chat', scope: 'sessions:write' },
        { key: '/workflow', scope: 'mcp:read' },
      ],
    },
    {
      key: 'governance',
      labelKey: 'governance',
      items: [{ key: '/audit', scope: 'audit:read' }],
    },
  ]

  it('keeps the configured group and item ordering', () => {
    expect(filterNavigationGroups(groups, () => true)).toEqual(groups)
  })

  it('filters inaccessible items and removes empty groups', () => {
    expect(filterNavigationGroups(groups, (scope) => scope === 'sessions:write')).toEqual([
      {
        key: 'workspace',
        labelKey: 'workspace',
        items: [{ key: '/chat', scope: 'sessions:write' }],
      },
    ])
  })

  it('defaults to opening the first two navigation groups', () => {
    expect(defaultOpenNavigationGroupKeys(groups)).toEqual([navigationGroupMenuKey('workspace'), navigationGroupMenuKey('governance')])
    expect(defaultOpenNavigationGroupKeys([])).toEqual([])
  })
})

describe('recent conversation preference', () => {
  it('defaults to expanded and restores an explicit collapsed preference', () => {
    expect(readRecentConversationsExpanded({ getItem: () => null })).toBe(true)
    expect(readRecentConversationsExpanded({ getItem: () => 'false' })).toBe(false)
  })

  it('persists the expanded state under the shell storage key', () => {
    const setItem = vi.fn<(key: string, value: string) => void>()
    writeRecentConversationsExpanded(true, { setItem })
    expect(setItem).toHaveBeenCalledWith(RECENT_CONVERSATIONS_STORAGE_KEY, 'true')
  })
})
