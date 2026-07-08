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
  useTracePayloadControlsSource,
  useTracePayloadRendererSource,
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
  /useAuthStore\(\)/,
  "Knowledge page must use auth scopes before allowing global RAG configuration changes",
)

assert.match(
  knowledge,
  /hasScope\("config:write"\)/,
  "Knowledge RAG settings must require config write scope in the frontend",
)

assert.match(
  knowledge,
  /ragSaveDisabled[\s\S]*!canWriteRagSettings\.value/,
  "Knowledge RAG save action must be disabled for users without config write scope",
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
  /openSourceReplacement/,
  "Knowledge document rows must provide an action for uploading a new source version",
)

assert.match(
  knowledge,
  /source-replacement-dialog/,
  "Knowledge page must use a bounded dialog for source version replacement",
)

assert.match(
  knowledge,
  /source-replacement-dialog[\s\S]{0,180}width="min\(560px,\s*calc\(100vw - 24px\)\)"/,
  "Knowledge source replacement dialog must use a viewport-aware width on mobile",
)

assert.match(
  knowledge,
  /replaceKnowledgeDocumentSource/,
  "Knowledge page must call the source replacement API from the row action",
)

assert.match(
  knowledge,
  /document-management-bar/,
  "Knowledge document management controls must live in a structured toolbar",
)

assert.doesNotMatch(
  knowledge,
  /document-primary[\s\S]{0,240}class="doc-id"/,
  "Knowledge document name column must not show the document ID badge under the title",
)

assert.match(
  knowledge,
  /knowledge\.documents\.columns\.visibility/,
  "Knowledge document table must expose visibility as its own column",
)

assert.match(
  knowledge,
  /document-visibility-tabs[\s\S]*updateDocumentVisibility/,
  "Knowledge document visibility must be changed with the shared visibility tabs",
)

assert.match(
  knowledge,
  /--document-table-font-size:\s*11px/,
  "Knowledge document table must use one compact font scale to avoid mixed row sizing",
)

assert.match(
  knowledge,
  /--visibility-tab-min-width:\s*44px/,
  "Knowledge document visibility tabs must use the compact table density",
)

assert.match(
  knowledge,
  /grid-template-columns:[\s\S]*minmax\(160px,\s*1\.35fr\)[\s\S]*minmax\(88px,\s*0\.44fr\)[\s\S]*132px/,
  "Knowledge document table columns must use compact bounded tracks",
)

for (const locale of ["zh-CN", "en-US"]) {
  i18n.global.locale.value = locale
  const visibleCountLabel = i18n.global.t("knowledge.documents.visibleCount", { count: 1, total: 3 })
  const visibilityColumn = i18n.global.t("knowledge.documents.columns.visibility")
  const visibilityLabel = i18n.global.t("knowledge.documents.visibilityLabel", { title: "sample.md" })
  const replaceSourceLabel = i18n.global.t("knowledge.documents.replaceSourceLabel", { title: "sample.md" })
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
    `Knowledge document source replacement label must include the document title in ${locale}`,
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
  /activeDetailTab/,
  "Trace span detail must expose Info, Metadata, and Overview tab state",
)

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
