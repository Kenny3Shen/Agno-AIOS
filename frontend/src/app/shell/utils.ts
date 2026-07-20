export interface NavigationGroup<T> {
  key: string
  labelKey: string
  items: T[]
}

export const navigationGroupMenuKey = (groupKey: string) => `navigation-group-${groupKey}`

export function defaultOpenNavigationGroupKeys<T>(groups: NavigationGroup<T>[]) {
  return groups.slice(0, 2).map((group) => navigationGroupMenuKey(group.key))
}

export function filterNavigationGroups<T extends { scope?: string; scopes?: readonly string[] }>(
  groups: NavigationGroup<T>[],
  canAccess: (scope: string) => boolean,
) {
  return groups.flatMap((group) => {
    const items = group.items.filter(
      (item) =>
        (!item.scope && !item.scopes?.length) ||
        (item.scope ? canAccess(item.scope) : item.scopes?.some(canAccess)),
    )
    return items.length ? [{ ...group, items }] : []
  })
}

/** Menu openKey for the group that owns ``path``, or null when path is outside grouped nav. */
export function navigationGroupKeyForItemPath<T extends { key: string }>(
  groups: NavigationGroup<T>[],
  path: string,
): string | null {
  for (const group of groups) {
    if (group.items.some((item) => item.key === path)) {
      return navigationGroupMenuKey(group.key)
    }
  }
  return null
}

/** Ensure ``groupMenuKey`` is present in openKeys without reordering existing keys. */
export function withOpenNavigationGroup(openKeys: readonly string[], groupMenuKey: string | null): string[] {
  if (!groupMenuKey || openKeys.includes(groupMenuKey)) return [...openKeys]
  return [...openKeys, groupMenuKey]
}
