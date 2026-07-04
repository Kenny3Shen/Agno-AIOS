import assert from "node:assert/strict"
import {
  buildShellHomeSections,
  canAccessShellNav,
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
