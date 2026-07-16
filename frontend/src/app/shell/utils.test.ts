import { describe, expect, it, vi } from 'vitest'
import {
  RECENT_CONVERSATIONS_STORAGE_KEY,
  defaultOpenNavigationGroupKeys,
  filterNavigationGroups,
  navigationGroupKeyForItemPath,
  navigationGroupMenuKey,
  readRecentConversationsExpanded,
  withOpenNavigationGroup,
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
        { key: '/workflow', scope: 'workflows:read' },
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

describe('deep-link navigation group expansion', () => {
  const fullGroups: NavigationGroup<{ key: string; scope?: string }>[] = [
    {
      key: 'workspace',
      labelKey: 'workspace',
      items: [
        { key: '/chat', scope: 'sessions:write' },
        { key: '/workflow', scope: 'workflows:read' },
      ],
    },
    {
      key: 'capabilities',
      labelKey: 'capabilities',
      items: [{ key: '/knowledge', scope: 'knowledge:read' }],
    },
    {
      key: 'governance',
      labelKey: 'governance',
      items: [
        { key: '/trace', scope: 'traces:read' },
        { key: '/approvals', scope: 'approvals:read' },
      ],
    },
    {
      key: 'intelligence',
      labelKey: 'intelligence',
      items: [{ key: '/cve', scope: 'cve:read' }],
    },
  ]

  it('resolves the group menu key for a deep-linked path', () => {
    expect(navigationGroupKeyForItemPath(fullGroups, '/trace')).toBe(navigationGroupMenuKey('governance'))
    expect(navigationGroupKeyForItemPath(fullGroups, '/cve')).toBe(navigationGroupMenuKey('intelligence'))
    expect(navigationGroupKeyForItemPath(fullGroups, '/chat')).toBe(navigationGroupMenuKey('workspace'))
    expect(navigationGroupKeyForItemPath(fullGroups, '/settings')).toBeNull()
    expect(navigationGroupKeyForItemPath(fullGroups, '/dashboard')).toBeNull()
  })

  it('adds the target group to open keys without reordering existing ones', () => {
    const open = [navigationGroupMenuKey('workspace'), navigationGroupMenuKey('capabilities')]
    const governance = navigationGroupMenuKey('governance')
    expect(withOpenNavigationGroup(open, governance)).toEqual([...open, governance])
    expect(withOpenNavigationGroup(open, navigationGroupMenuKey('workspace'))).toEqual(open)
    expect(withOpenNavigationGroup(open, null)).toEqual(open)
  })
})

