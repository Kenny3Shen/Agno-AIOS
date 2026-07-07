import assert from "node:assert/strict"
import {
  existsSync,
  sourcePath,
  useAgentEvalsApiSource,
  useApprovalsApiSource,
  useApi,
  useApiCore,
  useChatApiSource,
  useControlPlaneApiSource,
  useKnowledgeApiSource,
  useMemoryControlApiSource,
  useRuntimeToolsApiSource,
  useSchedulerApiSource,
  useSecurityDataApiSource,
  useSettingsApiSource,
  useTraceApiSource,
} from "./testSource.mjs"

const expectedComposableFiles = [
  "composables/useApiCore.ts",
  "composables/useChatApi.ts",
  "composables/useControlPlaneApi.ts",
  "composables/useMemoryControlApi.ts",
  "composables/useApprovalsApi.ts",
  "composables/useSchedulerApi.ts",
  "composables/useKnowledgeApi.ts",
  "composables/useRuntimeToolsApi.ts",
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

assert.doesNotMatch(
  useApi,
  /apiFetch\(|agentOsFetch\(|const loading = ref|export function use[A-Za-z]+Api\(/,
  "composables/useApi.ts must stay a compatibility re-export entry, not retain request implementations",
)

for (const exportName of [
  "useCveApi",
  "useChatApi",
  "useChatHistory",
  "useUrl2MdApi",
  "useSettingsApi",
  "useTracingApi",
  "useSkillsApi",
  "useKnowledgeApi",
  "useMcpApi",
  "useAgentEvalsApi",
]) {
  assert.match(
    useApi,
    new RegExp(`export \\{[^}]*\\b${exportName}\\b[^}]*\\} from '\\./`),
    `compatibility entry must re-export ${exportName}`,
  )
}

const domainExpectations = [
  [useSecurityDataApiSource, "useCveApi", "/cve/search"],
  [useSecurityDataApiSource, "useUrl2MdApi", "/url2md/parse"],
  [useChatApiSource, "useChatApi", "/chat"],
  [useChatApiSource, "useChatHistory", "/chat/sessions"],
  [useControlPlaneApiSource, "useControlPlaneApi", "/os/"],
  [useMemoryControlApiSource, "useMemoryControlApi", "/os/memory"],
  [useApprovalsApiSource, "useApprovalsApi", "/os/approvals"],
  [useSchedulerApiSource, "useSchedulerApi", "/schedules"],
  [useSettingsApiSource, "useSettingsApi", "/settings"],
  [useTraceApiSource, "useTracingApi", "/traces"],
  [useRuntimeToolsApiSource, "useSkillsApi", "/skills"],
  [useRuntimeToolsApiSource, "useMcpApi", "/mcp"],
  [useKnowledgeApiSource, "useKnowledgeApi", "/knowledge"],
  [useAgentEvalsApiSource, "useAgentEvalsApi", "/agent-evals"],
]

for (const [source, hookName, endpoint] of domainExpectations) {
  assert.match(source, new RegExp(`export function ${hookName}\\(`), `${hookName} must live in its domain module`)
  assert.ok(source.includes(endpoint), `${hookName} module must own endpoint logic for ${endpoint}`)
}

assert.doesNotMatch(
  useApi,
  /useOsControlApi/,
  "compatibility entry must not re-export the removed aggregate OS control composable",
)

assert.doesNotMatch(
  useControlPlaneApiSource + useMemoryControlApiSource + useApprovalsApiSource + useSchedulerApiSource,
  /export function useOsControlApi\(/,
  "OS control frontend API must be split into functional composables",
)
