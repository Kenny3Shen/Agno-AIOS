export const RECENT_CONVERSATIONS_STORAGE_KEY = 'tais-shell-recent-expanded'

export interface NavigationGroup<T> {
  key: string
  labelKey: string
  items: T[]
}

export const navigationGroupMenuKey = (groupKey: string) => `navigation-group-${groupKey}`

export function defaultOpenNavigationGroupKeys<T>(groups: NavigationGroup<T>[]) {
  return groups.slice(0, 2).map((group) => navigationGroupMenuKey(group.key))
}

export function filterNavigationGroups<T extends { scope?: string }>(groups: NavigationGroup<T>[], canAccess: (scope: string) => boolean) {
  return groups.flatMap((group) => {
    const items = group.items.filter((item) => !item.scope || canAccess(item.scope))
    return items.length ? [{ ...group, items }] : []
  })
}

export function readRecentConversationsExpanded(storage: Pick<Storage, 'getItem'> = localStorage) {
  return storage.getItem(RECENT_CONVERSATIONS_STORAGE_KEY) !== 'false'
}

export function writeRecentConversationsExpanded(expanded: boolean, storage: Pick<Storage, 'setItem'> = localStorage) {
  storage.setItem(RECENT_CONVERSATIONS_STORAGE_KEY, String(expanded))
}
