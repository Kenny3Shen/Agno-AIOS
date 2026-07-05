import assert from "node:assert/strict"
import {
  buildEvalSummaryCards,
  filterEvalCases,
  toolCallTone,
} from "./agentEvalsWorkbench.ts"

const cases = [
  { id: "case-1", name: "CVE accuracy", enabled: true, eval_types: ["accuracy"], tags: ["cve"], latest_status: "passed" },
  { id: "case-2", name: "MCP reliability", enabled: true, eval_types: ["reliability"], tags: ["mcp"], latest_status: "failed" },
]

assert.deepEqual(
  filterEvalCases(cases, { keyword: "mcp", evalType: "reliability", status: "failed", tag: "" }).map((item) => item.id),
  ["case-2"],
  "eval case filters should combine keyword, type, and latest status",
)

assert.equal(toolCallTone("missing"), "red", "missing expected tools should be red")
assert.equal(toolCallTone("called"), "green", "called expected tools should be green")

assert.deepEqual(
  buildEvalSummaryCards({ suiteCount: 1, caseCount: 2, passed: 1, failed: 1, latestRun: "2026-07-06", performanceSamples: 0 }),
  [
    { label: "Suites", value: 1, hint: "Active regression suites", tone: "blue" },
    { label: "Cases", value: 2, hint: "Enabled and disabled cases", tone: "green" },
    { label: "Pass Rate", value: "50%", hint: "1 passed / 1 failed", tone: "yellow" },
    { label: "Failures", value: 1, hint: "Failed samples available for replay", tone: "red" },
    { label: "Performance", value: 0, hint: "Historical samples only", tone: "blue" },
  ],
  "summary cards should be deterministic and copy-light",
)
