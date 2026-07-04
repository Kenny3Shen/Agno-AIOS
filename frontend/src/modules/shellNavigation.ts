import type { Component } from "vue"
import type { OsControlModule } from "../types"

export type ModuleNavId =
  | "dashboard"
  | "cve"
  | "assets"
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
  evaluation: "admin:read",
  approvals: "admin:read",
  scheduler: "admin:read",
  cve: "cve:read",
  assets: "asset:read",
  collect: "collect:write",
  settings: "settings:read",
}

export const osControlTabs = new Set<ActiveOsControlModule>([
  "sessions",
  "studio",
  "memory",
  "evaluation",
  "approvals",
  "scheduler",
])

export const fullCanvasTabs = new Set<ModuleNavId>([
  "dashboard",
  "chat",
  "trace",
  "workflow",
  "mcp",
  ...osControlTabs,
])

export const securityDataNavIds = new Set<NavId>(["cve", "assets", "collect"])

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
      navItemById.assets,
      navItemById.collect,
    ],
  },
]
  .map((section) => ({
    ...section,
    items: section.items.filter((item) => canAccess(item.id)),
  }))
  .filter((section) => section.items.length > 0)

export const shellContentClass = (tab: NavId) => {
  const base = "block h-full min-h-0"
  if (tab === "home") return base
  return fullCanvasTabs.has(tab) ? base : `${base} overflow-auto p-4 sm:p-5`
}
