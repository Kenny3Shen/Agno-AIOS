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
  traceStyle,
  useTraceDetailViewportSource,
  typesSource,
  useAgentEvalsApiSource,
  useApiCore,
  userRole,
  visibilityTabs,
  workflow,
} from "./testSource.mjs"

assert.match(
  useApiCore,
  /agentEvalsRequestFailed/,
  "Agent Eval API composable must expose a fallback key",
)

assert.match(
  useAgentEvalsApiSource,
  /function useAgentEvalsApi\(\)/,
  "Agent Eval API composable must expose useAgentEvalsApi",
)

assert.match(
  app,
  /const AgentEvals = defineAsyncComponent\(\(\) => import\("\.\/components\/AgentEvals\.vue"\)\)/,
  "Evaluation must load the dedicated AgentEvals workbench",
)

assert.match(
  app,
  /evaluation:\s*AgentEvals/,
  "Evaluation nav must map to the dedicated AgentEvals workbench",
)

assert.doesNotMatch(
  shellNavigation,
  new RegExp("os" + "ControlTabs[\\s\\S]*\"evaluation\""),
  "Evaluation must map as a direct shell page, not a grouped runtime tab",
)

assert.match(
  agentEvals,
  /PerformanceEval/,
  "AgentEvals should display the PerformanceEval dimension",
)

assert.match(
  agentEvals,
  /t\("agentEvals\.performance\.hiddenRun"\)/,
  "AgentEvals must render visible text for the disabled PerformanceEval run state",
)

assert.doesNotMatch(
  agentEvals,
  /runPerformance|performanceRunButton|@click="[^"]*performance/i,
  "AgentEvals must not expose a manual PerformanceEval run action",
)

assert.match(
  agentEvals,
  /filters\.suiteId !== "all"\s*\?\s*filters\.suiteId\s*:\s*""/,
  "Run suite action must require an explicit suite selection instead of using the first suite",
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
    useAgentEvalsApiSource,
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
    useAgentEvalsApiSource,
    new RegExp(apiPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    `Agent Eval API composable must call ${apiPath}`,
  )
}

assert.equal(
  removedAgentOsControlSource,
  "",
  "removed grouped parent entry must stay absent so each page maps directly to its workbench",
)

assert.equal(
  removedAgentOsLedgerSource,
  "",
  "generic grouped runtime ledger must be removed with the old aggregate entry",
)

assert.match(
  approvalsWorkbench,
  /approvals-workbench/,
  "Approvals page must render a dedicated approvals workbench",
)

assert.match(
  approvalsWorkbench,
  /resolveSelectedApproval\("approved"\)/,
  "Approvals page must bind an approve action",
)

assert.match(
  approvalsWorkbench,
  /resolveSelectedApproval\("rejected"\)/,
  "Approvals page must bind a reject action",
)

assert.match(
  schedulerWorkbench,
  /scheduler-workbench/,
  "Scheduler page must render a dedicated scheduler workbench",
)

assert.match(
  pageWorkbenchStyle,
  /\.scheduler-enabled-field\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden/s,
  "Scheduler enabled switch field must not overlap adjacent form controls",
)

assert.match(
  pageWorkbenchStyle,
  /\.scheduler-enabled-field\s+\.el-switch__core\s*\{[^}]*min-width:\s*40px/s,
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
  /ag-nav-security-data/,
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

for (const chartClass of ["dashboard-kpi-grid", "dashboard-line-chart", "dashboard-bars", "dashboard-run-list", "dashboard-model-list"]) {
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
  traceStyle,
  /trace-id-line/,
  "Trace identifiers must render in a dedicated wrapping line",
)

assert.match(
  trace,
  /trace-waterfall-row/,
  "Trace waterfall rows must use the refactored layout-safe row class",
)

assert.match(
  traceStyle,
  /overflow-wrap:\s*anywhere/,
  "Trace page CSS must allow long IDs and JSON-like values to wrap instead of overlapping",
)

assert.match(
  trace,
  /scrollDetailIntoView/,
  "Trace mobile selection must move the detail pane into view after choosing a run",
)

assert.match(
  traceStyle,
  /\.trace-body-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*20%\)\s+minmax\(0,\s*20%\)\s+minmax\(0,\s*60%\)/s,
  "Trace workbench must use fixed 20/20/60 columns for sessions, runs, and details",
)

assert.match(
  trace,
  /trace-detail-panel ag-right-panel/,
  "Trace run detail must be a fixed right panel instead of a drawer",
)

for (const removedTraceDrawerBehavior of [
  "traceDrawerOpen",
  "trace-detail-drawer",
  "trace-drawer-resizer",
  "openAdjacentRun",
  "previousRun",
  "nextRun",
  "collapseHeader",
  "refreshSelectedTrace",
]) {
  assert.equal(
    trace.includes(removedTraceDrawerBehavior),
    false,
    `Trace fixed detail panel must not retain drawer/navigation behavior: ${removedTraceDrawerBehavior}`,
  )
}

assert.match(
  useTraceDetailViewportSource,
  /scrollIntoView\(\{ block: "start", behavior: "smooth" \}\)/,
  "Trace detail viewport composable must scroll the fixed detail panel into view",
)

assert.match(
  readOptionalSource("components/Knowledge.vue"),
  /reader-strategy-console[\s\S]*strategy-row/,
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
  /advanced-configuration[\s\S]*knowledge-runtime-summary/,
  "Knowledge runtime status must live inside Advanced Configuration",
)

assert.match(
  knowledge,
  /knowledge-runtime-chip/,
  "Knowledge status items must use local runtime context chips",
)

assert.match(
  knowledge,
  /<div v-for="card in statisticsCards"[^>]*class="knowledge-runtime-chip"/,
  "Knowledge status metrics must render as compact runtime values",
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
  "knowledge-runtime-chip",
  "Knowledge runtime chips must use the 8px rectangular chip shape, not pill styling",
)

assert.doesNotMatch(
  knowledge,
  /knowledge-stat-strip|knowledge-stat-chip|ag-stat-strip|ag-stat-chip/,
  "Knowledge must not use the global stat-strip pattern",
)

assert.doesNotMatch(
  knowledge,
  /\.knowledge-runtime-chip\s*\{[^}]*border-radius:\s*999px/s,
  "Knowledge runtime chips must not use pill styling",
)

assert.match(
  knowledge,
  /knowledge-upload-pipeline/,
  "Knowledge upload area must show the RAG ingestion pipeline",
)
