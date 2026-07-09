import assert from "node:assert/strict"
import {
  agentEvals,
  approvalsWorkbench,
  removedAgentOsControlSource,
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
  knowledgeDocumentList,
  knowledgeIngestDrawer,
  knowledgeMetadataPanel,
  knowledgeRetrievalPlayground,
  knowledgeWorkbenchSource,
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
  traceSessionPanel,
  traceSpanHierarchy,
  traceStyle,
  useTracePayloadControlsSource,
  useTracePayloadRendererSource,
  useTraceSpanSelectionSource,
  useTraceFilterRefreshSchedulerSource,
  useTraceFilterWatchesSource,
  useTraceExternalSelectionEventsSource,
  useTraceLifecycleSource,
  useTraceDetailViewportSource,
  useTraceDerivedPanelsSource,
  useTraceSessionListSource,
  traceWorkbenchSource,
  typesSource,
  useSecurityDataApiSource,
  useSettingsApiSource,
  userRole,
  visibilityTabs,
  workflow,
} from "./testSource.mjs"

const pageWorkbenchCopySources = [
  removedAgentOsControlSource,
  approvalsWorkbench,
  removedAgentOsLedgerSource,
  schedulerWorkbench,
].join("\n")

assert.match(
  memoryControl,
  /memory-priority-inline/,
  "Memory priority metrics must live inside the query business panel",
)

assert.match(
  memoryControl,
  /class="memory-priority-inline-card"/,
  "Memory priority metrics must use local inline context chips",
)

assert.doesNotMatch(
  memoryControl,
  /memory-priority-strip|memory-priority-card|ag-stat-strip|ag-stat-chip/,
  "Memory must not use the global stat-strip pattern",
)

assert.doesNotMatch(
  memoryControl,
  /\.memory-priority-inline-card\s*\{[^}]*border-radius:\s*999px/s,
  "Memory priority context chips must not use pill styling",
)

assert.doesNotMatch(
  memoryControl,
  /\.memory-priority-inline-card::before/s,
  "Memory priority context chips must not add local tone bars",
)

assert.match(
  knowledge,
  /knowledge-document-workbench/,
  "Knowledge page must use the document-first workbench shell",
)

assert.match(
  knowledge,
  /KnowledgeDocumentList/,
  "Knowledge page must delegate document list rendering",
)

assert.match(
  knowledge,
  /KnowledgeMetadataPanel/,
  "Knowledge page must delegate selected metadata rendering",
)

assert.match(
  knowledge,
  /KnowledgeIngestDrawer/,
  "Knowledge page must use the shared Add and Update Drawer",
)

assert.match(
  knowledgeRetrievalPlayground,
  /retrieval-playground/,
  "Knowledge retrieval playground must remain available",
)

assert.match(
  knowledgeIngestDrawer,
  /knowledge-ingest-drawer/,
  "Knowledge Add and Update must share one Drawer surface",
)

assert.match(
  knowledgeIngestDrawer,
  /advancedIngestOpen/,
  "Knowledge Drawer advanced ingest options must be collapsed by local state",
)

assert.match(
  knowledgeIngestDrawer,
  /ingest_options/,
  "Knowledge Drawer must send per-request ingest options",
)

assert.doesNotMatch(
  knowledge,
  /advanced-configuration/,
  "Knowledge page must not keep global RAG editing in the bottom page area",
)

assert.doesNotMatch(
  knowledge,
  /metadataDialogOpen|sourceReplacementDialogOpen|source-replacement-dialog/,
  "Knowledge page must replace metadata and source replacement dialogs with the new panel and Drawer",
)

assert.match(
  knowledgeMetadataPanel,
  /knowledge-metadata-panel/,
  "Knowledge metadata panel must render selected document metadata",
)

assert.match(
  knowledgeWorkbenchSource,
  /mergeUpdatedKnowledgeDocument/,
  "Knowledge update flow must merge returned new document IDs through a pure helper",
)

assert.match(
  knowledgeDocumentList,
  /document-table.*role="table"/,
  "Knowledge document management must use the custom responsive document table surface",
)

assert.match(
  knowledgeDocumentList,
  /document-action-buttons/,
  "Knowledge document actions must stay grouped in a bounded icon button row",
)

assert.match(
  knowledge,
  /replaceKnowledgeDocumentSource/,
  "Knowledge page must call the source replacement API from the row action",
)

assert.match(
  knowledgeDocumentList,
  /document-management-bar/,
  "Knowledge document management controls must live in a structured toolbar",
)

assert.doesNotMatch(
  knowledge,
  /document-primary[\s\S]{0,240}class="doc-id"/,
  "Knowledge document name column must not show the document ID badge under the title",
)

assert.match(
  knowledgeDocumentList,
  /knowledge\.documents\.columns\.visibility/,
  "Knowledge document table must expose visibility as its own column",
)

assert.match(
  knowledgeDocumentList,
  /document-visibility-tabs[\s\S]*updateDocumentVisibility/,
  "Knowledge document visibility must be changed with the shared visibility tabs",
)

assert.match(
  knowledgeDocumentList,
  /--document-table-font-size:\s*11px/,
  "Knowledge document table must use one compact font scale to avoid mixed row sizing",
)

assert.match(
  knowledgeDocumentList,
  /--visibility-tab-min-width:\s*44px/,
  "Knowledge document visibility tabs must use the compact table density",
)

assert.match(
  knowledgeDocumentList,
  /grid-template-columns:[\s\S]*minmax\(180px,\s*1fr\)[\s\S]*minmax\(96px,\s*0\.38fr\)[\s\S]*132px/,
  "Knowledge document table columns must use compact bounded tracks",
)

for (const locale of ["zh-CN", "en-US"]) {
  i18n.global.locale.value = locale
  const visibleCountLabel = i18n.global.t("knowledge.documents.visibleCount", { count: 1, total: 3 })
  const visibilityColumn = i18n.global.t("knowledge.documents.columns.visibility")
  const visibilityLabel = i18n.global.t("knowledge.documents.visibilityLabel", { title: "sample.md" })
  const replaceSourceAction = i18n.global.t("knowledge.documents.replaceSource")
  const replaceSourceLabel = i18n.global.t("knowledge.documents.replaceSourceLabel", { title: "sample.md" })
  const sourceReplacedMessage = i18n.global.t("knowledge.messages.sourceReplaced")
  const ragPermissionLabel = i18n.global.t("knowledge.messages.configPermissionRequired")
  assert.notEqual(
    visibleCountLabel,
    "knowledge.documents.visibleCount",
    `Knowledge document visible count label must be translated in ${locale}`,
  )
  assert.ok(
    visibleCountLabel.includes("1") && visibleCountLabel.includes("3"),
    `Knowledge document visible count label must include count and total in ${locale}`,
  )
  assert.notEqual(
    visibilityColumn,
    "knowledge.documents.columns.visibility",
    `Knowledge document visibility column must be translated in ${locale}`,
  )
  assert.ok(
    visibilityLabel.includes("sample.md"),
    `Knowledge document visibility tabs label must include the document title in ${locale}`,
  )
  assert.ok(
    replaceSourceLabel.includes("sample.md"),
    `Knowledge document update label must include the document title in ${locale}`,
  )
  assert.doesNotMatch(
    [replaceSourceAction, replaceSourceLabel, sourceReplacedMessage].join("\n"),
    /上传新版本|new source version|new version/i,
    `Knowledge document update copy must not describe the action as uploading a new version in ${locale}`,
  )
  assert.notEqual(
    ragPermissionLabel,
    "knowledge.messages.configPermissionRequired",
    `Knowledge RAG settings permission message must be translated in ${locale}`,
  )
}

assert.doesNotMatch(
  knowledge,
  /toggleDocumentVisibility/,
  "Knowledge document visibility must not use an ambiguous toggle action",
)

assert.match(
  knowledgeDocumentList,
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
  "上传新版本",
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
  "Trace page must use a two-pane runtime inspector shell",
)

assert.match(
  trace,
  /<style\s+src="\.\.\/styles\/trace\.css"><\/style>/,
  "Trace page must load its stylesheet from styles/trace.css",
)

assert.match(
  traceStyle,
  /\.trace-console[\s\S]*\.trace-session-card[\s\S]*\.trace-content-detail/,
  "Trace stylesheet must own the Trace workbench CSS rules",
)

assert.doesNotMatch(
  trace,
  /<style>\s*\.trace-console/,
  "Trace page must not inline its global stylesheet",
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
  traceQueryToolbar,
  /trace-query-toolbar/,
  "Trace page must expose a compact filter toolbar instead of a hero header",
)

assert.match(
  trace,
  /<TraceQueryToolbar[\s\S]*v-model:advanced-filters-open="traceAdvancedFiltersOpen"[\s\S]*@refresh="refresh"[\s\S]*@refresh-all="refreshAll"[\s\S]*@reset-all-filters="resetAllFilters"/,
  "Trace page must delegate the query toolbar to TraceQueryToolbar",
)

assert.match(
  traceQueryToolbar,
  /trace-query-toolbar[\s\S]*trace-query-primary[\s\S]*trace-advanced-filters/,
  "TraceQueryToolbar must own the Trace query and advanced filter markup",
)

assert.match(
  traceQueryToolbar,
  /trace-query-toolbar[\s\S]*grid-cols-\[minmax\(0,1fr\)_auto\][\s\S]*trace-query-primary[\s\S]*flex-wrap[\s\S]*trace-advanced-filters[\s\S]*col-span-full/,
  "TraceQueryToolbar must move simple toolbar layout to UnoCSS utilities",
)

assert.doesNotMatch(
  traceStyle,
  /\.trace-query-toolbar\s*\{[^}]*display:\s*grid|\.trace-query-primary,\s*\n\.trace-advanced-filters\s*\{[^}]*display:\s*flex/,
  "Trace stylesheet must not keep simple query toolbar layout after UnoCSS utility migration",
)

assert.match(
  traceQueryToolbar,
  /useI18n\(\)/,
  "TraceQueryToolbar must read toolbar copy from vue-i18n",
)

assert.match(
  traceQueryToolbar,
  /trace\.filters\.searchSessionId[\s\S]*trace\.filters\.workflowId/,
  "TraceQueryToolbar must own toolbar filter labels",
)

assert.match(
  traceQueryToolbar,
  /Refresh/,
  "TraceQueryToolbar must own the toolbar refresh icon",
)

assert.doesNotMatch(
  trace,
  /traceAdvancedFiltersOpen\s*=\s*!traceAdvancedFiltersOpen|trace-query-primary|trace-advanced-filters/,
  "Trace page must not inline query toolbar internals",
)

assert.match(
  trace,
  /<TraceSessionPanel[\s\S]*v-model:session-page="sessionPage"[\s\S]*:filtered-sessions="filteredSessions"[\s\S]*:paged-sessions="pagedSessions"[\s\S]*@select-session="selectSession"/,
  "Trace page must delegate the session column to TraceSessionPanel",
)

assert.match(
  traceSessionPanel,
  /trace-session-panel[\s\S]*trace-session-list[\s\S]*trace-session-pagination[\s\S]*trace-session-empty/,
  "TraceSessionPanel must own the session panel structure",
)

assert.doesNotMatch(
  traceSessionPanel,
  /<el-pagination[\s\S]*\ssmall(?:\s|>)/,
  "TraceSessionPanel pagination must use Element Plus size API instead of deprecated boolean small",
)

assert.match(
  traceSessionPanel,
  /trace-session-panel[\s\S]*flex-col[\s\S]*trace-session-list[\s\S]*content-start[\s\S]*gap-2[\s\S]*p-\[10px\]/,
  "TraceSessionPanel must move simple session column layout to UnoCSS utilities",
)

assert.doesNotMatch(
  traceStyle,
  /\.trace-session-panel\s*\{[^}]*display:\s*flex|\.trace-session-list\s*\{[^}]*display:\s*grid/,
  "Trace stylesheet must not keep simple session column layout after UnoCSS utility migration",
)

assert.match(
  traceSessionPanel,
  /useI18n\(\)/,
  "TraceSessionPanel must read session panel copy from vue-i18n",
)

assert.match(
  traceSessionPanel,
  /trace\.sessions\.title[\s\S]*trace\.empty\.noSessionsDescription/,
  "TraceSessionPanel must own session panel copy",
)

assert.doesNotMatch(
  trace,
  /trace-session-list|trace-session-card|trace-session-pagination|trace-session-empty/,
  "Trace page must not inline session panel internals",
)

assert.match(
  trace,
  /<TraceRunsPanel[\s\S]*:filtered-run-rows="filteredRunRows"[\s\S]*:selected-session="selectedSession"[\s\S]*:api-error="apiError"[\s\S]*@open-trace-detail="openTraceDetail"/,
  "Trace page must delegate the runs column to TraceRunsPanel",
)

assert.match(
  traceRunsPanel,
  /trace-runs-workbench[\s\S]*trace-runs-toolbar[\s\S]*trace-runs-list[\s\S]*trace-run-row[\s\S]*trace-alert/,
  "TraceRunsPanel must own the runs panel structure",
)

assert.match(
  traceRunsPanel,
  /useI18n\(\)/,
  "TraceRunsPanel must read runs panel copy from vue-i18n",
)

assert.match(
  traceRunsPanel,
  /trace\.runs\.title[\s\S]*trace\.empty\.selectSessionTitle[\s\S]*trace\.empty\.noSessionTracesDescription/,
  "TraceRunsPanel must own runs panel copy",
)

assert.match(
  traceRunsPanel,
  /trace-runs-workbench[\s\S]*flex-1[\s\S]*trace-runs-list[\s\S]*gap-\[10px\][\s\S]*p-\[14px\]/,
  "TraceRunsPanel must move simple runs panel layout to UnoCSS utilities",
)

assert.doesNotMatch(
  traceStyle,
  /\.trace-runs-workbench\s*\{[^}]*display:\s*flex|\.trace-runs-list\s*\{[^}]*display:\s*grid/,
  "Trace stylesheet must not keep simple runs panel layout after UnoCSS utility migration",
)

assert.doesNotMatch(
  trace,
  /trace-runs-toolbar|trace-runs-list|trace-run-row|trace\.runs\.title/,
  "Trace page must not inline runs panel internals",
)

assert.match(
  trace,
  /<TraceSpanHierarchy[\s\S]*:tree="tree"[\s\S]*:spans="spans"[\s\S]*:selected-span="selectedSpan"[\s\S]*@select-span="selectSpan"[\s\S]*@node-click="onSpanNodeClick"/,
  "Trace page must delegate the span hierarchy column to TraceSpanHierarchy",
)

assert.match(
  traceSpanHierarchy,
  /trace-span-hierarchy[\s\S]*trace-hierarchy-tree[\s\S]*trace-hierarchy-fallback[\s\S]*trace-hierarchy-node/,
  "TraceSpanHierarchy must own the hierarchy tree and fallback markup",
)

assert.match(
  traceSpanHierarchy,
  /useI18n\(\)/,
  "TraceSpanHierarchy must read hierarchy empty copy from vue-i18n",
)

assert.match(
  traceSpanHierarchy,
  /trace\.empty\.noSpansTitle[\s\S]*trace\.empty\.noSpansDescription/,
  "TraceSpanHierarchy must own no-spans copy",
)

assert.match(
  traceSpanHierarchy,
  /grid-cols-\[12px_minmax\(0,1fr\)\][\s\S]*gap-\[3px\][\s\S]*text-\[var\(--trace-muted\)\]/,
  "TraceSpanHierarchy must move simple hierarchy layout to UnoCSS utilities",
)

assert.doesNotMatch(
  traceStyle,
  /\.trace-hierarchy-fallback\s*\{[\s\S]*display:\s*grid|\.trace-hierarchy-node-copy\s*\{[\s\S]*display:\s*grid/,
  "Trace stylesheet must not keep simple hierarchy grid layout after UnoCSS utility migration",
)

assert.doesNotMatch(
  trace,
  /trace-span-hierarchy|trace-hierarchy-tree|trace-hierarchy-fallback|trace\.empty\.noSpansTitle/,
  "Trace page must not inline span hierarchy internals",
)

assert.match(
  trace,
  /trace-content-detail/,
  "Trace content area must dedicate the right side to selected span content",
)

assert.match(
  trace,
  /trace-detail-shell trace-inspector-shell[\s\S]*flex-1[\s\S]*flex-col[\s\S]*overflow-hidden/,
  "Trace detail shell must move simple container layout to UnoCSS utilities",
)

assert.doesNotMatch(
  traceStyle,
  /\.trace-detail-shell\s*\{[^}]*display:\s*flex/,
  "Trace stylesheet must not keep simple detail shell flex layout after UnoCSS utility migration",
)

assert.match(
  trace,
  /useTracePayloadRenderer[\s\S]*renderPayloadMarkupForMode/,
  "Trace content detail must render markdown through the payload renderer composable",
)

assert.match(
  useTracePayloadRendererSource,
  /MarkdownIt[\s\S]*const renderPayloadMarkupForMode/,
  "Trace payload renderer composable must own markdown payload rendering",
)

for (const inlinePayloadRenderFlow of ["renderMarkdown", "renderPayloadMarkupForMode"]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlinePayloadRenderFlow}\\s*=`),
    `Trace page must not inline payload render flow: ${inlinePayloadRenderFlow}`,
  )
}

assert.doesNotMatch(
  trace,
  /MarkdownIt/,
  "Trace page must not own the markdown renderer dependency",
)

assert.match(
  trace,
  /useTraceSpanSelection[\s\S]*activeDetailTab[\s\S]*selectSpan[\s\S]*onSpanNodeClick/,
  "Trace span detail must use the span selection composable",
)

assert.match(
  useTraceSpanSelectionSource,
  /traceDetailTabForSection[\s\S]*const selectSpan\s*=/,
  "Trace span selection composable must own detail-tab mapping",
)

for (const inlineSpanSelectionFlow of ["scrollDetailSectionIntoView", "selectSpan", "onSpanNodeClick"]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlineSpanSelectionFlow}\\s*=`),
    `Trace page must not inline span selection flow: ${inlineSpanSelectionFlow}`,
  )
}

assert.doesNotMatch(
  trace,
  /nextTick/,
  "Trace page must not own span detail scroll scheduling",
)

assert.match(
  trace,
  /useTraceFilterRefreshScheduler[\s\S]*clearPendingFilterRefresh[\s\S]*scheduleSessionFilterRefresh[\s\S]*scheduleFilterRefresh/,
  "Trace filter watches must use the filter refresh scheduler composable",
)

assert.match(
  useTraceFilterRefreshSchedulerSource,
  /window\.setTimeout[\s\S]*const scheduleFilterRefresh\s*=/,
  "Trace filter refresh scheduler composable must own debounced refresh routing",
)

for (const inlineFilterRefreshFlow of [
  "clearPendingFilterRefresh",
  "scheduleSessionFilterRefresh",
  "scheduleRunFilterRefresh",
  "scheduleFilterRefresh",
]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlineFilterRefreshFlow}\\s*=`),
    `Trace page must not inline filter refresh flow: ${inlineFilterRefreshFlow}`,
  )
}

assert.doesNotMatch(
  trace,
  /filterRefreshTimer/,
  "Trace page must not own the filter refresh timer",
)

assert.match(
  trace,
  /useTraceFilterWatches[\s\S]*sessionPage[\s\S]*scheduleSessionFilterRefresh[\s\S]*scheduleFilterRefresh/,
  "Trace page must delegate filter watchers to a composable",
)

assert.match(
  useTraceFilterWatchesSource,
  /watch[\s\S]*clampTraceSessionPage[\s\S]*scheduleSessionFilterRefresh[\s\S]*scheduleFilterRefresh/,
  "Trace filter watches composable must own filter watchers and page clamping",
)

assert.doesNotMatch(
  trace,
  /watch\(/,
  "Trace page must not inline filter watchers",
)

assert.doesNotMatch(
  trace,
  /clampTraceSessionPage/,
  "Trace page must not own session page clamping",
)

assert.match(
  trace,
  /useTraceExternalSelectionEvents[\s\S]*openTraceDetail[\s\S]*selectSessionById/,
  "Trace page must delegate external selection events to a composable",
)

assert.match(
  useTraceExternalSelectionEventsSource,
  /agno-aios-trace-select[\s\S]*const handleExternalTraceSelect\s*=/,
  "Trace external selection events composable must own trace selection listeners",
)

assert.match(
  useTraceExternalSelectionEventsSource,
  /agno-aios-trace-session-open[\s\S]*agno-aios-trace-session-select[\s\S]*const handleExternalSessionSelect\s*=/,
  "Trace external selection events composable must own session selection listeners",
)

for (const inlineExternalSelectionFlow of ["handleExternalTraceSelect", "handleExternalSessionSelect"]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlineExternalSelectionFlow}\\s*=`),
    `Trace page must not inline external selection flow: ${inlineExternalSelectionFlow}`,
  )
}

assert.doesNotMatch(
  trace,
  /agno-aios-trace-/,
  "Trace page must not own external trace event names",
)

assert.match(
  trace,
  /useTraceLifecycle[\s\S]*refresh[\s\S]*clearPendingFilterRefresh/,
  "Trace page must delegate initial refresh and cleanup lifecycle",
)

assert.match(
  useTraceLifecycleSource,
  /onMounted[\s\S]*refresh\(\)[\s\S]*ElMessage\.error[\s\S]*onUnmounted[\s\S]*clearPendingFilterRefresh/,
  "Trace lifecycle composable must own initial refresh error handling and cleanup",
)

for (const inlineLifecycleApi of ["onMounted", "onUnmounted", "ElMessage"]) {
  assert.doesNotMatch(
    trace,
    new RegExp(inlineLifecycleApi),
    `Trace page must not own lifecycle dependency: ${inlineLifecycleApi}`,
  )
}

assert.match(
  trace,
  /useTraceDetailViewport[\s\S]*scrollDetailIntoView/,
  "Trace page must delegate detail viewport scrolling",
)

assert.match(
  useTraceDetailViewportSource,
  /matchMedia[\s\S]*querySelector[\s\S]*scrollDetailIntoView/,
  "Trace detail viewport composable must own responsive detail panel scrolling",
)

assert.doesNotMatch(
  trace,
  /const scrollDetailIntoView\s*=/,
  "Trace page must not inline detail viewport scrolling",
)

assert.doesNotMatch(
  trace,
  /window\.matchMedia|document\.querySelector/,
  "Trace page must not own detail panel DOM queries",
)

assert.match(
  trace,
  /useTraceDerivedPanels[\s\S]*filteredRunRows[\s\S]*overviewItems[\s\S]*traceMetadataItems[\s\S]*toolCallItems[\s\S]*logItems[\s\S]*parsedSpan/,
  "Trace page must delegate derived run and detail panel state to a composable",
)

for (const derivedPanelFlow of [
  "buildTraceRunRows",
  "filterTraceRunRows",
  "findTraceRunRow",
  "traceRunMetrics",
  "buildTraceOverviewItems",
  "buildTraceMetadataItems",
  "buildTraceToolCallItems",
  "buildTraceLogItems",
  "emptyTraceParsedSpan",
]) {
  assert.match(
    useTraceDerivedPanelsSource,
    new RegExp(derivedPanelFlow),
    `Trace derived panels composable must own ${derivedPanelFlow}`,
  )
}

for (const inlineDerivedPanelFlow of [
  "runRows",
  "filteredRunRows",
  "selectedRunRow",
  "selectedRunMetrics",
  "overviewItems",
  "traceMetadataItems",
  "toolCallItems",
  "logItems",
  "parsedSpan",
]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlineDerivedPanelFlow}\\s*=\\s*computed`),
    `Trace page must not inline derived panel state: ${inlineDerivedPanelFlow}`,
  )
}

assert.match(
  trace,
  /useTraceSessionList[\s\S]*filteredSessions[\s\S]*pagedSessions[\s\S]*selectedSession/,
  "Trace page must delegate derived session list state to a composable",
)

for (const sessionListFlow of [
  "filterTraceSessions",
  "pageTraceSessions",
  "findTraceSession",
]) {
  assert.match(
    useTraceSessionListSource,
    new RegExp(sessionListFlow),
    `Trace session list composable must own ${sessionListFlow}`,
  )
  assert.doesNotMatch(
    trace,
    new RegExp(sessionListFlow),
    `Trace page must not own session list helper: ${sessionListFlow}`,
  )
}

for (const inlineSessionListFlow of [
  "filteredSessions",
  "pagedSessions",
  "selectedSession",
]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlineSessionListFlow}\\s*=\\s*computed`),
    `Trace page must not inline session list state: ${inlineSessionListFlow}`,
  )
}

assert.match(
  traceWorkbenchSource,
  /TraceDetailTab\s*=\s*"info" \| "metadata" \| "overview"[\s\S]*traceDetailTabForSection/,
  "Trace workbench detail tab mapping must include the requested Overview tab",
)

assert.match(
  traceWorkbenchSource,
  /isTraceJsonPayload/,
  "Trace JSON payload detection must live in the trace workbench module",
)

assert.match(
  trace,
  /trace-json-payload[\s\S]*payloadTextForMode/,
  "Trace input and output sections must render JSON payloads through the trace workbench formatter",
)

assert.match(
  trace,
  /trace-metadata-ledger/,
  "Trace Metadata tab must render run-level identifiers and timestamps",
)

assert.match(
  trace,
  /trace-metadata-copy/,
  "Trace Metadata values must provide per-field copy buttons",
)

assert.match(
  trace,
  /useTracePayloadControls[\s\S]*copyMetadataValue/,
  "Trace Metadata copy buttons must use the payload controls composable",
)

for (const payloadControlFlow of ["copyPayload", "copyMetadataValue", "togglePayloadExpanded"]) {
  assert.match(
    useTracePayloadControlsSource,
    new RegExp(`const ${payloadControlFlow}\\s*=\\s*${payloadControlFlow === "togglePayloadExpanded" ? "\\(" : "async"}`),
    `Trace payload controls composable must own ${payloadControlFlow}`,
  )
}

for (const inlinePayloadFlow of ["copyText", "copyPayload", "copyMetadataValue", "togglePayloadExpanded"]) {
  assert.doesNotMatch(
    trace,
    new RegExp(`const ${inlinePayloadFlow}\\s*=`),
    `Trace page must not inline payload control flow: ${inlinePayloadFlow}`,
  )
}

assert.match(
  useTracePayloadControlsSource,
  /copyToClipboard/,
  "Trace payload controls composable must use the shared clipboard flow",
)

assert.match(
  traceWorkbenchSource,
  /Session ID[\s\S]*User ID[\s\S]*Run ID[\s\S]*Trace ID[\s\S]*Span ID/,
  "Trace Metadata workbench builder must include Session ID, User ID, Run ID, Trace ID, and Span ID",
)

assert.match(
  traceWorkbenchSource,
  /Input Tokens[\s\S]*Output Tokens[\s\S]*Tokens[\s\S]*Model[\s\S]*Provider/,
  "Trace Overview workbench builder must summarize token counts, model, provider, status, duration, and cost",
)

assert.match(
  pageWorkbenchCopySources,
  /useI18n\(\)/,
  "page workbenches must read user-facing copy from vue-i18n",
)

for (const bulkyWorkbenchHeaderClass of [
  "page-head",
  "page-mark",
  "page-title",
]) {
  assert.equal(
    pageWorkbenchCopySources.includes(bulkyWorkbenchHeaderClass),
    false,
    `page workbenches must remove bulky top header element: ${bulkyWorkbenchHeaderClass}`,
  )
}

for (const hardcodedWorkbenchCopy of [
  "加载控制面状态",
  "暂无记录",
  "Agno docs MCP 对齐状态",
  "评测 registry 已就绪，等待接入评测运行。",
  "审批 registry 已就绪，当前没有待处理请求。",
  "调度 registry 已就绪，当前没有计划任务。",
  "当前模块还没有可展示的运行记录。",
]) {
  assert.equal(
    pageWorkbenchCopySources.includes(hardcodedWorkbenchCopy),
    false,
    `page workbench must not hardcode copy: ${hardcodedWorkbenchCopy}`,
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
  [useSecurityDataApiSource, useSettingsApiSource].join("\n"),
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
  /hasScope\("config:write"\)/,
  "Settings page must check write scope before allowing configuration changes",
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
  useSettingsApiSource,
  /\/models\/test/,
  "Settings API must call the model connectivity test endpoint",
)

assert.match(
  useSettingsApiSource,
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
