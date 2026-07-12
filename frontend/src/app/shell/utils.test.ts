import { describe, expect, it } from 'vitest'
import { groupNavigation, joinMenuGroups } from './utils'

describe('shell navigation groups', () => {
  const items = [
    '/dashboard',
    '/chat',
    '/workflow',
    '/skills',
    '/mcp',
    '/knowledge',
    '/trace',
    '/memory',
    '/evaluations',
    '/approvals',
    '/cve',
    '/collect',
    '/audit',
    '/settings',
  ].map((key) => ({ key }))

  it('groups navigation items by their fixed page membership', () => {
    expect(groupNavigation(items).map((group) => group.map((item) => item.key))).toEqual([
      ['/dashboard', '/chat', '/workflow'],
      ['/skills', '/mcp', '/knowledge'],
      ['/trace', '/memory', '/evaluations', '/approvals'],
      ['/cve', '/collect'],
      ['/audit', '/settings'],
    ])
  })

  it('does not shift group boundaries when a page is absent', () => {
    const visible = items.filter((item) => item.key !== '/approvals')
    expect(groupNavigation(visible).map((group) => group.map((item) => item.key))).toEqual([
      ['/dashboard', '/chat', '/workflow'],
      ['/skills', '/mcp', '/knowledge'],
      ['/trace', '/memory', '/evaluations'],
      ['/cve', '/collect'],
      ['/audit', '/settings'],
    ])
  })

  it('adds dividers only between visible groups after permission filtering', () => {
    expect(joinMenuGroups([['a'], [], ['b']])).toEqual(['a', { type: 'divider', key: 'divider-1' }, 'b'])
  })
})
