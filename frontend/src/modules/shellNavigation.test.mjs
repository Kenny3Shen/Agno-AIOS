import assert from "node:assert/strict"
import {
  buildShellComponentProps,
  buildShellHomeSections,
  buildWorkspaceSignals,
  canAccessShellNav,
  resolveShellComponent,
  resolveShellMeta,
  shellComponentKey,
  shellContentClass,
  splitPrimaryShellNavItems,
} from "./shellNavigation.ts"

const icon = {}
const item = (id) => ({
  id,
  label: id,
  description: id,
  icon,
  tone: "blue",
})

const navItems = [
  item("dashboard"),
  item("chat"),
  item("trace"),
  item("workflow"),
  item("studio"),
  item("memory"),
  item("evaluation"),
  item("approvals"),
  item("scheduler"),
  item("skills"),
  item("mcp"),
  item("knowledge"),
  item("cve"),
  item("assets"),
  item("collect"),
  item("settings"),
]
const navItemById = Object.fromEntries(navItems.map((navItem) => [navItem.id, navItem]))
const available = new Set(["home", ...navItems.map((navItem) => navItem.id)])
const components = {
  dashboard: { name: "Dashboard" },
  chat: { name: "Chat" },
  trace: { name: "Trace" },
  workflow: { name: "Workflow" },
  studio: { name: "AgentOSControl" },
  memory: { name: "MemoryControl" },
  evaluation: { name: "AgentOSControl" },
  approvals: { name: "AgentOSControl" },
  scheduler: { name: "AgentOSControl" },
  skills: { name: "Skills" },
  mcp: { name: "MCP" },
  knowledge: { name: "Knowledge" },
  cve: { name: "CVE" },
  assets: { name: "Assets" },
  collect: { name: "Collect" },
  sessions: { name: "AgentOSControl" },
  settings: { name: "Settings" },
}

assert.equal(
  canAccessShellNav("home", available, () => false),
  true,
  "home must stay available without permissions",
)

assert.equal(
  canAccessShellNav("dashboard", available, () => false),
  true,
  "dashboard must stay available without permissions",
)

assert.equal(
  canAccessShellNav("mcp", available, (permission) => permission === "mcp:read"),
  true,
  "permissioned nav items must be visible when the matching permission is present",
)

assert.equal(
  canAccessShellNav("settings", available, () => false),
  false,
  "permissioned nav items must be hidden without their permission",
)

assert.equal(
  canAccessShellNav("chat", new Set(["home"]), () => true),
  false,
  "unknown or unavailable nav ids must be hidden even if the permission would pass",
)

assert.deepEqual(
  splitPrimaryShellNavItems([item("chat"), item("cve"), item("assets"), item("settings")]),
  {
    mainNavItems: [item("chat")],
    securityDataNavItems: [item("cve"), item("assets")],
  },
  "primary nav splitting must exclude settings and group security data items",
)

assert.deepEqual(
  buildShellHomeSections(
    {
      operations: "Operations",
      controlPlane: "Control",
      governance: "Governance",
      securityData: "Security Data",
    },
    navItemById,
    (id) => !["approvals", "scheduler", "assets"].includes(id),
  ).map((section) => ({
    title: section.title,
    items: section.items.map((navItem) => navItem.id),
  })),
  [
    { title: "Operations", items: ["dashboard", "chat", "trace", "workflow"] },
    { title: "Control", items: ["studio", "memory"] },
    { title: "Governance", items: ["evaluation"] },
    { title: "Security Data", items: ["skills", "mcp", "knowledge", "cve", "collect"] },
  ],
  "home sections must keep product grouping while filtering inaccessible items",
)

assert.equal(
  shellContentClass("home"),
  "block h-full min-h-0",
  "home should use the base canvas",
)

assert.equal(
  shellContentClass("trace"),
  "block h-full min-h-0",
  "full-canvas modules should not get scroll padding",
)

assert.equal(
  shellContentClass("knowledge"),
  "block h-full min-h-0 overflow-auto p-4 sm:p-5",
  "dense modules should get the scroll container treatment",
)

assert.equal(
  resolveShellComponent("home", () => true, components),
  null,
  "home should not mount a module component",
)

assert.equal(
  resolveShellComponent("trace", (id) => id === "trace", components),
  components.trace,
  "accessible module tabs should resolve their component",
)

assert.equal(
  resolveShellComponent("settings", () => false, components),
  null,
  "inaccessible module tabs should not resolve a component",
)

assert.equal(
  resolveShellMeta("home", item("home"), navItems).id,
  "home",
  "home should keep its dedicated metadata",
)

assert.equal(
  resolveShellMeta("trace", item("home"), navItems).id,
  "trace",
  "module metadata should come from the visible nav items",
)

assert.equal(
  resolveShellMeta("settings", item("home"), navItems.filter((navItem) => navItem.id !== "settings")).id,
  "home",
  "hidden module metadata should fall back to home",
)

assert.equal(
  shellComponentKey("trace", 7),
  "trace-7",
  "component keys must include both active tab and render key",
)

assert.deepEqual(
  buildShellComponentProps("chat", "user-1", "OP"),
  { currentUserId: "user-1", currentUserInitials: "OP" },
  "regular modules should receive user context props",
)

assert.deepEqual(
  buildShellComponentProps("scheduler", "user-1", "OP"),
  { currentUserId: "user-1", currentUserInitials: "OP", osModule: "scheduler" },
  "AgentOS control tabs must receive their osModule prop",
)

assert.deepEqual(
  buildWorkspaceSignals(
    12,
    { modules: "Modules", dataPlane: "Data", runtime: "Runtime", session: "Session" },
    { dataPlane: "Ready", runtime: "Online", session: "Active" },
  ),
  [
    { label: "Modules", value: 12 },
    { label: "Data", value: "Ready" },
    { label: "Runtime", value: "Online" },
    { label: "Session", value: "Active" },
  ],
  "workspace signals should preserve shell labels and computed values",
)
