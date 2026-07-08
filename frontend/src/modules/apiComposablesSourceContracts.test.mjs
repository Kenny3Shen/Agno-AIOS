import assert from "node:assert/strict"
import {
  existsSync,
  sourcePath,
  typesSource,
  useAgentEvalsApiSource,
  useApprovalsApiSource,
  removedApiBarrelSource,
  useApiCore,
  useChatApiSource,
  useKnowledgeApiSource,
  useMemoryControlApiSource,
  removedRuntimeAggregateApiSource,
  useMcpApiSource,
  useSchedulerApiSource,
  useSecurityDataApiSource,
  useSettingsApiSource,
  useSkillsApiSource,
  useTraceApiSource,
  viteConfig,
} from "./testSource.mjs"

const expectedComposableFiles = [
  "composables/useApiCore.ts",
  "composables/useChatApi.ts",
  "composables/useMemoryControlApi.ts",
  "composables/useApprovalsApi.ts",
  "composables/useSchedulerApi.ts",
  "composables/useKnowledgeApi.ts",
  "composables/useSkillsApi.ts",
  "composables/useMcpApi.ts",
  "composables/useSecurityDataApi.ts",
  "composables/useSettingsApi.ts",
  "composables/useTraceApi.ts",
  "composables/useAgentEvalsApi.ts",
]

for (const relativePath of expectedComposableFiles) {
  assert.ok(
    existsSync(sourcePath(relativePath)),
    `${relativePath} must exist as a real same-level API composable module`,
  )
}

assert.match(
  useApiCore,
  /export type ApiFallbackKey/,
  "API core module must own fallback key typing shared by domain composables",
)

assert.match(
  useApiCore,
  /export const messageFromResponse/,
  "API core module must own response error parsing shared by domain composables",
)

assert.equal(
  removedApiBarrelSource,
  "",
  "frontend API barrel must be removed; pages import domain composables directly",
)

assert.equal(
  removedRuntimeAggregateApiSource,
  "",
  "runtime tools aggregate API must be removed; Skills and MCP import focused composables directly",
)

const domainExpectations = [
  [useSecurityDataApiSource, "useCveApi", "/cve/search"],
  [useSecurityDataApiSource, "useUrl2MdApi", "/url2md/parse"],
  [useChatApiSource, "useChatApi", "/chat"],
  [useChatApiSource, "useChatHistory", "/chat/sessions"],
  [useMemoryControlApiSource, "useMemoryControlApi", "/memory"],
  [useApprovalsApiSource, "useApprovalsApi", "/approvals"],
  [useSchedulerApiSource, "useSchedulerApi", "/schedules"],
  [useSettingsApiSource, "useSettingsApi", "/settings"],
  [useTraceApiSource, "useTracingApi", "/traces"],
  [useSkillsApiSource, "useSkillsApi", "/skills"],
  [useMcpApiSource, "useMcpApi", "/mcp"],
  [useKnowledgeApiSource, "useKnowledgeApi", "/knowledge"],
  [useAgentEvalsApiSource, "useAgentEvalsApi", "/agent-evals"],
]

for (const [source, hookName, endpoint] of domainExpectations) {
  assert.match(source, new RegExp(`export function ${hookName}\\(`), `${hookName} must live in its domain module`)
  assert.ok(source.includes(endpoint), `${hookName} module must own endpoint logic for ${endpoint}`)
}

const removedRuntimeAggregateComposable = ["use", "Os", "Control", "Api"].join("")

assert.doesNotMatch(
  useMemoryControlApiSource + useApprovalsApiSource + useSchedulerApiSource,
  new RegExp(`export function ${removedRuntimeAggregateComposable}\\(`),
  "runtime frontend APIs must stay split into functional composables",
)

assert.doesNotMatch(
  typesSource,
  new RegExp("Page" + "PayloadBase|Page" + "PayloadResponse"),
  "Page responses must not share a generic payload response type; only metric and record item types stay shared",
)

for (const [interfaceName, moduleName] of [
  ["ApprovalListResponse", "approvals"],
  ["MemoryPayloadResponse", "memory"],
  ["SchedulerPayloadResponse", "scheduler"],
]) {
  assert.match(
    typesSource,
    new RegExp(`interface ${interfaceName} \\{[\\s\\S]*module: "${moduleName}"[\\s\\S]*metrics: WorkbenchMetric\\[\\][\\s\\S]*records: WorkbenchRecord\\[\\]`),
    `${interfaceName} must own its response shape while reusing only metric and record item types`,
  )
}

assert.match(
  typesSource,
  /interface SchedulerPayloadResponse \{[\s\S]*module: "scheduler"[\s\S]*schedules: SchedulerSchedule\[\]/,
  "Scheduler must expose its own payload response type instead of using a generic page payload response",
)

assert.ok(
  !existsSync(sourcePath("composables/" + "useControl" + "PlaneApi.ts")),
  "the generic aggregate runtime composable must be removed",
)

assert.match(
  viteConfig,
  /'\/schedules':\s*\{[\s\S]*target:\s*apiProxyTarget[\s\S]*changeOrigin:\s*true/,
  "Vite dev proxy must forward direct AgentOS scheduler routes instead of serving index.html",
)
