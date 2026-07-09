import assert from "node:assert/strict"
import {
  buildSidebarNavGroups,
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
import { hasRoleScope, hasUserScope } from "../lib/scopes.ts"
import { app, appStyle, settings } from "./testSource.mjs"

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
  item("memory"),
  item("evaluation"),
  item("approvals"),
  item("scheduler"),
  item("skills"),
  item("mcp"),
  item("knowledge"),
  item("cve"),
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
  memory: { name: "MemoryControl" },
  evaluation: { name: "AgentEvals" },
  approvals: { name: "ApprovalsWorkbench" },
  scheduler: { name: "SchedulerWorkbench" },
  skills: { name: "Skills" },
  mcp: { name: "MCP" },
  knowledge: { name: "Knowledge" },
  cve: { name: "CVE" },
  collect: { name: "Collect" },
  settings: { name: "Settings" },
}

assert.equal(
  canAccessShellNav("home", available, () => false),
  true,
  "home must stay available without scopes",
)

assert.equal(
  canAccessShellNav("dashboard", available, () => false),
  true,
  "dashboard must stay available without scopes",
)

assert.equal(
  canAccessShellNav("mcp", available, (scope) => scope === "mcp:read"),
  true,
  "scoped nav items must be visible when the matching scope is present",
)

assert.equal(
  canAccessShellNav("settings", available, () => false),
  false,
  "scoped nav items must be hidden without their scope",
)

assert.equal(
  canAccessShellNav("evaluation", available, (scope) => hasRoleScope("user", scope)),
  true,
  "evaluation must be available to users with the agent eval read scope",
)

assert.equal(
  canAccessShellNav("scheduler", available, (scope) => scope === "schedules:read"),
  true,
  "scheduler must use the native AgentOS schedules read scope",
)

assert.equal(
  canAccessShellNav("scheduler", available, (scope) => scope === "agent_os:admin"),
  false,
  "scheduler nav must not depend on the removed AIOS admin scheduler facade",
)

assert.equal(
  hasUserScope({ role: "guest", scopes: ["evals:read"] }, "evals:read"),
  true,
  "frontend scope checks must use server-issued scope claims",
)

assert.equal(
  hasUserScope({ role: "user", scopes: ["sessions:read"] }, "evals:read"),
  false,
  "frontend scope checks must not re-grant missing scopes when claims are present",
)

assert.equal(
  hasUserScope({ role: "guest", scopes: ["agent_os:admin"] }, "config:write"),
  true,
  "frontend scope checks must honor AgentOS admin scope claims",
)

assert.equal(
  hasUserScope({ role: "guest", permissions: ["agent_os:admin"] }, "config:write"),
  false,
  "frontend scope checks must ignore removed permissions fields",
)

assert.equal(
  canAccessShellNav("evaluation", available, (scope) => scope === "mcp:read"),
  false,
  "evaluation must stay hidden when only unrelated scopes are present",
)

assert.equal(
  canAccessShellNav("evaluation", available, (scope) => hasRoleScope("guest", scope)),
  false,
  "evaluation must stay hidden from guests",
)

assert.equal(
  canAccessShellNav("chat", new Set(["home"]), () => true),
  false,
  "unknown or unavailable nav ids must be hidden even if the scope would pass",
)

assert.deepEqual(
  splitPrimaryShellNavItems([item("chat"), item("cve"), item("collect"), item("settings")]),
  {
    mainNavItems: [item("chat")],
    securityDataNavItems: [item("cve"), item("collect")],
  },
  "primary nav splitting must exclude settings and group security data items",
)

assert.deepEqual(
  buildShellHomeSections(
    {
      operations: "Operations",
      knowledge: "Knowledge",
      governance: "Governance",
      securityData: "Security Data",
      settings: "Settings",
    },
    [
      { key: "operations", items: [item("home"), item("dashboard"), item("chat"), item("workflow")] },
      { key: "knowledge", items: [item("skills"), item("mcp"), item("knowledge")] },
      { key: "governance", items: [item("trace"), item("memory"), item("evaluation"), item("approvals"), item("scheduler")] },
      { key: "securityData", items: [item("cve"), item("collect")] },
      { key: "settings", items: [item("settings")] },
    ],
  ).map((section) => ({
    title: section.title,
    items: section.items.map((navItem) => navItem.id),
  })),
  [
    { title: "Operations", items: ["dashboard", "chat", "workflow"] },
    { title: "Knowledge", items: ["skills", "mcp", "knowledge"] },
    { title: "Governance", items: ["trace", "memory", "evaluation", "approvals", "scheduler"] },
    { title: "Security Data", items: ["cve", "collect"] },
  ],
  "home sections must mirror sidebar groups while excluding Home and Settings",
)

assert.deepEqual(
  buildSidebarNavGroups({
    defaultGroups: [
      { key: "operations", ids: ["home", "dashboard", "chat", "workflow"] },
      { key: "knowledge", ids: ["skills", "mcp", "knowledge"] },
      { key: "governance", ids: ["trace", "memory", "evaluation", "approvals", "scheduler"] },
      { key: "securityData", ids: ["cve", "collect"] },
      { key: "settings", ids: ["settings"] },
    ],
    storedGroups: [
      { key: "operations", items: [{ id: "home", tag: "" }, { id: "dashboard", tag: "" }, { id: "chat", tag: "" }, { id: "workflow", tag: "" }] },
      { key: "knowledge", items: [{ id: "trace", tag: "Trace moved" }, { id: "skills", tag: "" }, { id: "mcp", tag: "" }, { id: "knowledge", tag: "" }] },
      { key: "governance", items: [{ id: "evaluation", tag: "" }, { id: "approvals", tag: "" }, { id: "scheduler", tag: "" }] },
      { key: "securityData", items: [{ id: "cve", tag: "" }, { id: "collect", tag: "" }] },
      { key: "settings", items: [{ id: "settings", tag: "" }] },
    ],
    navItemsById: { home: item("home"), dashboard: item("dashboard"), ...navItemById },
    allNavItems: [item("home"), item("dashboard"), ...navItems.filter((navItem) => navItem.id !== "dashboard")],
    canAccess: () => true,
  }).map((group) => ({
    key: group.key,
    items: group.items.map((navItem) => navItem.label),
  })),
  [
    { key: "operations", items: ["home", "dashboard", "chat", "workflow"] },
    { key: "knowledge", items: ["Trace moved", "skills", "mcp", "knowledge"] },
    { key: "governance", items: ["evaluation", "approvals", "scheduler", "memory"] },
    { key: "securityData", items: ["cve", "collect"] },
    { key: "settings", items: ["settings"] },
  ],
  "sidebar groups must honor user cross-group layout instead of restoring moved items to default groups",
)

assert.match(
  app,
  /key:\s*"knowledge",\s*ids:\s*\["skills",\s*"mcp",\s*"knowledge"\]/,
  "App default sidebar Knowledge group must no longer include Memory",
)

assert.match(
  app,
  /key:\s*"governance",\s*ids:\s*\["trace",\s*"memory",\s*"evaluation",\s*"approvals",\s*"scheduler"\]/,
  "App default sidebar Governance group must place Memory directly below Trace",
)

assert.match(
  settings,
  /key:\s*"knowledge",[\s\S]*items:\s*\["Skills",\s*"MCP",\s*"Knowledge"\]/,
  "Settings default navigation Knowledge group must no longer include Memory",
)

assert.match(
  settings,
  /key:\s*"governance",[\s\S]*items:\s*\["Trace",\s*"Memory",\s*"Evaluation",\s*"Approvals",\s*"Scheduler"\]/,
  "Settings default navigation Governance group must place Memory directly below Trace",
)

assert.match(
  appStyle,
  /\.ag-nav-item\s*\{[^}]*min-height:\s*36px[^}]*gap:\s*8px[^}]*padding:\s*5px 8px/s,
  "Sidebar nav labels must use a tighter compact rhythm",
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
  "block h-full min-h-0",
  "module pages should delegate scroll padding to their shared page root",
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
  { currentUserId: "user-1", currentUserInitials: "OP" },
  "page workbenches should receive only shell user context props",
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
