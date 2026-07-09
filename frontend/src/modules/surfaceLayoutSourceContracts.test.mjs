import assert from "node:assert/strict"
import {
  agentEvals,
  approvalsWorkbench,
  removedAgentOsControlSource,
  pageWorkbenchStyle,
  removedAgentOsLedgerSource,
  schedulerWorkbench,
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
  knowledgeIngestDrawer,
  knowledgeMetadataPanel,
  knowledgeRetrievalPlayground,
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
  traceRunsPanel,
  typesSource,
  useApprovalsApiSource,
  userRole,
  visibilityTabs,
  workflow,
} from "./testSource.mjs"

const pageWorkbenchSurface = [
  removedAgentOsControlSource,
  approvalsWorkbench,
  removedAgentOsLedgerSource,
  schedulerWorkbench,
  pageWorkbenchStyle,
].join("\n")

for (const locale of ["zh-CN", "en-US"]) {
  i18n.global.locale.value = locale
  assert.notEqual(
    i18n.global.t("common.actions.refresh"),
    "common.actions.refresh",
    `Common refresh action must be translated in ${locale}`,
  )
}

assert.match(
  skills,
  /useI18n\(\)/,
  "Skills page must read user-facing copy from vue-i18n",
)

assert.match(
  skills,
  /hasScope\("skill:write"\)/,
  "Skills page must check write scope before allowing skill toggles",
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
  /hasScope\("mcp:write"\)/,
  "MCP page must check write scope before allowing mutating actions",
)

assert.match(
  mcp,
  /:disabled="!canWriteMcp"/,
  "MCP page must disable mutating controls for read-only users",
)

assert.match(
  memoryControl,
  /useMemoryWorkbenchController/,
  "Memory page must delegate state and flows to useMemoryWorkbenchController",
)

for (const componentName of [
  "MemoryQueryPanel",
  "MemoryUserQueue",
  "MemoryListPanel",
  "MemoryDetailPanel",
  "MemoryEditDialog",
]) {
  assert.ok(
    existsSync(sourcePath(`components/memory/${componentName}.vue`)),
    `Memory workbench must provide ${componentName}.vue`,
  )
  assert.match(
    memoryControl,
    new RegExp(`import ${componentName} from "\\./memory/${componentName}\\.vue"`),
    `Memory page must import ${componentName}`,
  )
  assert.match(
    memoryControl,
    new RegExp(`<${componentName}\\b`),
    `Memory page must render ${componentName}`,
  )
}

const memoryController = readOptionalSource("composables/useMemoryWorkbenchController.ts")
const memoryQueryPanel = readOptionalSource("components/memory/MemoryQueryPanel.vue")
const memoryUserQueue = readOptionalSource("components/memory/MemoryUserQueue.vue")
const memoryListPanel = readOptionalSource("components/memory/MemoryListPanel.vue")
const memoryDetailPanel = readOptionalSource("components/memory/MemoryDetailPanel.vue")
const memoryEditDialog = readOptionalSource("components/memory/MemoryEditDialog.vue")
const payloadViewer = readOptionalSource("components/common/PayloadViewer.vue")
const markdownViewer = readOptionalSource("components/common/MarkdownViewer.vue")
const memoryChildComponents = [
  memoryQueryPanel,
  memoryUserQueue,
  memoryListPanel,
  memoryDetailPanel,
  memoryEditDialog,
].join("\n")

assert.match(
  memoryController,
  /hasScope\("memories:write"\)/,
  "Memory controller must check memories:write before exposing edit flows",
)

assert.match(
  memoryController,
  /hasScope\("memories:delete"\)/,
  "Memory controller must check memories:delete before exposing delete flows",
)

assert.match(
  memoryController,
  /payloadAfterMemoryLoadFailure\(/,
  "Memory controller must keep the previous payload after a load failure",
)

assert.match(
  memoryController,
  /selectedMemoryId[\s\S]*memories\.value\.find[\s\S]*memories\.value\[0\]/,
  "Memory controller must keep the selected-memory fallback to the first visible memory",
)

assert.match(
  memoryController,
  /filters\.page\s*=\s*1/,
  "Memory controller must reset pagination when filters change",
)

assert.match(
  memoryChildComponents,
  /PayloadViewer/,
  "Memory detail must use the shared PayloadViewer for source input text/json/markdown viewing",
)

assert.match(
  memoryChildComponents,
  /DataChip/,
  "Memory panels must use the shared DataChip primitive for compact facts",
)

assert.match(
  memoryChildComponents,
  /StatusDot/,
  "Memory panels must use the shared StatusDot primitive for memory/user status",
)

assert.match(
  memoryChildComponents,
  /SectionHeader/,
  "Memory detail must use the shared SectionHeader primitive for metadata sections",
)

assert.match(
  memoryChildComponents,
  /EmptyState/,
  "Memory panels must use the shared EmptyState primitive for empty states",
)

assert.match(
  memoryChildComponents,
  /PanelHeader/,
  "Memory panels must use the shared PanelHeader primitive for panel headings",
)

assert.match(
  memoryDetailPanel,
  /<PayloadViewer[\s\S]*mode="text"/,
  "Memory detail source viewer must expose text, JSON, and Markdown modes through PayloadViewer",
)

assert.match(
  payloadViewer,
  /const modeOptions:[\s\S]*\["text", "json", "markdown"\]/,
  "Shared PayloadViewer must provide text, JSON, and Markdown source modes",
)

assert.match(
  markdownViewer,
  /new MarkdownIt\(\{[\s\S]*html:\s*false/,
  "Shared MarkdownViewer used by PayloadViewer must keep MarkdownIt html:false semantics",
)

assert.doesNotMatch(
  memoryControl,
  /class="memory-(query-panel|queue-panel|list-panel|detail-panel|row|empty|source|metadata|panel-head|edit-dialog)/,
  "MemoryControl shell must not keep the old page-local Memory DOM classes",
)

assert.doesNotMatch(
  memoryChildComponents,
  /class="memory-(query-panel|queue-panel|list-panel|detail-panel|row|empty|source|metadata|panel-head|edit-dialog)/,
  "Memory child components must not preserve old page-local Memory DOM classes",
)

assert.match(
  chat,
  /chat-thread-frame/,
  "Chat messages must render inside a centered desktop reading frame instead of spreading across the full workbench",
)

assert.match(
  chat,
  /\.chat-thread-frame\s*\{[\s\S]*max-width:\s*var\(--chat-readable-width\)/,
  "Chat reading frame must cap desktop line length with --chat-readable-width",
)

assert.match(
  chat,
  /chat-composer-frame/,
  "Chat composer controls must share the same centered frame as the message stream",
)

assert.match(
  chat,
  /\.chat-composer-frame\s*\{[\s\S]*max-width:\s*var\(--chat-readable-width\)/,
  "Chat composer frame must match the message frame width on desktop",
)

assert.doesNotMatch(
  chat,
  /\.message-row\.is-user\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+34px/,
  "User messages must not align against the full workbench width",
)

assert.match(
  chat,
  /assistantDisplayContent/,
  "Chat must normalize persisted assistant content before rendering localized status messages",
)

assert.match(
  chat,
  /chat\.notices\.requestBlocked/,
  "Blocked assistant responses must render through localized Chat copy",
)

assert.match(
  app,
  /ag-chat-session-scroll/,
  "Sidebar Chat sessions must live in a dedicated scroll region so module navigation remains reachable",
)

assert.match(
  appStyle,
  /\.ag-chat-session-scroll\s*\{[\s\S]*overflow-y:\s*auto/,
  "Sidebar Chat session scroll region must own overflow instead of pushing later nav groups behind the footer",
)

assert.match(
  app,
  /<el-icon><MoreFilled \/><\/el-icon>/,
  "Sidebar Chat session actions must use the standard More icon instead of a text colon",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-chat-session-menu\s*\{[^}]*position:\s*absolute/,
  "Sidebar Chat session actions must expand inline so the scroll container cannot clip the menu",
)

assert.match(
  appStyle,
  /\.ag-chat-session-menu\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/,
  "Sidebar Chat session action menu must occupy the full row width inside the session list",
)

assert.doesNotMatch(
  memoryDetailPanel,
  /selectedMemory\.topics/,
  "Memory detail metadata must leave topics in the middle item column",
)

assert.doesNotMatch(
  memoryControl,
  /previewPruneMemory|applyPruneMemory|prunePreview|pruneApply|memory-detail-grid/,
  "Memory page must remove pruning controls and the old bulky metadata grid",
)

assert.doesNotMatch(
  memoryControl,
  /memory-identity-strip|memory-meta-list|memory-topic-stack|detailFacts/,
  "Memory detail panel must not duplicate row metadata such as user, topics, and created timestamps",
)

for (const labelKey of [
  "runLabel",
  "sessionLabel",
  "sourceLabel",
  "userLabel",
  "agentLabel",
  "runStatusLabel",
]) {
  assert.match(
    approvalsWorkbench,
    new RegExp(`workbench\\.approvals\\.${labelKey}`),
    `Approvals detail metadata label must use workbench.approvals.${labelKey}`,
  )
}

assert.doesNotMatch(
  approvalsWorkbench,
  /<b>\s*(Run|Session|Source|User|Agent|Run Status)\s*<\/b>/,
  "Approvals detail metadata labels must not hardcode English copy",
)

assert.match(
  schedulerWorkbench,
  /workbench\.scheduler\.cronLabel/,
  "Scheduler detail cron label must use workbench.scheduler.cronLabel",
)

assert.doesNotMatch(
  schedulerWorkbench,
  /<span>\s*Cron\s*<\/span>/,
  "Scheduler detail cron label must not hardcode English copy",
)

assert.doesNotMatch(
  memoryDetailPanel,
  /openEditMemoryDialog|deleteSelectedMemory/,
  "Memory detail panel must not own edit/delete operations",
)

assert.match(
  memoryControl,
  /@media \(max-width: 980px\)[\s\S]*\.mem-workbench\s*\{[\s\S]*flex:\s*0 0 auto/,
  "Memory mobile workbench must use natural vertical flow so row topics and icon actions are not clipped",
)

assert.doesNotMatch(
  memoryListPanel,
  /max-height:\s*(?:3|4)\d+px/,
  "Memory mobile list must not hide row topics and icon actions inside a short internal scroller",
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
  /DataChip[\s\S]*v-for="metric in metrics"/,
  "MCP summary items must use shared DataChip context primitives",
)

assert.doesNotMatch(
  mcp,
  /\.mcp-context-chip\s*\{/,
  "MCP context chips must not keep old local chip CSS",
)

assert.doesNotMatch(
  mcp,
  /mcp-summary-strip|mcp-summary-chip|ag-stat-strip|ag-stat-chip/,
  "MCP must not use the global stat-strip pattern",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s*\{[^}]*display:\s*grid[^}]*border-radius:\s*8px[^}]*background:\s*var\(--ag-panel-soft\)[^}]*padding:\s*9px\s+10px/s,
  "Home Stat Chip style must define the compact 8px rectangular chip surface",
)

assert.match(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/s,
  "Home Stat Strip must render as a responsive signal grid",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*border:/s,
  "Home Stat Strip must not render as a nested standalone bubble bar",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*block-size:/s,
  "Home Stat Strip must not force a fixed height",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-stat-strip\s*\{[^}]*margin-block:/s,
  "Home Stat Strip spacing must be owned by the Home summary layout",
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

for (const [source, label] of [
  [dashboard, "Dashboard"],
  [trace, "Trace"],
  [workflow, "Workflow"],
  [mcp, "MCP"],
  [skills, "Skills"],
  [knowledge, "Knowledge"],
  [memoryControl, "Memory"],
  [pageWorkbenchSurface, "runtime workbench"],
  [agentEvals, "Evaluation"],
]) {
  assert.doesNotMatch(
    source,
    /ag-stat-strip|ag-stat-chip/,
    `${label} must not use the global Home stat-strip pattern`,
  )
}

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
  [dashboard, /dashboard-page ag-page-flow/, "Dashboard page"],
  [dashboard, /dashboard-header ag-content-panel/, "Dashboard header"],
  [dashboard, /dashboard-panel ag-content-panel/, "Dashboard panels"],
  [skills, /skill-toolbar ag-content-panel/, "Skills toolbar"],
  [skills, /skill-upload-panel ag-content-panel/, "Skills upload"],
  [mcp, /mcp-console ag-page-flow/, "MCP page"],
  [mcp, /mcp-toolbar ag-content-panel/, "MCP toolbar"],
  [mcp, /mcp-body ag-content-panel/, "MCP body"],
  [knowledge, /knowledge-console knowledge-workflow-shell ag-page-flow/, "Knowledge page"],
  [knowledge, /knowledge-document-workbench/, "Knowledge document workbench"],
  [knowledgeMetadataPanel, /knowledge-metadata-panel knowledge-panel ag-content-panel/, "Knowledge metadata"],
  [knowledgeIngestDrawer, /knowledge-ingest-drawer/, "Knowledge ingest drawer"],
  [knowledgeRetrievalPlayground, /knowledge-panel ag-content-panel retrieval-playground/, "Knowledge retrieval"],
  [trace, /trace-console ag-page-flow/, "Trace page"],
  [traceQueryToolbar, /trace-query-toolbar ag-content-panel/, "Trace filters"],
  [traceRunsPanel, /trace-runs-workbench/, "Trace runs"],
  [trace, /trace-body-grid ag-workspace-panel/, "Trace workbench"],
  [workflow, /workflow-console ag-page-flow/, "Workflow page"],
  [workflow, /workflow-header ag-content-panel/, "Workflow header"],
  [workflow, /workflow-workbench ag-workspace-panel/, "Workflow workbench"],
  [memoryControl, /ag-page-flow mem-control/, "Memory page"],
  [memoryQueryPanel, /ag-content-panel/, "Memory filters"],
  [memoryUserQueue, /ag-workspace-panel/, "Memory queue"],
  [memoryListPanel, /ag-workspace-panel/, "Memory list"],
  [memoryDetailPanel, /ag-right-panel/, "Memory detail"],
  [schedulerWorkbench, /page-panel ag-content-panel scheduler-list-panel/, "Scheduler list"],
  [cve, /cve-console ag-page-flow/, "CVE page"],
  [cve, /cve-query-panel ag-content-panel/, "CVE search"],
  [cve, /cve-results-panel ag-content-panel/, "CVE results"],
  [collect, /collect-console ag-page-flow/, "Collect page"],
  [collect, /collect-query-panel ag-content-panel/, "Collect input"],
  [collect, /collect-result-panel ag-content-panel/, "Collect result"],
  [settings, /settings-page ag-page-flow/, "Settings page"],
  [settings, /settings-tabs-head/, "Settings tabs head"],
]) {
  assert.match(
    source,
    pattern,
    `${label} must use the shared multi-section container system`,
  )
}

assert.match(
  cve,
  /<div class="cve-search-row[\s\S]*<el-input[\s\S]*<el-select[\s\S]*handleSearch[\s\S]*handleUpdateDatabase[\s\S]*<\/div>/,
  "CVE search and update actions must stay in the same row as the search controls",
)

assert.match(
  cve,
  /<div class="cve-search-row[\s\S]*t\('cve\.actions\.update'\)[\s\S]*<\/div>/,
  "CVE inline update button must use the short update label",
)

assert.doesNotMatch(
  cve,
  /<div class="cve-search-row[\s\S]*t\('cve\.actions\.updateDatabase'\)[\s\S]*<\/div>/,
  "CVE inline update button must not use the long update database label",
)

assert.doesNotMatch(
  cve,
  /mt-3 flex flex-col gap-3 sm:flex-row/,
  "CVE page must not render search and update actions in a separate row below the search controls",
)

for (const [source, pattern, label] of [
  [workflow, /workflow-inspector workflow-panel ag-right-panel/, "Workflow inspector"],
  [trace, /trace-detail-panel ag-right-panel/, "Trace detail"],
  [memoryDetailPanel, /ag-right-panel/, "Memory detail"],
  [schedulerWorkbench, /page-panel scheduler-detail-panel ag-right-panel/, "Scheduler detail"],
]) {
  assert.match(
    source,
    pattern,
    `${label} right content panel must stay on the shared right panel shell`,
  )
}

assert.doesNotMatch(
  memoryDetailPanel,
  /linear-gradient/s,
  "Memory right detail panel must not override the shared panel background with a local gradient",
)

assert.doesNotMatch(
  trace,
  /\.trace-detail-panel\s*\{[^}]*border-left:/s,
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
  /memory-command-copy|workbench\.memory\.modeAutomatic|workbench\.memory\.deskTitle|memoryModeDetails|workbench\.memory\.updateOnRun|workbench\.memory\.sessionSummaries|workbench\.memory\.readonly/,
  "Memory page must not render the removed automatic-memory desk copy or mode-status sentence",
)

assert.doesNotMatch(
  workflow,
  /workflow-title|workflow\.kicker|workflow\.title|workflow\.description/,
  "Workflow page must not render the removed top title and description copy",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s*\{[^}]*display:\s*grid[^}]*gap:\s*5px/s,
  "Home Stat Chips must use a stable grid layout",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s+strong\s*\{[^}]*text-overflow:\s*ellipsis/s,
  "Home Stat Chip values must use single-line ellipsis",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s+:where\(span,\s*small,\s*em\)\s*\{[^}]*font-size:\s*11px/s,
  "Home Stat Chip labels must be large enough to read at a glance",
)

assert.match(
  appStyle,
  /\.ag-stat-chip\s+strong\s*\{[^}]*font-size:\s*13px/s,
  "Home Stat Chip values must be large enough to read at a glance",
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
  "Home summary signal chips must not use flex sizing",
)

assert.doesNotMatch(
  appStyle,
  /\.ag-home-signal\s+(span|small|strong)\s*\{/,
  "Home summary signal chips must inherit label and value typography from ag-stat-chip",
)

assert.match(
  schedulerWorkbench,
  /class="scheduler-enabled-field"[\s\S]*?<el-switch/,
  "Scheduler create form enabled switch must use a stable field wrapper",
)

assert.match(
  useApprovalsApiSource,
  /listApprovals/,
  "Approvals API composable must expose approval listing",
)

assert.match(
  useApprovalsApiSource,
  /resolveApproval/,
  "Approvals API composable must expose approval resolve",
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
