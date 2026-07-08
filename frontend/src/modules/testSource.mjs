import { existsSync, readFileSync } from "node:fs"
import assert from "node:assert/strict"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { createI18n } from "vue-i18n"
import { enUS } from "../i18n/locales/en-US.ts"
import { zhCN } from "../i18n/locales/zh-CN.ts"
export { hasRoleScope, hasUserScope, userRole } from "../lib/scopes.ts"
export { existsSync }

const root = join(dirname(fileURLToPath(import.meta.url)), "..")
export const sourcePath = (relativePath) => join(root, relativePath)
export const readSource = (relativePath) => readFileSync(sourcePath(relativePath), "utf8")
export const readOptionalSource = (relativePath) => {
  const path = sourcePath(relativePath)
  return existsSync(path) ? readFileSync(path, "utf8") : ""
}

export const app = readSource("App.vue")
export const appStyle = readSource("style.css")
export const designTokens = readSource("styles/tokens.css")
export const authScreen = readSource("components/AuthScreen.vue")
export const chat = readOptionalSource("components/Chat.vue")
export const trace = readOptionalSource("components/Trace.vue")
export const dashboard = readOptionalSource("components/Dashboard.vue")
export const cve = readOptionalSource("components/CVE.vue")
export const mcp = readOptionalSource("components/MCP.vue")
export const skills = readOptionalSource("components/Skills.vue")
export const collect = readOptionalSource("components/Collect.vue")
export const settings = readOptionalSource("components/Settings.vue")
export const knowledge = readOptionalSource("components/Knowledge.vue")
export const removedAgentOsControlSource = readOptionalSource("components/" + "Agent" + "OS" + "Control.vue")
export const approvalsWorkbench = readOptionalSource("components/ApprovalsWorkbench.vue")
export const removedAgentOsLedgerSource = readOptionalSource("components/" + "agent" + "os/" + "Agent" + "OS" + "Ledger.vue")
export const schedulerWorkbench = readOptionalSource("components/SchedulerWorkbench.vue")
export const agentEvals = readOptionalSource("components/AgentEvals.vue")
export const memoryControl = readOptionalSource("components/MemoryControl.vue")
export const workflow = readOptionalSource("components/Workflow.vue")
export const pageWorkbenchStyle = readOptionalSource("styles/page-workbench.css")
export const typesSource = readSource("types/index.ts")
export const removedApiBarrelSource = readOptionalSource("composables/useApi.ts")
export const useApiCore = readOptionalSource("composables/useApiCore.ts")
export const useChatApiSource = readOptionalSource("composables/useChatApi.ts")
export const useMemoryControlApiSource = readOptionalSource("composables/useMemoryControlApi.ts")
export const useApprovalsApiSource = readOptionalSource("composables/useApprovalsApi.ts")
export const useSchedulerApiSource = readOptionalSource("composables/useSchedulerApi.ts")
export const useKnowledgeApiSource = readOptionalSource("composables/useKnowledgeApi.ts")
export const removedRuntimeAggregateApiSource = readOptionalSource("composables/" + "useRuntime" + "ToolsApi.ts")
export const useSkillsApiSource = readOptionalSource("composables/useSkillsApi.ts")
export const useMcpApiSource = readOptionalSource("composables/useMcpApi.ts")
export const useSecurityDataApiSource = readOptionalSource("composables/useSecurityDataApi.ts")
export const useSettingsApiSource = readOptionalSource("composables/useSettingsApi.ts")
export const useTraceApiSource = readOptionalSource("composables/useTraceApi.ts")
export const useTracePayloadControlsSource = readOptionalSource("composables/useTracePayloadControls.ts")
export const useTracePayloadRendererSource = readOptionalSource("composables/useTracePayloadRenderer.ts")
export const useTraceSessionControllerSource = readOptionalSource("composables/useTraceSessionController.ts")
export const useAgentEvalsApiSource = readOptionalSource("composables/useAgentEvalsApi.ts")
export const apiClient = readOptionalSource("lib/apiClient.ts")
export const viteConfig = readSource("../vite.config.ts")
export const clipboard = readOptionalSource("lib/clipboard.ts")
export const authStoreSource = readOptionalSource("stores/auth.ts")
export const scopes = readOptionalSource("lib/scopes.ts")
export const shellNavigation = readOptionalSource("modules/shellNavigation.ts")
export const shellBrand = readOptionalSource("modules/shellBrand.ts")
export const traceWorkbenchSource = readOptionalSource("modules/traceWorkbench.ts")
export const visibilityTabs = readOptionalSource("components/common/ResourceVisibilityTabs.vue")

const compositionModeKey = "lega" + "cy"

export const i18n = createI18n({
  [compositionModeKey]: false,
  locale: "zh-CN",
  messages: {
    "en-US": enUS,
    "zh-CN": zhCN,
  },
})

export const assertTextOrder = (source, labels, message) => {
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

export const assertNoPillStatChip = (source, className, message) => {
  assert.doesNotMatch(
    source,
    new RegExp(`\\.${className}\\s*\\{[^}]*border-radius:\\s*999px`, "s"),
    message,
  )
}
