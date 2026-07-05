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
  | "studio"
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

export type HomeSectionTitles = {
  operations: string
  controlPlane: string
  governance: string
  securityData: string
}

export type ShellComponentProps = {
  currentUserId: string | null
  currentUserInitials: string
  osModule?: ActiveOsControlModule
}

export type WorkspaceSignal = {
  label: string
  value: string | number
}

export const navPermissions: Partial<Record<ModuleNavId, string>> = {
  chat: "session:write:own",
  skills: "skill:read",
  mcp: "mcp:read",
  knowledge: "knowledge:read",
  trace: "trace:read:own",
  workflow: "mcp:read",
  sessions: "session:read:own",
  studio: "mcp:read",
  memory: "memory:read:own",
  evaluation: "agent_eval:read",
  approvals: "admin:read",
  scheduler: "admin:read",
  cve: "cve:read",
  collect: "collect:write",
  settings: "settings:read",
}

export const fullCanvasTabs = new Set<ModuleNavId>([
  "dashboard",
  "chat",
  "trace",
  "workflow",
  "mcp",
  "evaluation",
  "sessions",
  "studio",
  "memory",
  "approvals",
  "scheduler",
])

export const securityDataNavIds = new Set<NavId>(["cve", "collect"])

export const canAccessShellNav = (
  id: NavId,
  availableNavIds: Set<NavId>,
  hasPermission: (permission: string) => boolean,
) => {
  if (!availableNavIds.has(id)) return false
  if (id === "home" || id === "dashboard") return true
  const permission = navPermissions[id]
  return permission ? hasPermission(permission) : true
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
  navItemById: Record<ModuleNavId, NavItem>,
  canAccess: (id: NavId) => boolean,
): HomeSection[] => [
  {
    title: titles.operations,
    items: [navItemById.dashboard, navItemById.chat, navItemById.trace, navItemById.workflow],
  },
  { title: titles.controlPlane, items: [navItemById.studio, navItemById.memory] },
  {
    title: titles.governance,
    items: [navItemById.evaluation, navItemById.approvals, navItemById.scheduler],
  },
  {
    title: titles.securityData,
    items: [
      navItemById.skills,
      navItemById.mcp,
      navItemById.knowledge,
      navItemById.cve,
      navItemById.collect,
    ],
  },
]
  .map((section) => ({
    ...section,
    items: section.items.filter((item) => canAccess(item.id)),
  }))
  .filter((section) => section.items.length > 0)

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
  "studio",
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
