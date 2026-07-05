import assert from "node:assert/strict"
import { buildWorkflowCode, normalizePythonIdentifier, workflowStepSymbol } from "./workflowBuilder.ts"

const steps = [
  {
    id: "intake",
    kind: "step",
    executor: "agent",
    name: "标准化请求",
    symbol: "intake",
    description: "把分析员输入整理成可重复执行的 workflow input。",
    expression: "",
    maxIterations: 1,
    branches: 1,
  },
  {
    id: "route",
    kind: "router",
    executor: "function",
    name: "选择响应路径",
    symbol: "route",
    description: "按风险选择升级或报告路径。",
    expression: "last_step_content.contains('critical')",
    maxIterations: 1,
    branches: 2,
  },
]

assert.equal(
  normalizePythonIdentifier("标准化请求", "intake"),
  "intake",
  "non-ASCII display names must not become the shared fallback symbol",
)

assert.equal(
  workflowStepSymbol(steps[0]),
  "intake",
  "workflow steps should use the explicit Python symbol for generated variables",
)

const code = buildWorkflowCode({
  name: "security_research_workflow",
  description: "Security research workflow",
  input: "研判 CVE-2026-0001 的暴露风险。",
  sessionId: "security-research-session",
  userId: "operator@example.com",
  steps,
  streamEvents: true,
  storeEvents: true,
  addWorkflowHistoryToSteps: true,
  numHistoryRuns: 5,
})

assert.match(
  code,
  /Step\(name="标准化请求", agent=intake_agent/,
  "generated code must preserve localized Agno step names while using valid Python variables",
)

assert.match(
  code,
  /Router\([\s\S]*selector="last_step_content\.contains\('critical'\)"/,
  "router steps must generate Agno selector configuration",
)

assert.match(
  code,
  /stream_events=True/,
  "generated print_response call must expose Agno workflow event streaming",
)

assert.match(
  code,
  /store_events=True/,
  "generated Workflow constructor must expose event persistence",
)

assert.match(
  code,
  /num_history_runs=5/,
  "generated Workflow constructor must cap and expose workflow history run depth",
)

assert.match(
  code,
  /session_id="security-research-session"/,
  "generated run call must preserve the workflow session id used for persisted run history",
)

assert.match(
  code,
  /user_id="operator@example.com"/,
  "generated run call must preserve the workflow user id when provided",
)
