import assert from "node:assert/strict"
import {
  agentEvals,
  agentOSControl,
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
  typesSource,
  useApi,
  useApprovalsApiSource,
  useControlPlaneApiSource,
  userRole,
  visibilityTabs,
  workflow,
} from "./testSource.mjs"

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
  /hasScope\("memories:write"\)/,
  "Memory page must check write scope before exposing memory mutations",
)

assert.match(
  memoryControl,
  /memory-edit-dialog/,
  "Memory page must render a dedicated edit dialog for updating memories",
)

assert.match(
  memoryControl,
  /memory-row-actions/,
  "Memory item rows must expose edit/delete actions where the content focus lives",
)

const memoryRowFacts = memoryControl.match(
  /<span class="memory-row-facts">([\s\S]*?)<\/span>\s*<\/button>/,
)?.[1] || ""
const memoryRowCopy = memoryControl.match(
  /<span class="memory-row-copy">([\s\S]*?)<\/span>\s*<span class="memory-row-facts">/,
)?.[1] || ""
const memoryRowActions = memoryControl.match(
  /<span v-if="canWriteMemory" class="memory-row-actions">([\s\S]*?)<\/span>\s*<\/article>/,
)?.[1] || ""
const memoryDetailMetadata = memoryControl.match(
  /<section class="memory-metadata-panel">([\s\S]*?)<\/section>/,
)?.[1] || ""

assert.match(
  memoryRowFacts,
  /v-for="topic in memory\.topics"/,
  "Memory item rows must keep topics under the item content",
)

assert.doesNotMatch(
  memoryRowFacts,
  /memory\.user_id|memory\.agent_id|memory\.team_id|memory\.created_at|memory\.updated_at|createdLabel|updatedLabel/,
  "Memory item rows must not duplicate user, agent, team, or timestamps from the detail metadata",
)

assert.doesNotMatch(
  memoryRowCopy,
  /memory\.input/,
  "Memory item rows must not show the source input; it belongs in the detail metadata",
)

assert.match(
  memoryRowActions,
  /:aria-label="t\('agentOS\.memory\.editMemory'\)"/,
  "Memory row edit action must keep an accessible name while rendering as an icon button",
)

assert.match(
  memoryRowActions,
  /:aria-label="t\('agentOS\.memory\.deleteMemory'\)"/,
  "Memory row delete action must keep an accessible name while rendering as an icon button",
)

assert.doesNotMatch(
  memoryRowActions,
  /\{\{\s*t\("agentOS\.memory\.(editMemory|deleteMemory)"\)\s*\}\}/,
  "Memory row edit/delete actions must be icon-only buttons without visible text labels",
)

for (const metadataField of [
  "selectedMemory.user_id",
  "selectedMemory.agent_id",
  "selectedMemory.team_id",
  "selectedMemory.created_at",
  "selectedMemory.updated_at",
]) {
  assert.match(
    memoryDetailMetadata,
    new RegExp(metadataField.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `Memory detail metadata must include ${metadataField}`,
  )
}

assert.match(
  memoryDetailMetadata,
  /selectedMemory\.input/,
  "Memory detail metadata must include the source input that generated the memory",
)

assert.match(
  memoryDetailMetadata,
  /inputLabel/,
  "Memory detail metadata must label the source input field",
)

assert.match(
  memoryControl,
  /import MarkdownIt from "markdown-it"/,
  "Memory source input viewer must use MarkdownIt for formatted source rendering",
)

assert.match(
  memoryDetailMetadata,
  /memory-source-viewer/,
  "Memory detail metadata must render source input in a formatted viewer",
)

assert.match(
  memoryDetailMetadata,
  /v-html="renderSourceInput\(\)"/,
  "Memory source input viewer must render formatted markup instead of raw plain text only",
)

assert.match(
  memoryDetailMetadata,
  /sourceInputViewMode/,
  "Memory source input viewer must support selectable text, JSON, and Markdown modes",
)

assert.match(
  memoryDetailMetadata,
  /copySourceInput/,
  "Memory source input viewer must provide a copy action",
)

assert.match(
  memoryDetailMetadata,
  /sourceInputExpanded/,
  "Memory source input viewer must provide an expand/collapse state",
)

assert.doesNotMatch(
  memoryDetailMetadata,
  /memory-source-toolbar">\s*<span>\{\{\s*t\("agentOS\.memory\.inputLabel"\)\s*\}\}<\/span>/,
  "Memory source input viewer must not duplicate the source label inside the compact toolbar",
)

assert.match(
  memoryControl,
  /\.memory-source-actions\s*\{[\s\S]*grid-template-columns:\s*minmax\(92px,\s*1fr\)\s+auto\s+auto/,
  "Memory source input actions must stay in one stable row in the narrow right panel",
)

assert.match(
  memoryControl,
  /\.memory-mode-flags\s*\{[\s\S]*padding:\s*10px\s+12px\s+10px/,
  "Memory mode flag chips must leave bottom padding before the divider when they wrap",
)

assert.match(
  memoryControl,
  /\.memory-metadata-list\s*>\s*div\s*\{/,
  "Memory metadata row layout must only target direct rows so nested source viewer divs are not converted into metadata grids",
)

assert.doesNotMatch(
  memoryDetailMetadata,
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

assert.doesNotMatch(
  memoryControl,
  /<aside class="memory-detail-panel"[\s\S]*?(openEditMemoryDialog|deleteSelectedMemory)[\s\S]*?<\/aside>/,
  "Memory detail panel must not own edit/delete operations",
)

assert.match(
  memoryControl,
  /@media \(max-width: 980px\)[\s\S]*\.memory-workbench\s*\{[\s\S]*flex:\s*0 0 auto/,
  "Memory mobile workbench must use natural vertical flow so row topics and icon actions are not clipped",
)

assert.match(
  memoryControl,
  /@media \(max-width: 980px\)[\s\S]*\.memory-list\s*\{[\s\S]*overflow:\s*visible/,
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
  /mcp-context-chip/,
  "MCP summary items must use local context chips",
)

assertNoPillStatChip(
  mcp,
  "mcp-context-chip",
  "MCP context chips must use the 8px rectangular shape, not pill styling",
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
  [agentOSControl, "AgentOS"],
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
  agentOSControl,
  /class="scheduler-enabled-field"[\s\S]*?<el-switch/,
  "Scheduler create form enabled switch must use a stable field wrapper",
)

assert.match(
  useApprovalsApiSource,
  /listApprovals/,
  "AgentOS API composable must expose approval listing",
)

assert.match(
  useApprovalsApiSource,
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
