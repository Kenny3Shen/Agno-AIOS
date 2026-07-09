import { computed, ref, type ComputedRef } from "vue"

export interface SettingsNavigationItemConfig {
  id: string
  tag: string
}

export interface SettingsNavigationGroupConfig {
  key: string
  items: SettingsNavigationItemConfig[]
}

export interface SettingsNavigationDragState {
  groupKey: string
  itemId: string
}

export const NAVIGATION_LAYOUT_CHANGE_EVENT = "agno-aios-navigation-layout-change"

const DEFAULT_NAVIGATION_GROUPS: SettingsNavigationGroupConfig[] = [
  {
    key: "operations",
    items: ["home", "dashboard", "chat", "workflow"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "knowledge",
    items: ["skills", "mcp", "knowledge"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "governance",
    items: ["trace", "memory", "evaluation", "approvals", "scheduler"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "securityData",
    items: ["cve", "collect"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "settings",
    items: ["settings"].map((id) => ({ id, tag: "" })),
  },
]

const cloneInitialNavigationGroups = () => DEFAULT_NAVIGATION_GROUPS.map((group) => ({
  key: group.key,
  items: group.items.map((item) => ({ ...item })),
}))

export function useSettingsNavigationLayout(canWriteSettings: ComputedRef<boolean>) {
  const navigationLayout = ref<SettingsNavigationGroupConfig[]>(cloneInitialNavigationGroups())
  const draggedNavigationItem = ref<SettingsNavigationDragState | null>(null)
  const originalNavigationTags = ref("")

  const navigationItemIds = computed(() => DEFAULT_NAVIGATION_GROUPS.flatMap((group) => group.items.map((item) => item.id)))

  const cloneBaseNavigationLayout = (tagSource: Record<string, unknown> = {}) => (
    DEFAULT_NAVIGATION_GROUPS.map((group) => ({
      key: group.key,
      items: group.items.map((item) => ({
        id: item.id,
        tag: typeof tagSource[item.id] === "string" ? tagSource[item.id] as string : "",
      })),
    }))
  )

  const serializeNavigationTags = () => JSON.stringify({
    version: 1,
    groups: navigationLayout.value.map((group) => ({
      key: group.key,
      items: group.items.map((item) => ({ id: item.id, tag: item.tag })),
    })),
  })

  const dispatchNavigationLayoutChange = (raw: string) => {
    window.dispatchEvent(new CustomEvent(NAVIGATION_LAYOUT_CHANGE_EVENT, { detail: { raw } }))
  }

  const normalizedNavigationGroupsFrom = (source: Record<string, unknown>) => {
    const allowedItems = new Set(navigationItemIds.value)
    const assignedItems = new Set<string>()
    const rawGroups = Array.isArray(source.groups) ? source.groups : []

    const layout = DEFAULT_NAVIGATION_GROUPS.map((defaultGroup) => {
      const rawGroup = rawGroups.find((group) => {
        return group && typeof group === "object" && (group as Record<string, unknown>).key === defaultGroup.key
      }) as Record<string, unknown> | undefined
      const rawItems = Array.isArray(rawGroup?.items) ? rawGroup.items : []
      const items: SettingsNavigationItemConfig[] = []

      for (const rawItem of rawItems) {
        const itemRecord = rawItem && typeof rawItem === "object" ? rawItem as Record<string, unknown> : null
        const id = typeof rawItem === "string" ? rawItem : itemRecord?.id
        if (typeof id !== "string" || !allowedItems.has(id) || assignedItems.has(id)) continue
        assignedItems.add(id)
        const tag = typeof itemRecord?.tag === "string"
          ? itemRecord.tag
          : typeof source[id] === "string" ? source[id] as string : ""
        items.push({ id, tag })
      }

      return { key: defaultGroup.key, items }
    })

    for (const defaultGroup of DEFAULT_NAVIGATION_GROUPS) {
      const group = layout.find((item) => item.key === defaultGroup.key)
      if (!group) continue
      for (const item of defaultGroup.items) {
        if (assignedItems.has(item.id)) continue
        assignedItems.add(item.id)
        group.items.push({
          id: item.id,
          tag: typeof source[item.id] === "string" ? source[item.id] as string : "",
        })
      }
    }

    return layout
  }

  const loadNavigationTags = (raw: string) => {
    let parsed: unknown = {}
    try {
      parsed = raw ? JSON.parse(raw) : {}
    } catch {
      parsed = {}
    }
    const source = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {}
    navigationLayout.value = Array.isArray(source.groups)
      ? normalizedNavigationGroupsFrom(source)
      : cloneBaseNavigationLayout(source)
    originalNavigationTags.value = serializeNavigationTags()
  }

  const findNavigationGroup = (groupKey: string) => navigationLayout.value.find((group) => group.key === groupKey)

  const moveNavigationItem = (groupKey: string, itemId: string, direction: -1 | 1) => {
    if (!canWriteSettings.value) return
    const group = findNavigationGroup(groupKey)
    if (!group) return
    const index = group.items.findIndex((item) => item.id === itemId)
    const nextIndex = index + direction
    if (index < 0 || nextIndex < 0 || nextIndex >= group.items.length) return
    const [item] = group.items.splice(index, 1)
    group.items.splice(nextIndex, 0, item)
  }

  const updateNavigationItemTag = (groupKey: string, itemId: string, tag: string) => {
    if (!canWriteSettings.value) return
    const group = findNavigationGroup(groupKey)
    const item = group?.items.find((navigationItem) => navigationItem.id === itemId)
    if (!item) return
    item.tag = tag
  }

  const onNavigationDragStart = (event: DragEvent, groupKey: string, itemId: string) => {
    if (!canWriteSettings.value) return
    draggedNavigationItem.value = { groupKey, itemId }
    event.dataTransfer?.setData("text/plain", `${groupKey}:${itemId}`)
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move"
  }

  const onNavigationDragEnd = () => {
    draggedNavigationItem.value = null
  }

  const onNavigationDrop = (targetGroupKey: string, beforeItemId?: string) => {
    if (!canWriteSettings.value || !draggedNavigationItem.value) return
    if (beforeItemId === draggedNavigationItem.value.itemId) {
      draggedNavigationItem.value = null
      return
    }
    const sourceGroup = findNavigationGroup(draggedNavigationItem.value.groupKey)
    const targetGroup = findNavigationGroup(targetGroupKey)
    if (!sourceGroup || !targetGroup) return

    const sourceIndex = sourceGroup.items.findIndex((item) => item.id === draggedNavigationItem.value?.itemId)
    if (sourceIndex < 0) return
    let targetIndex = beforeItemId
      ? targetGroup.items.findIndex((targetItem) => targetItem.id === beforeItemId)
      : targetGroup.items.length
    if (targetIndex < 0) targetIndex = targetGroup.items.length
    if (sourceGroup === targetGroup && targetIndex > sourceIndex) targetIndex -= 1
    const [item] = sourceGroup.items.splice(sourceIndex, 1)
    targetGroup.items.splice(targetIndex, 0, item)
    draggedNavigationItem.value = null
  }

  return {
    navigationLayout,
    draggedNavigationItem,
    originalNavigationTags,
    serializeNavigationTags,
    loadNavigationTags,
    dispatchNavigationLayoutChange,
    moveNavigationItem,
    updateNavigationItemTag,
    onNavigationDragStart,
    onNavigationDragEnd,
    onNavigationDrop,
  }
}
