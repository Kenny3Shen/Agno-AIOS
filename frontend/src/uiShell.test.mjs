import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { createI18n } from "vue-i18n"
import { enUS } from "./i18n/locales/en-US.ts"
import { zhCN } from "./i18n/locales/zh-CN.ts"
import "./modules/shellNavigation.test.mjs"
import "./modules/agentEvalsWorkbench.test.mjs"
import "./modules/traceWorkbench.test.mjs"
import "./modules/workflowBuilder.test.mjs"

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
const appStyle = readSource("style.css")
const designTokens = readSource("styles/tokens.css")
const viteConfig = readOptionalSource("../vite.config.ts")
const apiMain = readOptionalSource("../../api/main.py")
const authScreen = readSource("components/AuthScreen.vue")
const chat = readOptionalSource("components/Chat.vue")
const trace = readOptionalSource("components/Trace.vue")
const dashboard = readOptionalSource("components/Dashboard.vue")
const cve = readOptionalSource("components/CVE.vue")
const mcp = readOptionalSource("components/MCP.vue")
const skills = readOptionalSource("components/Skills.vue")
const collect = readOptionalSource("components/Collect.vue")
const settings = readOptionalSource("components/Settings.vue")
const knowledge = readOptionalSource("components/Knowledge.vue")
const agentOSControl = readOptionalSource("components/AgentOSControl.vue")
const memoryControl = readOptionalSource("components/MemoryControl.vue")
const workflow = readOptionalSource("components/Workflow.vue")
const typesSource = readSource("types/index.ts")
const useApi = readSource("composables/useApi.ts")
const apiClient = readOptionalSource("lib/apiClient.ts")
const authClientSource = readOptionalSource("lib/authClient.ts")
const clipboard = readOptionalSource("lib/clipboard.ts")
const authStoreSource = readOptionalSource("stores/auth.ts")
const permissions = readOptionalSource("lib/permissions.ts")
const shellNavigation = readOptionalSource("modules/shellNavigation.ts")

const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  messages: {
    "en-US": enUS,
    "zh-CN": zhCN,
  },
})

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

const assertNoPillStatChip = (source, className, message) => {
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s*\\{[^}]*border-radius:\\s*999px`, "s"),
    message,
  )
}

assert.equal(
  app.includes("ag-nav-desc"),
  false,
  "sidebar navigation must not render secondary explanatory text",
)

assert.match(
  viteConfig,
  /outDir:\s*['"]dist['"]/,
  "frontend build output must stay in ignored frontend/dist for ordinary commits",
)

assert.match(
  viteConfig,
  /manualChunks/,
  "frontend build must define manual chunks to keep large vendors split",
)

assert.match(
  apiMain,
  /frontend_static_dir/,
  "backend must resolve the frontend static directory through a reusable helper",
)

assert.match(
  apiMain,
  /Path\("frontend\/dist"\)[\s\S]*Path\("source"\)/,
  "backend must prefer frontend/dist builds and only fall back to root source/",
)

for (const locale of ["zh-CN", "en-US"]) {
  i18n.global.locale.value = locale
  assert.doesNotThrow(
    () => i18n.global.t("mcp.upload.manifestPlaceholder"),
    `MCP upload manifest placeholder must compile in ${locale}`,
  )
}

assert.equal(
  app.includes("ag-user-chip"),
  false,
  "topbar must not render the user identity; the sidebar footer is the single user location",
)

assert.equal(
  app.includes("<p>{{ currentMeta.description }}</p>"),
  false,
  "topbar must stay compact and avoid rendering duplicate page descriptions",
)

assert.equal(
  app.includes("ag-command"),
  false,
  "home must avoid the previous oversized hero block",
)

assert.equal(
  app.includes("ag-plane-grid"),
  false,
  "home must avoid the extra runtime overview card wall",
)

assert.equal(
  app.includes("ag-topbar-button"),
  false,
  "topbar refresh control must use the compact icon treatment",
)

assert.match(
  app,
  /ag-topbar-icon/,
  "topbar actions must use compact icon buttons",
)

assert.match(
  app,
  /ag-sidebar-toggle/,
  "sidebar must use a visible toggle button instead of pointer drag resizing",
)

assert.match(
  app,
  /gridTemplateColumns:\s*isMobile\.value\s*\?\s*undefined\s*:/,
  "mobile shell must not keep desktop sidebar grid columns while using a fixed overlay sidebar",
)

assert.match(
  app,
  /currentModelLabel/,
  "brand model chip must be driven by the current Agent model label",
)

assert.match(
  app,
  /useI18n\(\)/,
  "App shell must read display copy from vue-i18n",
)

assert.match(
  app,
  /setI18nLocale/,
  "App shell must synchronize the shell locale store with vue-i18n",
)

assert.match(
  app,
  /t\("shell\.nav\.home\.label"\)/,
  "App shell navigation labels must be sourced from i18n messages",
)

for (const hardcodedShellCopy of [
  ">New chat<",
  ">Sessions<",
  ">No sessions<",
  ">Refresh traces<",
  ">Trace Observability<",
  "关闭导航遮罩",
  "当前会话",
  "已认证",
  "运行平面",
  "未登录",
  "运营控制面",
  "资产、漏洞、知识入库",
  "对话、MCP、Trace 观测",
  "会话加载失败",
  "Trace 队列加载失败",
  "会话已归档",
  "归档会话失败",
  ">打开<",
  ">No traces<",
]) {
  assert.equal(
    app.includes(hardcodedShellCopy),
    false,
    `App shell must not hardcode sidebar copy: ${hardcodedShellCopy}`,
  )
}

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

assert.match(
  authScreen,
  /auth\.brief\.items\.chat/,
  "AuthScreen brief chips must be sourced from i18n",
)

assert.match(
  authScreen,
  /auth\.oauth\.label/,
  "AuthScreen OAuth label must be sourced from i18n",
)

assert.match(
  authScreen,
  /auth\.footer\.jwt/,
  "AuthScreen footer technology chips must be sourced from i18n",
)

assert.match(
  authScreen,
  /useI18n\(\)/,
  "AuthScreen must read user-facing copy from vue-i18n",
)

assert.match(
  authStoreSource,
  /hasRolePermission/,
  "auth store must reuse the shared frontend RBAC helper",
)

assert.match(
  authStoreSource,
  /is_superuser/,
  "auth store must elevate superusers to admin in shell state",
)

assert.match(
  authStoreSource,
  /hasPermission = \(permission: string\)/,
  "auth store must expose a reusable permission helper",
)

assert.match(
  permissions,
  /ROLE_PERMISSIONS/,
  "frontend RBAC helper must define the role permission matrix",
)

assert.match(
  permissions,
  /"collect:write"/,
  "frontend RBAC helper must reflect write-only modules such as Collect",
)

assert.match(
  permissions,
  /agent_eval:read/,
  "frontend permissions must include Agent Eval read permission",
)

assert.match(
  permissions,
  /agent_eval:write/,
  "frontend permissions must include Agent Eval write permission",
)

assert.match(
  permissions,
  /agent_eval:run/,
  "frontend permissions must include Agent Eval run permission",
)

for (const hardcodedAuthCopy of [
  "登录后继续使用 Chat、MCP、Trace 与模型设置。",
  "进入工作台",
  "创建账号",
  "登录",
  "注册",
  "邮箱",
  "密码",
  "至少 8 位",
  "进入 Agno AIOS",
  "创建并进入",
  "请输入有效邮箱",
  "密码至少需要 8 位",
  "认证失败",
  "OAuth 授权失败",
]) {
  assert.equal(
    authScreen.includes(hardcodedAuthCopy),
    false,
    `AuthScreen must not hardcode auth copy: ${hardcodedAuthCopy}`,
  )
}

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

assert.match(
  app,
  /ag-home-summary/,
  "Home must use the compact summary strip",
)

assert.match(
  app,
  /ag-module-tile/,
  "Home modules must render as compact direct-action tiles",
)

assert.equal(
  mcp.includes("xl:grid-cols-[minmax(0,1fr)_320px]"),
  false,
  "MCP must avoid the previous wide right-side context rail",
)

assert.match(
  mcp,
  /mcp-summary-strip/,
  "MCP must use the compact summary strip instead of metric cards and a side rail",
)

assert.match(
  mcp,
  /<div class="mcp-console ag-page-flow">\s*<section class="mcp-summary-strip ag-stat-strip">/,
  "MCP summary strip must be a direct page-flow child like Knowledge",
)

assert.doesNotMatch(
  mcp,
  /mcp-toolbar ag-content-panel[\s\S]{0,800}mcp-summary-strip|\.mcp-summary-url\s*\{[^}]*flex:/s,
  "MCP toolbar must not wrap or resize the Knowledge-style summary strip",
)

assert.equal(
  agentOSControl.includes("agentos-notes"),
  false,
  "AgentOS control pages must avoid the previous notes sidebar",
)

assert.equal(
  agentOSControl.includes("agentos-note-strip"),
  false,
  "AgentOS control pages must not render implementation note chips",
)

assert.match(
  shellNavigation,
  /navPermissions/,
  "Shell navigation must define module visibility permissions",
)

assert.match(
  app,
  /canAccessNav/,
  "App shell must gate module access by the current role",
)

assert.match(
  app,
  /visibleNavItems/,
  "App shell must filter inaccessible modules out of the sidebar",
)

assert.match(
  app,
  /visibleSettingsItem/,
  "App shell must hide the settings entry when the current role cannot read it",
)

assertTextOrder(
  app,
  [
    't("shell.nav.home.label")',
    't("shell.nav.dashboard.label")',
    't("shell.nav.chat.label")',
    't("shell.nav.skills.label")',
    't("shell.nav.mcp.label")',
    't("shell.nav.knowledge.label")',
    't("shell.nav.trace.label")',
  ],
  "sidebar navigation order must match Agno OS control-plane priority",
)

for (const controlPlaneLabel of [
  't("shell.nav.studio.label")',
  't("shell.nav.memory.label")',
  't("shell.nav.evaluation.label")',
  't("shell.nav.approvals.label")',
  't("shell.nav.scheduler.label")',
]) {
  assert.match(
    app,
    new RegExp(controlPlaneLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `sidebar must include missing AgentOS control-plane page ${controlPlaneLabel}`,
  )
}

assert.equal(
  app.includes('t("shell.nav.metrics.label")'),
  false,
  "Metrics must be merged into Trace instead of remaining as a standalone sidebar page",
)

assert.equal(
  app.includes('t("shell.nav.sessions.label")'),
  false,
  "Sessions must be merged into Trace instead of remaining as a standalone sidebar page",
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
  /ag-chat-session-menu-trigger/,
  "Chat session rows must include a compact action menu trigger",
)

assert.match(
  app,
  /copySidebarSessionRuns/,
  "Chat session action menu must support copying runs",
)

assert.match(
  app,
  /archiveSidebarChatSession/,
  "Chat session archive action must be wired from the sidebar",
)

assert.match(
  useApi,
  /archiveSession/,
  "Chat history API must expose archiveSession instead of permanent deletion for sidebar delete",
)

assert.match(
  apiClient,
  /Authorization.*Bearer/,
  "shared API client must attach Bearer auth tokens",
)

assert.equal(
  /user_id:\s*userId/.test(useApi),
  false,
  "Chat API must not send frontend-provided user_id",
)

assert.equal(
  /archiveSession\s*=\s*async\s*\([^)]*userId/.test(useApi),
  false,
  "archiveSession must not accept frontend-provided user id",
)

for (const traceParam of ["session_id", "run_id", "agent_id", "team_id", "workflow_id", "user_id"]) {
  assert.match(
    useApi,
    new RegExp(`qs\\.set\\('${traceParam}'`),
    `Trace API must preserve ${traceParam} query parameter when provided`,
  )
}

for (const sessionTraceParam of ["session_id", "user_id"]) {
  assert.match(
    trace,
    new RegExp(`${sessionTraceParam}:\\s*session\\.${sessionTraceParam === "session_id" ? "session_id" : "user_id"}`),
    `Trace page must pass selected session ${sessionTraceParam} into listTraces`,
  )
}

for (const traceInteraction of ["@keyup.enter=\"refresh\"", "@click=\"refresh\""]) {
  assert.match(
    trace,
    new RegExp(traceInteraction.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `Trace filters must keep manual refresh interaction: ${traceInteraction}`,
  )
}

assert.match(
  useApi,
  /const cleanParam =/,
  "Trace API must normalize query parameters before appending them to URLSearchParams",
)

assert.equal(
  /\p{Script=Han}/u.test(useApi),
  false,
  "API composables must not hardcode localized Chinese fallback copy",
)

assert.match(
  useApi,
  /cleanParam\(params\.session_id\)/,
  "Trace API must trim session_id before querying",
)

assert.match(
  clipboard,
  /execCommand\('copy'\)/,
  "clipboard helper must fall back when navigator.clipboard is unavailable",
)

assert.match(
  clipboard,
  /catch\s*\{[\s\S]*Fall back below when browser permission or context blocks clipboard API/,
  "clipboard helper must fall back when navigator.clipboard is blocked by permissions",
)

assert.match(
  clipboard,
  /textarea\.focus/,
  "clipboard fallback must focus the temporary textarea before copy",
)

assert.match(
  clipboard,
  /setSelectionRange/,
  "clipboard fallback must explicitly select the text range before copy",
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

for (const chatHook of [
  "markdown-skeleton",
  "stream-cursor",
  "code-copy",
  "zoomedImage",
  "source-collapse",
  "thinking-collapse",
  "tool-timeline",
]) {
  assert.match(
    chat,
    new RegExp(chatHook),
    `Chat must expose ${chatHook} interaction support`,
  )
}

assert.doesNotMatch(
  chat,
  /import\(["']mermaid["']\)|language-mermaid|mermaid-fallback/,
  "Chat must not bundle Mermaid rendering support",
)

for (const bulkyHeaderClass of [
  "agent-chat-header",
  "agent-core",
  "agent-model-pill",
]) {
  assert.equal(
    chat.includes(bulkyHeaderClass),
    false,
    `Chat page must remove bulky top header element: ${bulkyHeaderClass}`,
  )
}

assert.match(
  chat,
  /useI18n\(\)/,
  "Chat page must read user-facing copy from vue-i18n",
)

for (const hardcodedChatCopy of [
  "Agent 对话",
  "执行中",
  "待命",
  "Markdown 内容加载中",
  "展开思考",
  "收起思考",
  "展开来源",
  "收起来源",
  "Agent 正在规划下一步",
  "描述目标，例如：分析这个 CVE 的暴露面影响",
  "选择模型",
  "未填写模型 ID",
  "发送任务",
  "放大预览",
  "你好！我是 AgentOS 安全智能体",
  "未选择",
  "未加载到模型配置",
  "请选择一个可用模型",
  "已禁用，请切换模型",
  "未完成参数配置",
  "帮我评估 CVE 的暴露面影响",
  "生成一次外部暴露面排查计划",
  "把这段告警整理成处置步骤",
  "模型配置加载失败",
  "模型不可用",
  "抱歉，处理请求时遇到错误。请稍后再试。",
]) {
  assert.equal(
    chat.includes(hardcodedChatCopy),
    false,
    `Chat page must not hardcode user-facing copy: ${hardcodedChatCopy}`,
  )
}

for (const traceFilterHook of [
  "sessionFilters.sessionId",
  "sessionFilters.userId",
  "sessionFilters.keyword",
  "sessionFilters.status",
  "filteredSessions",
  "selectSession",
  "scheduleFilterRefresh",
]) {
  assert.match(
    trace,
    new RegExp(traceFilterHook.replace(".", "\\.")),
    `Trace filters must auto-refresh when ${traceFilterHook} changes`,
  )
}

for (const removedPanelCopy of [
  "MCP 工具中枢",
  "基于 FastMCP 的服务控制、访问 Token 与外部接入",
  "TRACE CONSOLE",
  "Agent 观测中心",
  "会话记录、Trace 队列、Span 瀑布与错误上下文统一查看",
  "从左侧队列进入 Trace，可查看 Span 瀑布、树状关系和属性详情。",
  "未来规划",
  "启用 Agent Team 架构后",
  "注意：Skill 启用/禁用在下一次 Agent 对话时生效。",
]) {
  assert.equal(
    `${mcp}\n${trace}\n${skills}`.includes(removedPanelCopy),
    false,
    `right/content panel must remove middle explanatory copy: ${removedPanelCopy}`,
  )
}

assert.match(
  skills,
  /skills-console/,
  "Skills page must use an explicit bordered console surface",
)

assert.match(
  skills,
  /skill-card/,
  "Skills rows must use the shared tokenized card surface",
)

assert.match(
  skills,
  /skill-summary-strip/,
  "Skills page must summarize total, enabled, and script counts in a compact strip",
)

assert.match(
  skills,
  /<div class="skills-console ag-page-flow">\s*<section class="skill-summary-strip ag-stat-strip">/,
  "Skills summary strip must be a direct page-flow child like Knowledge",
)

assert.match(
  skills,
  /skill-summary-chip ag-stat-chip/,
  "Skills summary items must use the shared Stat Chip surface",
)

assertNoPillStatChip(
  skills,
  "skill-summary-chip",
  "Skills Stat Chips must use the shared 8px rectangular chip shape, not pill styling",
)

assert.doesNotMatch(
  skills,
  /\.skill-summary-chip\s+(span|small|strong)\s*\{/,
  "Skills Stat Chips must inherit label and value typography from the shared ag-stat-chip style",
)

assert.doesNotMatch(
  skills,
  /skills-action-bar ag-content-panel[\s\S]{0,800}skill-summary-strip|skills-header ag-content-panel/,
  "Skills action toolbar must not wrap the Knowledge-style summary strip",
)

assert.match(
  skills,
  /skills-console ag-page-flow/,
  "Skills page must use the shared page flow instead of a local full-height surface",
)

assert.match(
  skills,
  /status-pill/,
  "Skills page must use the shared compact status pill language",
)

assert.equal(
  skills.includes("skill-status-dot"),
  false,
  "Skills page must avoid the old standalone status dot styling",
)

assert.equal(
  skills.includes("skill-secondary-action"),
  false,
  "Skills page must not render the disabled placeholder upload action in the header",
)

assert.match(
  skills,
  /useI18n\(\)/,
  "Skills page must read user-facing copy from vue-i18n",
)

assert.match(
  skills,
  /hasPermission\("skill:write"\)/,
  "Skills page must check write permission before allowing skill toggles",
)

assert.match(
  skills,
  /:disabled="!canWriteSkills"/,
  "Skills page must disable skill toggles for read-only users",
)

assert.match(
  mcp,
  /useI18n\(\)/,
  "MCP page must read user-facing copy from vue-i18n",
)

assert.match(
  mcp,
  /hasPermission\("mcp:write"\)/,
  "MCP page must check write permission before allowing mutating actions",
)

assert.match(
  mcp,
  /:disabled="!canWriteMcp"/,
  "MCP page must disable mutating controls for read-only users",
)

for (const bulkyMcpMetric of [
  '"Control"',
  '"Integrated"',
]) {
  assert.equal(
    mcp.includes(bulkyMcpMetric),
    false,
    `MCP summary strip must not render duplicate control metric: ${bulkyMcpMetric}`,
  )
}

assert.match(
  mcp,
  /mcp-summary-chip ag-stat-chip/,
  "MCP summary items must use the shared Stat Chip surface",
)

assertNoPillStatChip(
  mcp,
  "mcp-summary-chip",
  "MCP Stat Chips must use the shared 8px rectangular chip shape, not pill styling",
)

assert.doesNotMatch(
  mcp,
  /\.mcp-summary-chip\s+(span|small|strong)\s*\{/,
  "MCP Stat Chips must inherit label and value typography from the shared ag-stat-chip style",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s*\{[^}]*border-radius:\s*8px[^}]*background:\s*var\(--ag-panel-soft\)[^}]*padding:\s*7px\s+10px/s,
  "Shared Stat Chip style must define the consistent compact 8px rectangular chip surface",
)

assert.match(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*flex-wrap:\s*nowrap[^}]*overflow:\s*hidden/s,
  "Shared Stat Strips must provide the compact single-row layout globally",
)

assert.match(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*border:\s*1px\s+solid\s+var\(--ag-border\)[^}]*border-radius:\s*8px[^}]*background:\s*var\(--ag-panel\)[^}]*padding:\s*8px/s,
  "Shared Stat Strips must render as a consistent standalone bubble bar",
)

assert.match(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*block-size:\s*var\(--ag-stat-strip-height\)/s,
  "Shared Stat Strips must use one fixed height across pages",
)

assert.match(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*margin-block:\s*10px/s,
  "Shared Stat Strips must keep consistent vertical spacing from surrounding content",
)

assert.match(
  designTokens,
  /--ag-page-title-gap:\s*10px;[\s\S]*--ag-section-gap:\s*12px;[\s\S]*--ag-stat-strip-height:\s*50px;[\s\S]*--ag-container-border:\s*1px solid var\(--ag-border\);[\s\S]*--ag-container-radius:\s*12px;[\s\S]*--ag-container-padding:\s*14px;/,
  "Layout tokens must define the shared page rhythm and container shell",
)

assert.match(
  appStyle,
  /\.ag-page-flow\s*\{[^}]*gap:\s*var\(--ag-section-gap\)[^}]*padding:\s*var\(--ag-page-title-gap\)\s+var\(--ag-page-padding-inline\)\s+var\(--ag-page-padding-block-end\)/s,
  "Shared page flow must own the top spacing and section gap",
)

assert.match(
  appStyle,
  /\.ag-page-flow\s+:where\(\.ag-stat-strip\)\s*\{[^}]*margin-block:\s*0/s,
  "Page-scoped Stat Strips must rely on the shared page gap instead of adding extra Knowledge top spacing",
)

assert.match(
  appStyle,
  /\.ag-content-panel,\s*\n\.ag-right-panel\s*\{[^}]*border:\s*var\(--ag-container-border\)[^}]*border-radius:\s*var\(--ag-container-radius\)[^}]*background:\s*var\(--ag-container-bg\)[^}]*padding:\s*var\(--ag-container-padding\)[^}]*box-shadow:\s*var\(--ag-container-shadow\)/s,
  "Shared content panels must use the container token shell",
)

assert.match(
  appStyle,
  /\.ag-workspace-panel\s*\{[^}]*border:\s*var\(--ag-container-border\)[^}]*border-radius:\s*var\(--ag-container-radius\)[^}]*background:\s*var\(--ag-container-bg\)[^}]*box-shadow:\s*var\(--ag-container-shadow\)/s,
  "Shared workspace panels must use the same container token shell without content padding",
)

for (const [source, pattern, label] of [
  [dashboard, /situation-page ag-page-flow/, "Dashboard page"],
  [dashboard, /situation-header ag-content-panel/, "Dashboard header"],
  [dashboard, /situation-panel ag-content-panel/, "Dashboard panels"],
  [skills, /skills-action-bar ag-content-panel/, "Skills toolbar"],
  [skills, /skill-upload-panel ag-content-panel/, "Skills upload"],
  [mcp, /mcp-console ag-page-flow/, "MCP page"],
  [mcp, /mcp-toolbar ag-content-panel/, "MCP toolbar"],
  [mcp, /mcp-body ag-content-panel/, "MCP body"],
  [knowledge, /knowledge-console knowledge-workflow-shell ag-page-flow/, "Knowledge page"],
  [knowledge, /knowledge-panel ag-content-panel knowledge-upload-panel/, "Knowledge upload"],
  [knowledge, /knowledge-panel ag-content-panel retrieval-playground/, "Knowledge retrieval"],
  [trace, /trace-console ag-page-flow/, "Trace page"],
  [trace, /trace-query-toolbar ag-content-panel/, "Trace filters"],
  [trace, /trace-body-grid ag-workspace-panel/, "Trace workbench"],
  [workflow, /workflow-console ag-page-flow/, "Workflow page"],
  [workflow, /workflow-header ag-content-panel/, "Workflow header"],
  [workflow, /workflow-workbench ag-workspace-panel/, "Workflow workbench"],
  [memoryControl, /memory-control ag-page-flow/, "Memory page"],
  [memoryControl, /memory-query-panel ag-content-panel/, "Memory filters"],
  [memoryControl, /memory-queue-panel ag-workspace-panel/, "Memory queue"],
  [memoryControl, /memory-list-panel ag-workspace-panel/, "Memory list"],
  [agentOSControl, /agentos-control ag-page-flow/, "AgentOS page"],
  [agentOSControl, /agentos-panel ag-content-panel scheduler-list-panel/, "Scheduler list"],
  [agentOSControl, /agentos-panel ag-content-panel/, "AgentOS ledger"],
  [cve, /cve-console ag-page-flow/, "CVE page"],
  [cve, /cve-query-panel ag-content-panel/, "CVE search"],
  [cve, /cve-results-panel ag-content-panel/, "CVE results"],
  [collect, /collect-console ag-page-flow/, "Collect page"],
  [collect, /collect-query-panel ag-content-panel/, "Collect input"],
  [collect, /collect-result-panel ag-content-panel/, "Collect result"],
  [settings, /settings-page ag-page-flow/, "Settings page"],
  [settings, /settings-toolbar ag-content-panel/, "Settings toolbar"],
]) {
  assert.match(
    source,
    pattern,
    `${label} must use the shared multi-section container system`,
  )
}

for (const [source, pattern, label] of [
  [workflow, /workflow-inspector workflow-panel ag-right-panel/, "Workflow inspector"],
  [trace, /trace-detail-drawer ag-right-panel/, "Trace detail"],
  [memoryControl, /memory-detail-panel ag-right-panel/, "Memory detail"],
  [agentOSControl, /agentos-panel scheduler-detail-panel ag-right-panel/, "Scheduler detail"],
]) {
  assert.match(
    source,
    pattern,
    `${label} right content panel must stay on the shared right panel shell`,
  )
}

assert.doesNotMatch(
  memoryControl,
  /\.memory-detail-panel\s*\{[^}]*linear-gradient/s,
  "Memory right detail panel must not override the shared panel background with a local gradient",
)

assert.doesNotMatch(
  trace,
  /\.trace-detail-drawer\s*\{[^}]*border-left:/s,
  "Trace right detail panel must not use a one-sided border instead of the shared panel border",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*border-bottom:/s,
  "Shared Stat Strips must not use the old bottom-divider treatment",
)

assert.doesNotMatch(
  memoryControl,
  /\.memory-command\s*\{[^}]*border-bottom:/s,
  "Memory command area must not add a full-width divider outside the shared containers",
)

assert.doesNotMatch(
  memoryControl,
  /memory-command-copy|agentOS\.memory\.modeAutomatic|agentOS\.memory\.deskTitle|memoryModeDetails|agentOS\.memory\.updateOnRun|agentOS\.memory\.sessionSummaries|agentOS\.memory\.readonly/,
  "Memory page must not render the removed automatic-memory desk copy or mode-status sentence",
)

assert.doesNotMatch(
  workflow,
  /workflow-title|workflow\.kicker|workflow\.title|workflow\.description/,
  "Workflow page must not render the removed top title and description copy",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s*\{[^}]*flex:\s*0\s+1\s+164px[^}]*justify-content:\s*space-between/s,
  "Shared Stat Chips must keep a stable compact width with separated label and value",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s+strong\s*\{[^}]*text-overflow:\s*ellipsis/s,
  "Shared Stat Chip values must use single-line ellipsis globally",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s+:where\(span,\s*small,\s*em\)\s*\{[^}]*font-size:\s*11px/s,
  "Shared Stat Chip labels must be large enough to read at a glance",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s+strong\s*\{[^}]*font-size:\s*12px/s,
  "Shared Stat Chip values must be large enough to read at a glance",
)

assert.match(
  app,
  /ag-home-summary-strip ag-stat-strip/,
  "Home summary signals must use the shared compact Stat Strip",
)

assert.match(
  appStyle,
  /\.ag-home-summary-strip\s*\{[^}]*min-width:\s*0/s,
  "Home summary signal strip must be shrinkable inside the shell card",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-home-signal\s*\{[^}]*flex:/s,
  "Home summary signal chips must inherit compact width from the shared ag-stat-chip style",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-home-signal\s+(span|small|strong)\s*\{/,
  "Home summary signal chips must inherit label and value typography from the shared ag-stat-chip style",
)

for (const [source, className, label] of [
  [dashboard, "situation-metric", "Dashboard"],
  [trace, "trace-stat-card", "Trace"],
  [agentOSControl, "agentos-summary-chip", "AgentOS"],
  [workflow, "workflow-stat-chip", "Workflow"],
]) {
  assert.match(
    source,
    new RegExp(`${className} ag-stat-chip`),
    `${label} Stat Chips must use the shared Stat Chip surface`,
  )
  assertNoPillStatChip(
    source,
    className,
    `${label} Stat Chips must use the shared 8px rectangular chip shape, not pill styling`,
  )
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s+(span|small|strong)\\s*\\{`, "s"),
    `${label} Stat Chips must inherit label and value typography from the shared ag-stat-chip style`,
  )
}

for (const [source, className, label] of [
  [trace, "trace-stat-strip", "Trace"],
  [agentOSControl, "agentos-summary-strip", "AgentOS"],
  [workflow, "workflow-stat-strip", "Workflow"],
  [mcp, "mcp-summary-strip", "MCP"],
  [skills, "skill-summary-strip", "Skills"],
  [knowledge, "knowledge-stat-strip", "Knowledge"],
  [memoryControl, "memory-priority-strip", "Memory"],
]) {
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s*\\{[^}]*display:\\s*grid`, "s"),
    `${label} Stat Strip must inherit layout from the shared ag-stat-strip style`,
  )
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s*\\{[^}]*border(?:-bottom)?:`, "s"),
    `${label} Stat Strip must inherit bubble borders from the shared ag-stat-strip style`,
  )
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s*\\{[^}]*background:`, "s"),
    `${label} Stat Strip must inherit background from the shared ag-stat-strip style`,
  )
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s*\\{[^}]*padding(?:-[a-z]+)?:`, "s"),
    `${label} Stat Strip must inherit padding from the shared ag-stat-strip style`,
  )
}

for (const [source, className, label] of [
  [trace, "trace-stat-card", "Trace"],
  [agentOSControl, "agentos-summary-chip", "AgentOS"],
]) {
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}::before`, "s"),
    `${label} Stat Chips must not add page-specific tone bars`,
  )
}

assert.doesNotMatch(
  dashboard,
  /class="ag-stat-strip mt-3[^"]*grid/,
  "Dashboard Stat Strip must not override the shared compact strip with grid utilities",
)

assert.match(
  agentOSControl,
  /class="scheduler-enabled-field"[\s\S]*?<el-switch/,
  "Scheduler create form enabled switch must use a stable field wrapper",
)

assert.match(
  useApi,
  /listApprovals/,
  "AgentOS API composable must expose approval listing",
)

assert.match(
  useApi,
  /resolveApproval/,
  "AgentOS API composable must expose approval resolve",
)

for (const typeName of [
  "AgentEvalType",
  "AgentEvalSuite",
  "AgentEvalCase",
  "AgentEvalSuiteRun",
  "AgentEvalCaseRun",
  "AgentEvalAgnoRun",
  "AgentEvalTrendResponse",
  "AgentEvalFailureResponse",
  "AgentEvalSuiteCreateRequest",
  "AgentEvalCaseCreateRequest",
]) {
  assert.match(
    typesSource,
    new RegExp(`(?:interface|type)\\s+${typeName}\\b`),
    `Agent Eval frontend type must be exported: ${typeName}`,
  )
}

assert.match(
  useApi,
  /agentEvalsRequestFailed/,
  "Agent Eval API composable must expose a fallback key",
)

assert.match(
  useApi,
  /function useAgentEvalsApi\(\)/,
  "Agent Eval API composable must expose useAgentEvalsApi",
)

for (const methodName of [
  "listSuites",
  "createSuite",
  "listCases",
  "createCase",
  "runSuite",
  "runCase",
  "replayCaseRun",
  "listAgnoRuns",
  "getAgnoRun",
  "getTrends",
  "listFailures",
]) {
  assert.match(
    useApi,
    new RegExp(`\\b${methodName}\\b`),
    `Agent Eval API composable must expose ${methodName}`,
  )
}

for (const apiPath of [
  "/agent-evals/suites",
  "/agent-evals/cases",
  "/agent-evals/agno-runs",
  "/agent-evals/trends",
  "/agent-evals/failures",
]) {
  assert.match(
    useApi,
    new RegExp(apiPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `Agent Eval API composable must call ${apiPath}`,
  )
}

assert.match(
  agentOSControl,
  /approvals-workbench/,
  "AgentOS approvals module must render a dedicated approvals workbench",
)

assert.match(
  agentOSControl,
  /resolveSelectedApproval\("approved"\)/,
  "AgentOS approvals module must bind an approve action",
)

assert.match(
  agentOSControl,
  /resolveSelectedApproval\("rejected"\)/,
  "AgentOS approvals module must bind a reject action",
)

assert.match(
  agentOSControl,
  /\.scheduler-enabled-field\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden/s,
  "Scheduler enabled switch field must not overlap adjacent form controls",
)

assert.match(
  agentOSControl,
  /\.scheduler-enabled-field\s+:deep\(\.el-switch__core\)\s*\{[^}]*min-width:\s*40px/s,
  "Scheduler enabled switch core must preserve the Element Plus switch track width",
)

assert.doesNotMatch(
  app,
  /\.ag-stat-chip\.ag-stat-chip\s*\{/,
  "App shell must not override the shared compact Stat Chip surface",
)

assert.match(
  appStyle,
  /html:not\(\.dark\)\s+:where\(\.ag-stat-chip\)/,
  "Light mode must style all shared Stat Chips through ag-stat-chip",
)

assert.match(
  trace,
  /useI18n\(\)/,
  "Trace page must read user-facing copy from vue-i18n",
)

for (const hardcodedSkillsCopy of [
  "后端上传接口当前为占位，暂不可用",
  "上传",
  "刷新",
  "加载中…",
  "未检测到任何 Skill",
  "脚本",
  "暂无描述",
  "收起脚本",
  "查看 ",
  "已启用",
  "已禁用",
  "加载 Skills 列表失败",
  "切换 Skill 状态失败",
]) {
  assert.equal(
    skills.includes(hardcodedSkillsCopy),
    false,
    `Skills page must not hardcode copy: ${hardcodedSkillsCopy}`,
  )
}

for (const oldSkillsColor of ["#0969DA", "#D0D7DE", "#30363D", "#0D1117", "rounded-xl"]) {
  assert.equal(
    skills.includes(oldSkillsColor),
    false,
    `Skills page must not keep old GitHub-style styling token: ${oldSkillsColor}`,
  )
}

for (const hardcodedMcpCopy of [
  "服务能力",
  "访问 Token",
  "签发访问 Token",
  "Token 名称，例如 AgentOS",
  "仅显示一次，请立即复制",
  "暂无访问 Token",
  "名称，例如 CVE Hunter",
  "能力描述",
  "接入说明",
  "管理入口",
  "加载 MCP 数据失败",
  "生成 Token 失败",
  "删除 Token 失败",
  "FastMCP",
  "Client URL",
]) {
  assert.equal(
    mcp.includes(hardcodedMcpCopy),
    false,
    `MCP page must not hardcode copy: ${hardcodedMcpCopy}`,
  )
}

for (const hardcodedTraceCopy of [
  "刷新 Trace 队列",
  "选择一次 Agent Run",
  "重新拉取",
  "按父子关系查看 Agent、LLM、Tool 与 Hook",
  "暂无 spans",
  "点击 Span 查看详情",
  "错误信息",
  "复制 JSON",
  "开始偏移",
  "加载 traces 失败",
]) {
  assert.equal(
    trace.includes(hardcodedTraceCopy),
    false,
    `Trace page must not hardcode copy: ${hardcodedTraceCopy}`,
  )
}

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
  "components/Assets.vue",
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
  existsSync(repoPath("api/routes/collect.py")),
  true,
  "backend route filename must align with Collect",
)

assert.equal(
  existsSync(repoPath("api/routes/trace.py")),
  true,
  "backend route filename must align with Trace",
)

for (const oldRoute of ["api/routes/asset.py", "api/routes/assets.py", "api/routes/url2md.py", "api/routes/traces.py"]) {
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
  trace,
  /trace-session-panel/,
  "Trace page must expose a session filtering panel",
)

assert.equal(
  app.includes("ag-trace-queue-panel"),
  false,
  "Trace Queue sidebar panel must be removed; Trace observation is reached through Session filtering",
)

assert.equal(
  app.includes("toggleTraceQueue"),
  false,
  "Trace nav item must not keep a queue expand/collapse action",
)

assert.match(
  app,
  /securityDataNavItems/,
  "CVE and Collect must be rendered as a separate sidebar group",
)

assert.match(
  settings,
  /settings\.tabs\.navigation/,
  "Settings must include a navigation configuration tab",
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

assert.equal(
  /#[0-9A-Fa-f]{3,8}/.test(dashboard),
  false,
  "Dashboard page must use shared design tokens instead of hardcoded hex colors",
)

for (const [pageName, pageSource] of [
  ["CVE", cve],
  ["Collect", collect],
  ["Settings", settings],
  ["Knowledge", knowledge],
]) {
  assert.equal(
    /#[0-9A-Fa-f]{3,8}\b|rgba\(/.test(pageSource),
    false,
    `${pageName} page must use shared design tokens instead of hardcoded colors`,
  )
}

assert.match(
  dashboard,
  /useI18n\(\)/,
  "Dashboard page must read user-facing copy from vue-i18n",
)

assert.equal(
  dashboard.includes("situation-core"),
  false,
  "Dashboard must avoid the old oversized header icon block",
)

for (const hardcodedDashboardCopy of [
  "安全运营态势总览",
  "漏洞、响应链路、异常态势与 Agent 负载",
  "最近 24 小时",
  "最近 7 天",
  "最近 30 天",
  "刷新",
  "Trace 延迟趋势",
  "小时运行热力",
  "Agent 负载雷达",
  "Span / Error 分布",
  "暂无 Span 分布数据",
  "最近研判链路",
  "会话 ",
  "运行 ",
  "暂无 Agent 运行数据",
  "状态分布",
  "Agent 响应负载",
  "暂无 Agent 维度数据",
  "异常响应",
  "最近样本未发现异常运行",
  "运行样本",
  "当前样本",
  "响应成功率",
  "按最近样本计算",
  "异常运行",
  "状态 ERROR 或含错误 Span",
  "平均耗时",
]) {
  assert.equal(
    dashboard.includes(hardcodedDashboardCopy),
    false,
    `Dashboard page must not hardcode copy: ${hardcodedDashboardCopy}`,
  )
}

assert.match(
  authClientSource,
  /fallbacks/,
  "auth client must accept caller-provided localized fallback messages",
)

for (const hardcodedAuthClientCopy of [
  "当前环境不支持 Fetch API",
  "登录失败",
  "注册失败",
  "获取当前用户失败",
  "获取 OAuth Provider 失败",
  "获取 OAuth 授权地址失败",
  "OAuth Provider 未返回授权地址",
]) {
  assert.equal(
    authClientSource.includes(hardcodedAuthClientCopy),
    false,
    `auth client must not hardcode localized error copy: ${hardcodedAuthClientCopy}`,
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

assert.match(
  knowledge,
  /knowledge-workflow-shell/,
  "Knowledge page must be reorganized as an AI workspace workflow shell",
)

for (const bulkyKnowledgeHeaderClass of [
  "knowledge-hero",
  "knowledge-eyebrow",
  "knowledge-hero-actions",
]) {
  assert.equal(
    knowledge.includes(bulkyKnowledgeHeaderClass),
    false,
    `Knowledge page must remove bulky top hero element: ${bulkyKnowledgeHeaderClass}`,
  )
}

assert.match(
  knowledge,
  /knowledge-stat-strip ag-stat-strip/,
  "Knowledge page must expose status in the shared compact Stat Strip",
)

assert.match(
  knowledge,
  /knowledge-stat-chip ag-stat-chip/,
  "Knowledge status items must use the shared Stat Chip surface",
)

assert.match(
  knowledge,
  /<div v-for="card in statisticsCards"[^>]*class="knowledge-stat-chip ag-stat-chip"/,
  "Knowledge status metrics must render as compact stat values, not list/article items",
)

const knowledgeStatisticsCardsBlock = knowledge.match(/const statisticsCards = computed\(\(\) => \[([\s\S]*?)\]\)/)?.[1] ?? ""
assert.equal(
  [...knowledgeStatisticsCardsBlock.matchAll(/label:\s*t\("knowledge\.stats\./g)].length,
  4,
  "Knowledge status strip must show only the four primary statistics",
)

assert.equal(
  knowledge.includes("knowledge-stat-dashboard"),
  false,
  "Knowledge page must not use a separate statistics dashboard pattern for Stat Chips",
)

assertNoPillStatChip(
  knowledge,
  "knowledge-stat-chip",
  "Knowledge Stat Chips must use the shared 8px rectangular chip shape, not pill styling",
)

assert.doesNotMatch(
  knowledge,
  /\.knowledge-stat-chip\s*\{[^}]*flex:\s*1\s+1/s,
  "Knowledge Stat Chips must not stretch into dashboard cards",
)

assert.doesNotMatch(
  knowledge,
  /\.knowledge-stat-chip\s+(span|small|strong)\s*\{/,
  "Knowledge Stat Chips must inherit label and value typography from the shared ag-stat-chip style",
)

assert.doesNotMatch(
  knowledge,
  /\.knowledge-stat-strip\s*\{[^}]*display:\s*(flex|grid)/s,
  "Knowledge Stat Strip must inherit layout from the shared ag-stat-strip style",
)

assert.doesNotMatch(
  knowledge,
  /\.knowledge-stat-chip\s*\{[^}]*flex-basis/s,
  "Knowledge Stat Chips must not override the shared compact chip width",
)

assert.match(
  knowledge,
  /knowledge-upload-pipeline/,
  "Knowledge upload area must show the RAG ingestion pipeline",
)

assert.match(
  memoryControl,
  /memory-priority-strip ag-stat-strip/,
  "Memory priority metrics must use the shared compact Stat Strip",
)

assert.match(
  memoryControl,
  /class="memory-priority-card ag-stat-chip"/,
  "Memory priority metrics must use the shared Stat Chip surface",
)

assert.doesNotMatch(
  memoryControl,
  /\.memory-priority-card\s+(span|small|strong)\s*\{/,
  "Memory priority Stat Chips must inherit label and value typography from the shared ag-stat-chip style",
)

assert.doesNotMatch(
  memoryControl,
  /\.memory-priority-card\s*\{[^}]*min-height:/s,
  "Memory priority Stat Chips must inherit compact sizing from the shared ag-stat-chip style",
)

assert.doesNotMatch(
  memoryControl,
  /\.memory-priority-card::before/s,
  "Memory priority metrics must not add local tone bars that make Stat Chip backgrounds look inconsistent",
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

assert.doesNotMatch(
  knowledge,
  /<el-table[\s\S]*fixed=/,
  "Knowledge document management must not use fixed Element Plus table columns that overflow narrow shells",
)

assert.match(
  knowledge,
  /document-table.*role="table"/,
  "Knowledge document management must use the custom responsive document table surface",
)

assert.match(
  knowledge,
  /document-action-buttons/,
  "Knowledge document actions must stay grouped in a bounded icon button row",
)

assert.match(
  knowledge,
  /@media\s*\(max-width:\s*1120px\)[\s\S]*\.document-row\s*\{[\s\S]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  "Knowledge document rows must collapse into a responsive card grid before they can overflow the shell",
)

assert.match(
  knowledge,
  /useI18n\(\)/,
  "Knowledge page must read user-facing copy from vue-i18n",
)

for (const hardcodedKnowledgeCopy of [
  "RAG Workspace",
  "Upload, parse, embed",
  "刷新",
  "清空",
  "上传知识",
  "Reader 默认自动识别",
  "文件上传",
  "文本导入",
  "服务端路径",
  "拖入文件或",
  "选择文件",
  "标题",
  "来源",
  "写入选中文件",
  "检索验证",
  "输入检索问题",
  "正在检索知识库",
  "暂无命中",
  "文档管理",
  "搜索文档",
  "知识文档列表",
  "后端重建接口待接入",
  "RAG 参数",
  "Document Name",
  "Embedding Status",
  "Document Preview",
  "Document Metadata",
  "加载知识库失败",
  "知识库已更新",
  "请选择文件",
  "删除知识文档",
  "清空知识库",
  "检索问题不能为空",
]) {
  assert.equal(
    knowledge.includes(hardcodedKnowledgeCopy),
    false,
    `Knowledge page must not hardcode copy: ${hardcodedKnowledgeCopy}`,
  )
}

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

assert.equal(
  trace.includes("trace-hero"),
  false,
  "Trace page must remove the bulky duplicate hero header",
)

assert.match(
  trace,
  /trace-toolbar/,
  "Trace page must expose a compact filter toolbar instead of a hero header",
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

assert.match(
  agentOSControl,
  /useI18n\(\)/,
  "AgentOS control pages must read user-facing copy from vue-i18n",
)

for (const bulkyAgentOSHeaderClass of [
  "agentos-head",
  "agentos-mark",
  "agentos-title",
]) {
  assert.equal(
    agentOSControl.includes(bulkyAgentOSHeaderClass),
    false,
    `AgentOS control pages must remove bulky top header element: ${bulkyAgentOSHeaderClass}`,
  )
}

for (const hardcodedAgentOSCopy of [
  "加载控制面状态",
  "暂无记录",
  "Agno docs MCP 对齐状态",
  "评测 registry 已就绪，等待接入评测运行。",
  "审批 registry 已就绪，当前没有待处理请求。",
  "调度 registry 已就绪，当前没有计划任务。",
  "当前模块还没有可展示的运行记录。",
]) {
  assert.equal(
    agentOSControl.includes(hardcodedAgentOSCopy),
    false,
    `AgentOS control page must not hardcode copy: ${hardcodedAgentOSCopy}`,
  )
}

assert.match(
  collect,
  /useI18n\(\)/,
  "Collect page must read user-facing copy from vue-i18n",
)

assert.match(
  collect,
  /useShellStore\(\)/,
  "Collect page must use the shared shell store for responsive state",
)

for (const hardcodedCollectCopy of [
  "请输入要解析的网址",
  "解析",
  "清空",
  "Markdown 文本",
  "渲染预览",
  "解析后会在这里显示 Markdown 文本",
  "输入网址并点击解析",
  "支持将网页内容转换为 Markdown 格式",
  "已复制到剪贴板",
  "复制失败",
  "无效网址",
  "请输入一个有效的 URL",
  "解析成功",
  "已获取 Markdown 内容",
  "未返回内容",
  "后端未返回 Markdown 文本",
  "解析失败",
  "网络或后端错误",
]) {
  assert.equal(
    collect.includes(hardcodedCollectCopy),
    false,
    `Collect page must not hardcode copy: ${hardcodedCollectCopy}`,
  )
}

assert.doesNotMatch(
  app,
  /shell\.nav\.assets|components\/Assets\.vue|id:\s*["']assets["']/,
  "Assets navigation and component mapping must be removed",
)

assert.doesNotMatch(
  useApi,
  /useAssetApi|\/asset\/search|AssetSearch/,
  "Asset search API client must be removed from the frontend",
)

assert.match(
  cve,
  /useI18n\(\)/,
  "CVE page must read user-facing copy from vue-i18n",
)

assert.match(
  cve,
  /useShellStore\(\)/,
  "CVE page must use the shared shell store for responsive state",
)

for (const hardcodedCveCopy of [
  "输入 CVE 编号或关键字",
  "数据来源",
  "全部",
  "搜索",
  "更新数据库",
  "CVE 编号",
  "来源",
  "链接",
  "描述",
  "展开",
  "收起",
  "发现日期",
  "条结果",
  "已按来源筛选",
  "未找到结果",
  "未找到符合条件的 CVE 记录",
  "请尝试调整搜索条件",
  "等待检索条件",
  "组件名或漏洞关键词",
  "更新会触发后端 CVE 数据同步任务",
  "更新 CVE 数据库",
  "更新成功",
  "更新失败",
  "未知错误",
  "网络错误",
]) {
  assert.equal(
    cve.includes(hardcodedCveCopy),
    false,
    `CVE page must not hardcode copy: ${hardcodedCveCopy}`,
  )
}

assert.match(
  settings,
  /useI18n\(\)/,
  "Settings page must read user-facing copy from vue-i18n",
)

assert.match(
  settings,
  /hasPermission\("settings:write"\)/,
  "Settings page must check write permission before allowing configuration changes",
)

assert.match(
  settings,
  /:disabled="!canWriteSettings/,
  "Settings page must disable configuration controls for read-only users",
)

assert.match(
  settings,
  /required-mark/,
  "Settings page must visibly mark required model and runtime parameters",
)

assert.match(
  settings,
  /testModelConnection/,
  "Settings page must expose a model connectivity test action",
)

assert.match(
  settings,
  /settings\.actions\.testConnection/,
  "Settings model connectivity test button must use i18n copy",
)

assert.match(
  useApi,
  /\/models\/test/,
  "Settings API must call the model connectivity test endpoint",
)

assert.match(
  useApi,
  /modelsTestFailed/,
  "Settings API must expose a localized model connectivity fallback",
)

for (const hardcodedSettingsCopy of [
  "系统配置",
  "运行时参数与 Agent 模型路由配置",
  "新增模型",
  "保存",
  "模型路由",
  "选择 Agent 默认模型",
  "默认模型",
  "未命名模型",
  "待配置",
  "自定义模型参数",
  "启用",
  "禁用",
  "显示名称",
  "例如 DeepSeek V4 Flash",
  "说明",
  "用于低延迟研判",
  "非 LLM 的平台参数",
  "敏感字段返回时会脱敏",
  "飞书 Webhook URL",
  "飞书机器人通知",
  "自定义模型",
  "加载配置失败",
  "请先补全必填参数",
  "测试模型连接失败",
  "模型连接正常",
  "模型连接失败",
  "确定要删除这个模型配置吗",
  "删除模型",
  "删除失败",
  "配置已保存",
  "保存配置失败",
  "Builtin",
  "Default",
  "Model ID",
  "Base URL",
  "API Key",
  "MCP Server URL",
  "MCP Access Token",
  "YOUR_ACCESS_TOKEN",
  "https://api.example.com/v1",
  "sk-...",
]) {
  assert.equal(
    settings.includes(hardcodedSettingsCopy),
    false,
    `Settings page must not hardcode copy: ${hardcodedSettingsCopy}`,
  )
}

for (const pageWithSharedResponsiveState of [
  ["CVE", cve],
  ["Collect", collect],
]) {
  assert.match(
    pageWithSharedResponsiveState[1],
    /useSecurityDataStore\(\)/,
    `${pageWithSharedResponsiveState[0]} page must keep workflow state in the shared security data store`,
  )
  assert.equal(
    pageWithSharedResponsiveState[1].includes("checkMobile"),
    false,
    `${pageWithSharedResponsiveState[0]} page must not keep page-local mobile resize state`,
  )
  assert.equal(
    /addEventListener\((["'])resize\1/.test(pageWithSharedResponsiveState[1]),
    false,
    `${pageWithSharedResponsiveState[0]} page must not attach its own resize listener`,
  )
}
