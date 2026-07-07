import type { Component } from "vue"
import type { OsControlModule } from "../types"

export type ModuleNavId =
  | "dashboard"
  | "cve"
  | "knowledge"
  | "collect"
  | "chat"
  | "trace"
  | "workflow"
  | "mcp"
  | "skills"
  | "sessions"
  | "memory"
  | "evaluation"
  | "approvals"
  | "scheduler"
  | "settings"

export type NavId = "home" | ModuleNavId
export type NavTone = "red" | "blue" | "green" | "yellow"
export type ActiveOsControlModule = Exclude<OsControlModule, "metrics">

export type NavItem = {
  id: NavId
  label: string
  description: string
  badge?: string
  icon: Component
  tone: NavTone
}

export type HomeSection = {
  title: string
  items: NavItem[]
}

export type SidebarDefaultNavGroup = {
  key: string
  ids: NavId[]
}

export type SidebarStoredNavItem = {
  id: NavId
  tag: string
}

export type SidebarStoredNavGroup = {
  key: string
  items: SidebarStoredNavItem[]
}

export type SidebarNavGroup = {
  key: string
  items: NavItem[]
}

export type HomeSectionTitles = Record<string, string>

export type ShellComponentProps = {
  currentUserId: string | null
  currentUserInitials: string
  osModule?: ActiveOsControlModule
}

export type WorkspaceSignal = {
  label: string
  value: string | number
}

export const navScopes: Partial<Record<ModuleNavId, string>> = {
  chat: "sessions:write",
  skills: "skill:read",
  mcp: "mcp:read",
  knowledge: "knowledge:read",
  trace: "traces:read",
  workflow: "mcp:read",
  sessions: "sessions:read",
  memory: "memories:read",
  evaluation: "evals:read",
  approvals: "approvals:read",
  scheduler: "schedules:read",
  cve: "cve:read",
  collect: "collect:write",
  settings: "config:read",
}

export const fullCanvasTabs = new Set<ModuleNavId>([
  "dashboard",
  "chat",
  "trace",
  "workflow",
  "mcp",
  "evaluation",
  "sessions",
  "memory",
  "approvals",
  "scheduler",
])

export const securityDataNavIds = new Set<NavId>(["cve", "collect"])

export const canAccessShellNav = (
  id: NavId,
  availableNavIds: Set<NavId>,
  hasScope: (scope: string) => boolean,
) => {
  if (!availableNavIds.has(id)) return false
  if (id === "home" || id === "dashboard") return true
  const scope = navScopes[id]
  return scope ? hasScope(scope) : true
}

export const splitPrimaryShellNavItems = (items: NavItem[]) => {
  const primaryItems = items.filter((item) => item.id !== "settings")
  return {
    mainNavItems: primaryItems.filter((item) => !securityDataNavIds.has(item.id)),
    securityDataNavItems: primaryItems.filter((item) => securityDataNavIds.has(item.id)),
  }
}

export const buildShellHomeSections = (
  titles: HomeSectionTitles,
  groups: SidebarNavGroup[],
  excludedIds: Set<NavId> = new Set(["home", "settings"]),
): HomeSection[] => groups
  .map((group) => ({
    title: titles[group.key] || group.key,
    items: group.items.filter((item) => !excludedIds.has(item.id)),
  }))
  .filter((section) => section.items.length > 0)

export const buildSidebarNavGroups = ({
  defaultGroups,
  storedGroups,
  navItemsById,
  allNavItems,
  canAccess,
}: {
  defaultGroups: SidebarDefaultNavGroup[]
  storedGroups: SidebarStoredNavGroup[]
  navItemsById: Record<NavId, NavItem>
  allNavItems: NavItem[]
  canAccess: (id: NavId) => boolean
}): SidebarNavGroup[] => {
  const assignedItems = new Set<NavId>()
  const storedItemIds = new Set<NavId>()

  for (const group of storedGroups) {
    for (const item of group.items) storedItemIds.add(item.id)
  }

  const groups = defaultGroups.map((defaultGroup) => {
    const storedGroup = storedGroups.find((group) => group.key === defaultGroup.key)
    const items: NavItem[] = []

    for (const storedItem of storedGroup?.items ?? []) {
      const item = navItemsById[storedItem.id]
      if (!item || assignedItems.has(item.id) || !canAccessNavItem(canAccess, item.id)) continue
      assignedItems.add(item.id)
      items.push({
        ...item,
        label: storedItem.tag.trim() || item.label,
      })
    }

    for (const id of defaultGroup.ids) {
      const item = navItemsById[id]
      if (!item || assignedItems.has(id) || storedItemIds.has(id) || !canAccessNavItem(canAccess, id)) continue
      assignedItems.add(id)
      items.push(item)
    }

    return { key: defaultGroup.key, items }
  })

  for (const item of allNavItems) {
    if (assignedItems.has(item.id) || storedItemIds.has(item.id) || !canAccessNavItem(canAccess, item.id)) continue
    assignedItems.add(item.id)
    groups[0]?.items.push(item)
  }

  return groups.filter((group) => group.items.length > 0)
}

const canAccessNavItem = (canAccess: (id: NavId) => boolean, id: NavId) => canAccess(id)

export const shellContentClass = (_tab: NavId) => {
  const base = "block h-full min-h-0"
  return base
}

export const resolveShellComponent = (
  tab: NavId,
  canAccess: (id: NavId) => boolean,
  componentMap: Record<ModuleNavId, Component>,
): Component | null => {
  if (tab === "home") return null
  if (!canAccess(tab)) return null
  return componentMap[tab]
}

export const resolveShellMeta = (
  tab: NavId,
  homeItem: NavItem,
  visibleModuleNavItems: NavItem[],
): NavItem => {
  if (tab === "home") return homeItem
  return visibleModuleNavItems.find((item) => item.id === tab) ?? homeItem
}

export const shellComponentKey = (tab: NavId, renderKey: number) => `${tab}-${renderKey}`

export const buildShellComponentProps = (
  tab: NavId,
  currentUserId: string | null,
  currentUserInitials: string,
): ShellComponentProps => {
  const baseProps = { currentUserId, currentUserInitials }
  if (tab !== "home" && osControlTabs.has(tab as ActiveOsControlModule)) {
    return { ...baseProps, osModule: tab as ActiveOsControlModule }
  }
  return baseProps
}

export const osControlTabs = new Set<ActiveOsControlModule>([
  "sessions",
  "memory",
  "approvals",
  "scheduler",
])

export const buildWorkspaceSignals = (
  moduleCount: number,
  labels: {
    modules: string
    dataPlane: string
    runtime: string
    session: string
  },
  values: {
    dataPlane: string
    runtime: string
    session: string
  },
): WorkspaceSignal[] => [
  { label: labels.modules, value: moduleCount },
  { label: labels.dataPlane, value: values.dataPlane },
  { label: labels.runtime, value: values.runtime },
  { label: labels.session, value: values.session },
]
