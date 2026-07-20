import { describe, expect, it } from 'vitest'
import {
  defaultOpenNavigationGroupKeys,
  filterNavigationGroups,
  navigationGroupKeyForItemPath,
  navigationGroupMenuKey,
  withOpenNavigationGroup,
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

  it('keeps an item when any of its alternative scopes is granted', () => {
    const alternatives: NavigationGroup<{
      key: string
      scopes?: string[]
    }>[] = [
      {
        key: 'capabilities',
        labelKey: 'capabilities',
        items: [
          { key: '/skills', scopes: ['skill:read', 'skill:write'] },
        ],
      },
    ]

    expect(
      filterNavigationGroups(
        alternatives,
        (scope) => scope === 'skill:write',
      ),
    ).toEqual(alternatives)
  })

  it('defaults to opening the first two navigation groups', () => {
    expect(defaultOpenNavigationGroupKeys(groups)).toEqual([navigationGroupMenuKey('workspace'), navigationGroupMenuKey('governance')])
    expect(defaultOpenNavigationGroupKeys([])).toEqual([])
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
