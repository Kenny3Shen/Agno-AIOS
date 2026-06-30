import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const root = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(root, "..", "..")
const sourcePath = (relativePath) => join(root, relativePath)
const repoPath = (relativePath) => join(repoRoot, relativePath)
const readSource = (relativePath) => readFileSync(sourcePath(relativePath), "utf8")
const readOptionalSource = (relativePath) => {
  const path = sourcePath(relativePath)
  return existsSync(path) ? readFileSync(path, "utf8") : ""
}

const app = readSource("App.vue")
const authScreen = readSource("components/AuthScreen.vue")
const chat = readOptionalSource("components/Chat.vue")

assert.equal(
  app.includes("ag-nav-desc"),
  false,
  "sidebar navigation must not render secondary explanatory text",
)

assert.equal(
  app.includes("ag-user-chip"),
  false,
  "topbar must not render the user identity; the sidebar footer is the single user location",
)

assert.match(
  app,
  /ag-sidebar-toggle/,
  "sidebar must use a visible toggle button instead of pointer drag resizing",
)

assert.match(
  app,
  /currentModelLabel/,
  "brand model chip must be driven by the current Agent model label",
)

assert.equal(
  app.includes("startSidebarResize"),
  false,
  "sidebar resizing must not use drag handlers",
)

assert.equal(
  authScreen.includes("auth-copy"),
  false,
  "unauthenticated screen must avoid the previous long marketing copy panel",
)

assert.match(
  authScreen,
  /auth-brief/,
  "unauthenticated screen must use the compact shared shell visual language",
)

assert.equal(
  app.includes("ag-nav-section-title"),
  false,
  "expanded sidebar must not render category titles",
)

for (const category of ["安全运营", "数据底座", "AI 编排", "系统治理"]) {
  assert.equal(
    app.includes(category),
    false,
    `sidebar grouping must not expose the old category label: ${category}`,
  )
}

assert.match(
  app,
  /ag-nav-divider/,
  "sidebar nav must use simple divider grouping",
)

assert.match(
  app,
  /ag-chat-session-toggle/,
  "Chat nav item must include a small session expand/collapse trigger",
)

assert.match(
  app,
  /ag-chat-session-panel/,
  "Chat sessions must render under the Chat nav item",
)

assert.match(
  app,
  /agno-aios-chat-session-select/,
  "sidebar session clicks must notify the Chat view",
)

assert.match(
  app,
  /ag-user-menu-trigger/,
  "sidebar user footer must use a compact more menu trigger",
)

assert.equal(
  app.includes("ag-user-actions"),
  false,
  "sidebar footer must not render visible settings/logout action buttons",
)

assert.equal(
  existsSync(sourcePath("components/Chat.vue")),
  true,
  "Chat component file must align with the Chat nav label",
)

assert.equal(
  existsSync(sourcePath("components/Trace.vue")),
  true,
  "Trace component file must align with the Trace nav label",
)

assert.equal(
  existsSync(sourcePath("components/Dashboard.vue")),
  true,
  "Dashboard component file must align with the Dashboard nav label",
)

assert.equal(
  existsSync(sourcePath("components/Assets.vue")),
  true,
  "Assets component file must align with the Assets nav label",
)

assert.equal(
  existsSync(sourcePath("components/Collect.vue")),
  true,
  "Collect component file must align with the Collect nav label",
)

assert.equal(
  existsSync(sourcePath("components/Knowledge.vue")),
  true,
  "Knowledge component file must align with the Knowledge nav label",
)

assert.equal(
  existsSync(sourcePath("components/Skills.vue")),
  true,
  "Skills component file must align with the Skills nav label",
)

assert.equal(
  existsSync(sourcePath("components/MCP.vue")),
  true,
  "MCP component file must align with the MCP nav label",
)

assert.equal(
  existsSync(sourcePath("components/CVE.vue")),
  true,
  "CVE component file must align with the CVE nav label",
)

for (const oldComponent of [
  "components/LlmChat.vue",
  "components/AgentTracing.vue",
  "components/AgentSituation.vue",
  "components/AssetSearch.vue",
  "components/Url2Md.vue",
  "components/KnowledgeManage.vue",
  "components/SkillManage.vue",
  "components/McpManage.vue",
  "components/CveSearch.vue",
]) {
  assert.equal(
    existsSync(sourcePath(oldComponent)),
    false,
    `old component filename should be renamed: ${oldComponent}`,
  )
}

assert.equal(
  existsSync(repoPath("api/routes/assets.py")),
  true,
  "backend route filename must align with Assets",
)

assert.equal(
  existsSync(repoPath("api/routes/collect.py")),
  true,
  "backend route filename must align with Collect",
)

assert.equal(
  existsSync(repoPath("api/routes/trace.py")),
  true,
  "backend route filename must align with Trace",
)

for (const oldRoute of ["api/routes/asset.py", "api/routes/url2md.py", "api/routes/traces.py"]) {
  assert.equal(
    existsSync(repoPath(oldRoute)),
    false,
    `old backend route filename should be renamed: ${oldRoute}`,
  )
}

assert.equal(
  chat.includes("lg:grid-cols-[236px_minmax(0,1fr)]"),
  false,
  "Chat view must not reserve an internal desktop session sidebar",
)

assert.equal(
  chat.includes("showMobileSidebar"),
  false,
  "Chat sessions should live in the app sidebar rather than an internal mobile drawer",
)

assert.match(
  chat,
  /chat-composer-row/,
  "Chat input, model selector, and send button must share one composer row",
)
