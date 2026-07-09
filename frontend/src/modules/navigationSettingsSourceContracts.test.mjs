import assert from "node:assert/strict"
import {
  agentEvals,
  removedAgentOsControlSource,
  apiClient,
  app,
  appStyle,
  assertNoPillStatChip,
  assertTextOrder,
  authScreen,
  authStoreSource,
  chat,
  clipboard,
  collect,
  cve,
  dashboard,
  designTokens,
  existsSync,
  hasRoleScope,
  hasUserScope,
  i18n,
  knowledge,
  mcp,
  memoryControl,
  readOptionalSource,
  readSource,
  scopes,
  settings,
  shellBrand,
  shellNavigation,
  skills,
  sourcePath,
  trace,
  traceQueryToolbar,
  traceSessionPanel,
  traceWorkbenchSource,
  typesSource,
  useApiCore,
  useChatApiSource,
  useMemoryControlApiSource,
  useTraceSessionControllerSource,
  useTraceApiSource,
  userRole,
  visibilityTabs,
  workflow,
} from "./testSource.mjs"

const settingsRuntimePanel = readOptionalSource("components/settings/SettingsRuntimePanel.vue")
const settingsModelPanel = readOptionalSource("components/settings/SettingsModelPanel.vue")
const settingsNavigationPanel = readOptionalSource("components/settings/SettingsNavigationPanel.vue")
const useSettingsNavigationLayoutSource = readOptionalSource("composables/useSettingsNavigationLayout.ts")
const settingsModularSource = [
  settings,
  settingsRuntimePanel,
  settingsModelPanel,
  settingsNavigationPanel,
  useSettingsNavigationLayoutSource,
].join("\n")
const chatMessageList = readOptionalSource("components/chat/ChatMessageList.vue")
const chatMessageCard = readOptionalSource("components/chat/ChatMessageCard.vue")
const chatComposer = readOptionalSource("components/chat/ChatComposer.vue")
const chatModelSelect = readOptionalSource("components/chat/ChatModelSelect.vue")
const useChatScrollStateSource = readOptionalSource("composables/useChatScrollState.ts")
const useChatMarkdownRendererSource = readOptionalSource("composables/useChatMarkdownRenderer.ts")
const chatModularSource = [
  chat,
  chatMessageList,
  chatMessageCard,
  chatComposer,
  chatModelSelect,
  useChatScrollStateSource,
  useChatMarkdownRendererSource,
].join("\n")

assert.equal(
  removedAgentOsControlSource,
  "",
  "removed aggregate parent must stay absent in favor of direct page components",
)

assert.equal(
  removedAgentOsControlSource.includes("page-notes"),
  false,
  "page workbenches must avoid the previous notes sidebar",
)

assert.equal(
  removedAgentOsControlSource.includes("page-note-strip"),
  false,
  "page workbenches must not render implementation note chips",
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
  /canAccess:\s*canAccessNav/,
  "App shell must pass scope filtering into persisted navigation group building",
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
  "sidebar navigation order must keep the runtime pages grouped after core operations",
)

for (const runtimePageLabel of [
  't("shell.nav.memory.label")',
  't("shell.nav.evaluation.label")',
  't("shell.nav.approvals.label")',
  't("shell.nav.scheduler.label")',
]) {
  assert.match(
    app,
    new RegExp(runtimePageLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `sidebar must include missing runtime page ${runtimePageLabel}`,
  )
}

assert.equal(
  existsSync(sourcePath("components/Chat.vue")),
  true,
  "Chat component file must align with the Chat nav label",
)

for (const expectedChatModule of [
  "components/chat/ChatMessageList.vue",
  "components/chat/ChatMessageCard.vue",
  "components/chat/ChatComposer.vue",
  "components/chat/ChatModelSelect.vue",
  "composables/useChatScrollState.ts",
  "composables/useChatMarkdownRenderer.ts",
]) {
  assert.equal(
    existsSync(sourcePath(expectedChatModule)),
    true,
    `Chat modularization must provide ${expectedChatModule}`,
  )
}

for (const chatShellDependency of [
  "ChatMessageList",
  "ChatComposer",
  "useChatScrollState",
  "useChatMarkdownRenderer",
]) {
  assert.match(
    chat,
    new RegExp(chatShellDependency),
    `Chat.vue must orchestrate through ${chatShellDependency}`,
  )
}

assert.doesNotMatch(
  chat,
  /import\s+MarkdownIt\s+from\s+["']markdown-it["']|from\s+["']highlight\.js["']/,
  "Chat.vue must not own MarkdownIt/highlight setup after moving assistant rendering to child/composable contracts",
)

assert.doesNotMatch(
  chat,
  /const\s+(pendingNewMessages|showScrollToBottom|showBackToTop)\s*=\s*ref\(/,
  "Chat.vue must delegate scroll visibility and new-message counters to useChatScrollState",
)

assert.match(
  chatMessageList,
  /ChatMessageCard/,
  "ChatMessageList must render messages through ChatMessageCard",
)

assert.match(
  chatMessageCard,
  /MarkdownViewer/,
  "ChatMessageCard must render assistant Markdown through the shared MarkdownViewer primitive",
)

assert.match(
  chatComposer,
  /ChatModelSelect/,
  "ChatComposer must delegate model choice to ChatModelSelect",
)

assert.match(
  useChatMarkdownRendererSource,
  /parseAssistantMessage/,
  "useChatMarkdownRenderer must own assistant thinking/source/tool extraction",
)

assert.match(
  useChatMarkdownRendererSource,
  /enhanceRenderedMarkdown/,
  "useChatMarkdownRenderer must own code-copy and image-zoom enhancement hooks",
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
    chatModularSource,
    new RegExp(chatHook),
    `Chat modular components/composables must expose ${chatHook} interaction support`,
  )
}

assert.match(
  settings,
  /SettingsRuntimePanel/,
  "Settings shell must delegate runtime parameter rendering to SettingsRuntimePanel",
)

assert.match(
  settings,
  /SettingsModelPanel/,
  "Settings shell must delegate model routing rendering to SettingsModelPanel",
)

assert.match(
  settings,
  /SettingsNavigationPanel/,
  "Settings shell must delegate navigation editing rendering to SettingsNavigationPanel",
)

assert.match(
  settings,
  /useSettingsNavigationLayout/,
  "Settings shell must use the navigation layout composable instead of owning drag/drop internals",
)

assert.match(
  settingsRuntimePanel,
  /SectionHeader/,
  "SettingsRuntimePanel must use the shared SectionHeader primitive",
)

assert.match(
  settingsModelPanel,
  /SectionHeader/,
  "SettingsModelPanel must use the shared SectionHeader primitive",
)

assert.match(
  settingsModelPanel,
  /DataChip|StatusDot/,
  "SettingsModelPanel must use shared chip/status primitives for model metadata",
)

assert.match(
  settingsNavigationPanel,
  /SectionHeader/,
  "SettingsNavigationPanel must use the shared SectionHeader primitive",
)

assert.match(
  settingsNavigationPanel,
  /DataChip/,
  "SettingsNavigationPanel must use the shared DataChip primitive for group counts",
)

assert.match(
  settingsModularSource,
  /navigationLayout/,
  "Settings navigation editor must persist user-controlled layout, not only tags",
)

assert.match(
  settingsNavigationPanel,
  /:draggable="canWriteSettings"/,
  "Settings navigation items must be draggable when the user can write settings",
)

assert.match(
  useSettingsNavigationLayoutSource,
  /moveNavigationItem/,
  "Settings navigation editor must expose keyboard/button movement controls through the composable",
)

assert.match(
  useSettingsNavigationLayoutSource,
  /items:\s*\["home",\s*"dashboard",\s*"chat",\s*"workflow"\]/,
  "Settings navigation defaults must serialize real shell nav ids instead of display labels",
)

assert.doesNotMatch(
  useSettingsNavigationLayoutSource,
  /items:\s*\["Home",\s*"Dashboard",\s*"Chat",\s*"Workflow"\]/,
  "Settings navigation defaults must not persist old display labels as ids",
)

assert.doesNotMatch(
  settings,
  /settings-toolbar/,
  "Settings must not keep a standalone title/description toolbar after moving actions into concrete page areas",
)

assert.doesNotMatch(
  settings,
  /t\('settings\.title'\)|t\("settings\.title"\)|t\('settings\.description'\)|t\("settings\.description"\)/,
  "Settings must not render the removed title and subtitle copy",
)

assert.match(
  settings,
  /ag-settings-tabs-head/,
  "Settings save action must live beside the tab switcher as the page-level commit action",
)

assert.match(
  settingsModelPanel,
  /ag-settings-model-actions/,
  "Settings add-model action must live in the model routing section header",
)

assert.match(
  settingsModelPanel,
  /<SectionHeader[\s\S]*class="flex-wrap"/,
  "Settings model section header must wrap actions on narrow screens",
)

assert.match(
  settingsModelPanel,
  /ag-settings-model-actions flex w-full flex-col/,
  "Settings model actions must stack controls on narrow screens before controls can overflow",
)

assert.match(
  settingsModelPanel,
  /class="w-\[240px\] max-w-full"/,
  "Settings default model select must keep readable width on narrow screens",
)

assert.match(
  settingsModelPanel,
  /class="w-\[240px\] max-w-full cursor-pointer sm:w-auto"/,
  "Settings add model button must keep readable width on narrow screens",
)

assert.match(
  app,
  /sidebarNavGroups/,
  "App shell sidebar must render from the normalized user navigation layout",
)

assert.match(
  app,
  /fetchSettings/,
  "App shell must load persisted Settings navigation layout",
)

assert.match(
  app,
  /NAV_TAGS/,
  "App shell must consume the Settings NAV_TAGS payload",
)

assert.match(
  settingsModularSource,
  /agno-aios-navigation-layout-change/,
  "Settings must notify the app shell after saving navigation layout changes",
)

assert.match(
  app,
  /addEventListener\("agno-aios-navigation-layout-change"/,
  "App shell must listen for Settings navigation layout changes without requiring a refresh",
)

assert.match(
  app,
  /removeEventListener\("agno-aios-navigation-layout-change"/,
  "App shell must clean up the Settings navigation layout listener",
)

assert.match(
  useSettingsNavigationLayoutSource,
  /beforeItemId === draggedNavigationItem\.value\.itemId/,
  "Settings drag sorting must ignore dropping an item onto itself",
)

assert.match(
  useSettingsNavigationLayoutSource,
  /targetIndex -= 1/,
  "Settings drag sorting must keep the intended insertion point when moving down inside one group",
)

for (const oldSettingsSelector of [
  "settings-section",
  "settings-section-head",
  "model-card",
  "runtime-card",
  "model-badge",
  "navigation-group-card",
  "navigation-order-item",
]) {
  assert.equal(
    settings.includes(oldSettingsSelector),
    false,
    `Settings shell must not keep old page-local selector ${oldSettingsSelector}`,
  )
}

assert.equal(
  settings.includes("settings.navigation.note"),
  false,
  "Settings navigation editor must not render the bottom drag instruction note",
)

for (const localeSource of [readSource("i18n/locales/en-US.ts"), readSource("i18n/locales/zh-CN.ts")]) {
  assert.equal(
    localeSource.includes("可拖拽项目跨分组排版，也可以用箭头按钮精确调整顺序。"),
    false,
    "Settings navigation instruction note copy must be removed from locale messages",
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
  useChatApiSource,
  /archiveSession/,
  "Chat history API must expose archiveSession instead of permanent deletion for sidebar delete",
)

assert.match(
  useMemoryControlApiSource,
  /deleteMemory\s*=\s*async/,
  "Memory API must expose deleteMemory for Agno user memories",
)

assert.match(
  useMemoryControlApiSource,
  /apiFetch\(`\/memory\/\$\{encodeURIComponent\(memoryId\)\}/,
  "deleteMemory must call the authenticated Memory delete endpoint",
)

assert.match(
  useMemoryControlApiSource,
  /updateMemory\s*=\s*async/,
  "Memory API must expose updateMemory for Agno user memories",
)

assert.match(
  useMemoryControlApiSource,
  /method:\s*'PATCH'/,
  "updateMemory must patch the authenticated Memory endpoint",
)

assert.doesNotMatch(
  useMemoryControlApiSource,
  /pruneMemory|\/os\/memory\/prune/,
  "Memory pruning API must not remain exposed after pruning removal",
)

assert.match(
  apiClient,
  /Authorization.*Bearer/,
  "shared API client must attach Bearer auth tokens",
)

assert.equal(
  /user_id:\s*userId/.test(useChatApiSource),
  false,
  "Chat API must not send frontend-provided user_id",
)

assert.equal(
  /archiveSession\s*=\s*async\s*\([^)]*userId/.test(useChatApiSource),
  false,
  "archiveSession must not accept frontend-provided user id",
)

for (const traceParam of ["session_id", "run_id", "agent_id", "team_id", "workflow_id", "user_id"]) {
  assert.match(
    useTraceApiSource,
    new RegExp(`qs\\.set\\('${traceParam}'`),
    `Trace API must preserve ${traceParam} query parameter when provided`,
  )
}

for (const sessionTraceParam of ["session_id", "user_id"]) {
  assert.match(
    traceWorkbenchSource,
    new RegExp(`${sessionTraceParam}:\\s*session\\.${sessionTraceParam === "session_id" ? "session_id" : "user_id"}`),
    `Trace workbench must pass selected session ${sessionTraceParam} into listTraces params`,
  )
}

for (const traceInteraction of ["@keyup.enter=\"emit('refresh')\"", "@click=\"emit('refresh')\""]) {
  assert.match(
    traceQueryToolbar,
    new RegExp(traceInteraction.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `Trace filters must keep manual refresh interaction: ${traceInteraction}`,
  )
}

assert.match(
  trace,
  /useTraceSessionController/,
  "Trace page must delegate session and trace loading flows to a composable",
)

for (const traceControllerFlow of ["refresh", "loadSessionTraces", "selectTraceById", "refreshRuns"]) {
  assert.match(
    useTraceSessionControllerSource,
    new RegExp(`const ${traceControllerFlow}\\s*=\\s*async`),
    `Trace session controller must own async flow: ${traceControllerFlow}`,
  )
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${traceControllerFlow}\\s*=\\s*async`),
    `Trace page must not inline async flow: ${traceControllerFlow}`,
  )
}

assert.match(
  useApiCore,
  /export const cleanParam =/,
  "Trace API must normalize query parameters before appending them to URLSearchParams",
)

assert.equal(
  /\p{Script=Han}/u.test([useApiCore, useChatApiSource, useMemoryControlApiSource, useTraceApiSource].join("\n")),
  false,
  "API composables must not hardcode localized Chinese fallback copy",
)

assert.match(
  useTraceApiSource,
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

for (const traceToolbarFilterField of [
  "sessionFilters.sessionId",
  "sessionFilters.userId",
  "sessionFilters.keyword",
  "sessionFilters.status",
]) {
  assert.match(
    traceQueryToolbar,
    new RegExp(traceToolbarFilterField.replace(".", "\\.")),
    `Trace toolbar must expose filter field: ${traceToolbarFilterField}`,
  )
}

for (const traceFilterHook of [
  "filteredSessions",
  "pagedSessions",
  "SESSION_PAGE_SIZE",
  "selectSession",
  "scheduleFilterRefresh",
]) {
  assert.match(
    trace,
    new RegExp(traceFilterHook.replace(".", "\\.")),
    `Trace filters must auto-refresh when ${traceFilterHook} changes`,
  )
}

assert.match(
  traceSessionPanel,
  /v-for="session in pagedSessions"/,
  "Trace Sessions column must render paginated sessions instead of the full filtered list",
)

assert.match(
  trace,
  /const SESSION_PAGE_SIZE = 10/,
  "Trace Sessions column must default to 10 rows per page",
)

assert.match(
  traceSessionPanel,
  /:rows="sessionPageSize"/,
  "Trace Sessions loading skeleton must match the default session page size",
)

assert.match(
  traceSessionPanel,
  /trace-session-pagination/,
  "Trace Sessions column must expose pagination controls",
)

for (const removedTraceIntroCopy of [
  "按 Session ID、User ID 或预览内容定位对话，再查看对应 Trace。",
  "默认按 runs 查看，可用 Session ID、Run ID、Agent、Team、Workflow 和状态筛选。",
  "Filter sessions on the left to load the corresponding trace observation here.",
  "selectSessionDescription",
  "selectTraceDescription",
  "selectSpanDescription",
]) {
  assert.equal(
    trace.includes(removedTraceIntroCopy),
    false,
    `Trace page must not render explanatory panel copy: ${removedTraceIntroCopy}`,
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
  /skill-list-item/,
  "Skills rows must use the shared tokenized list item surface",
)

assert.match(
  skills,
  /skill-detail-panel ag-content-panel/,
  "Skills metadata must use the shared tokenized panel surface",
)

assert.match(
  skills,
  /skill-toolbar ag-content-panel/,
  "Skills page must summarize total, enabled, and script counts in the business toolbar",
)

assert.match(
  skills,
  /<MetricChip v-for="metric in summaryMetrics"/,
  "Skills summary items must render through the shared metric chip primitive",
)

assert.match(
  skills,
  /skill-toolbar-action/,
  "Skills upload action must stay in the Skills toolbar",
)

assertNoPillStatChip(
  skills,
  "skill-context-chip",
  "Skills toolbar context chips must use the 8px rectangular shape, not pill styling",
)

assert.doesNotMatch(
  skills,
  /skill-summary-strip|skill-summary-chip|ag-stat-strip|ag-stat-chip/,
  "Skills must not use the global stat-strip pattern",
)

assert.doesNotMatch(
  skills,
  /skills-action-bar ag-content-panel[\s\S]{0,800}skill-summary-strip|skills-header ag-content-panel/,
  "Skills must not keep the old action toolbar or header pattern",
)

assert.match(
  skills,
  /skills-console ag-page-flow/,
  "Skills page must use the shared page flow instead of a local full-height surface",
)

assert.match(
  skills,
  /<StatusChip class="w-11"/,
  "Skills page must use a compact shared status chip for enabled state",
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
