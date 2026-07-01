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
const trace = readOptionalSource("components/Trace.vue")
const dashboard = readOptionalSource("components/Dashboard.vue")

const assertTextOrder = (source, labels, message) => {
  let previousIndex = -1
  for (const label of labels) {
    const currentIndex = source.indexOf(label)
    assert.notEqual(currentIndex, -1, `${message}: missing ${label}`)
    assert.ok(
      currentIndex > previousIndex,
      `${message}: ${label} must appear after the previous label`,
    )
    previousIndex = currentIndex
  }
}

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
  /dashboardItem/,
  "Dashboard must be modeled separately so it can sit directly under Home",
)

assertTextOrder(
  app,
  ['label: "Home"', 'label: "Dashboard"', 'label: "Chat"', 'label: "Skills"', 'label: "MCP"', 'label: "Knowledge"', 'label: "Trace"'],
  "sidebar navigation order must match Agno OS control-plane priority",
)

for (const controlPlaneLabel of [
  'label: "Sessions"',
  'label: "Studio"',
  'label: "Memory"',
  'label: "Metrics"',
  'label: "Evaluation"',
  'label: "Approvals"',
  'label: "Scheduler"',
]) {
  assert.match(
    app,
    new RegExp(controlPlaneLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `sidebar must include missing AgentOS control-plane page ${controlPlaneLabel}`,
  )
}

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
  /ag-chat-session-archive/,
  "Chat session rows must include an archive/delete affordance",
)

assert.match(
  app,
  /archiveSidebarChatSession/,
  "Chat session archive action must be wired from the sidebar",
)

assert.match(
  readSource("composables/useApi.ts"),
  /archiveSession/,
  "Chat history API must expose archiveSession instead of permanent deletion for sidebar delete",
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

assert.match(
  trace,
  /trace-run-title/,
  "Trace detail header must use a stable block title container",
)

assert.match(
  app,
  /ag-trace-queue-panel/,
  "Trace Queue must be rendered as an expandable sidebar panel under the Trace nav item",
)

assert.equal(
  trace.includes("当前查询总量"),
  false,
  "Trace page must not keep dashboard-style query total metrics in the content area",
)

assert.equal(
  trace.includes("trace-summary-grid"),
  false,
  "Trace page summary metric grid must move out of Trace and into Dashboard",
)

for (const chartClass of ["latency-chart", "hour-heatmap", "radar-chart", "span-bar-list"]) {
  assert.match(
    dashboard,
    new RegExp(chartClass),
    `Dashboard must include data-platform chart surface ${chartClass}`,
  )
}

assert.match(
  trace,
  /trace-id-line/,
  "Trace identifiers must render in a dedicated wrapping line",
)

assert.match(
  trace,
  /trace-waterfall-row/,
  "Trace waterfall rows must use the refactored layout-safe row class",
)

assert.match(
  trace,
  /overflow-wrap:\s*anywhere/,
  "Trace page CSS must allow long IDs and JSON-like values to wrap instead of overlapping",
)

assert.match(
  trace,
  /scrollDetailIntoView/,
  "Trace mobile selection must move the detail pane into view after choosing a run",
)

assert.match(
  trace,
  /\.trace-canvas\s*{[^}]*height:\s*100%/s,
  "Trace canvas must close the desktop height chain so the right detail pane scrolls instead of being clipped",
)

assert.match(
  readOptionalSource("components/Knowledge.vue"),
  /knowledge-strategy-grid/,
  "Knowledge page must expose suffix-aware chunking strategy guidance",
)

assert.match(
  readOptionalSource("components/Knowledge.vue"),
  /searchType/,
  "Knowledge page must expose configurable search_type controls",
)

const knowledge = readOptionalSource("components/Knowledge.vue")

assert.match(
  knowledge,
  /knowledge-workflow-shell/,
  "Knowledge page must be reorganized as an AI workspace workflow shell",
)

assert.match(
  knowledge,
  /knowledge-stat-dashboard/,
  "Knowledge page must show status as a statistics dashboard",
)

assert.match(
  knowledge,
  /knowledge-upload-pipeline/,
  "Knowledge upload area must show the RAG ingestion pipeline",
)

assert.match(
  knowledge,
  /retrieval-playground/,
  "Knowledge page must expose a Retrieval Playground section",
)

assert.match(
  knowledge,
  /advanced-configuration/,
  "Knowledge page must collapse reader and RAG tuning details into Advanced Configuration",
)

assert.match(
  knowledge,
  /document-preview-drawer/,
  "Knowledge document management must provide a preview drawer without requiring backend changes",
)

assert.match(
  trace,
  /trace-inspector-shell/,
  "Trace page must use a two-pane AgentOS-style inspector shell",
)

assert.match(
  trace,
  /trace-io-section/,
  "Trace page must render parsed input and output sections",
)

assert.match(
  trace,
  /parsedSpan/,
  "Trace page must render backend-parsed span content instead of raw JSON only",
)

assert.match(
  trace,
  /trace-content-layout/,
  "Trace content area must use the reference-style left hierarchy and right content layout",
)

assert.match(
  trace,
  /trace-span-hierarchy/,
  "Trace content area must dedicate the left side to span hierarchy",
)

assert.match(
  trace,
  /trace-content-detail/,
  "Trace content area must dedicate the right side to selected span content",
)

assert.match(
  trace,
  /renderMarkdown/,
  "Trace content detail must render markdown instead of displaying markdown as plain text",
)

assert.match(
  trace,
  /trace-evidence-strip/,
  "Trace run header must use compact copyable evidence chips instead of large Session/Run/Agent/Workflow cards",
)

assert.match(
  trace,
  /activeDetailTab/,
  "Trace span detail must expose an Info/Metadata tab state",
)

assert.match(
  trace,
  /isJsonPayload/,
  "Trace input and output sections must render JSON payloads as formatted code blocks",
)

assert.match(
  trace,
  /trace-metadata-ledger/,
  "Trace Metadata tab must collect span offsets, parent, events, ids, extracted metadata, and raw attributes",
)
