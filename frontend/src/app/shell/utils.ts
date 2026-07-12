export const NAVIGATION_GROUP_KEYS = [
  ['/dashboard', '/chat', '/workflow'],
  ['/skills', '/mcp', '/knowledge'],
  ['/trace', '/memory', '/evaluations', '/approvals'],
  ['/cve', '/collect'],
  ['/audit', '/settings'],
] as const

export function groupNavigation<T extends { key: string }>(items: T[]) {
  const byKey = new Map(items.map((item) => [item.key, item]))
  return NAVIGATION_GROUP_KEYS.map((keys) =>
    keys.flatMap((key) => {
      const item = byKey.get(key)
      return item ? [item] : []
    }),
  )
}

export function joinMenuGroups<T>(groups: T[][]) {
  const visible = groups.filter((group) => group.length > 0)
  return visible.flatMap((group, index) => index === 0 ? group : [{ type: 'divider' as const, key: `divider-${index}` }, ...group])
}
