export type EvalCaseFilter = {
  keyword: string
  evalType: string
  status: string
  tag: string
}

export type EvalSummaryInput = {
  suiteCount: number
  caseCount: number
  passed: number
  failed: number
  latestRun: string
  performanceSamples: number
}

export type EvalSummaryCard = {
  label: string
  value: string | number
  hint: string
  tone: "blue" | "green" | "yellow" | "red"
}

export type EvalTone = "blue" | "green" | "yellow" | "red" | "muted"

export const filterEvalCases = <T extends {
  name?: string
  eval_types?: string[]
  tags?: string[]
  latest_status?: string
}>(cases: T[], filters: EvalCaseFilter): T[] => {
  const keyword = filters.keyword.trim().toLowerCase()
  return cases.filter((item) => {
    const matchesKeyword = !keyword || String(item.name || "").toLowerCase().includes(keyword)
    const matchesType = !filters.evalType || filters.evalType === "all" || (item.eval_types || []).includes(filters.evalType)
    const matchesStatus = !filters.status || filters.status === "all" || item.latest_status === filters.status
    const matchesTag = !filters.tag || filters.tag === "all" || (item.tags || []).includes(filters.tag)
    return matchesKeyword && matchesType && matchesStatus && matchesTag
  })
}

export const toolCallTone = (status: string) => {
  if (status === "missing" || status === "unexpected") return "red"
  if (status === "called" || status === "expected") return "green"
  return "blue"
}

export const evalTypeLabel = (type?: string | null) => {
  if (type === "accuracy") return "AccuracyEval"
  if (type === "agent_as_judge") return "AgentJudgeEval"
  if (type === "reliability") return "ReliabilityEval"
  if (type === "performance") return "PerformanceEval"
  return type || "-"
}

export const statusTone = (status?: string | null): EvalTone => {
  if (status === "failed" || status === "error") return "red"
  if (status === "passed" || status === "completed") return "green"
  if (status === "running" || status === "queued") return "yellow"
  return "blue"
}

export const scoreLabel = (score?: number | null) => {
  if (score === null || score === undefined) return "-"
  return Number.isInteger(score) ? String(score) : score.toFixed(2)
}

export const replayCaseRunId = (run: {
  case_run_id?: string | null
  data?: Record<string, unknown>
  eval_input?: Record<string, unknown>
} | null) => {
  if (!run) return ""
  const candidates = [
    run.case_run_id,
    run.data?.case_run_id,
    run.data?.caseRunId,
    run.eval_input?.case_run_id,
    run.eval_input?.caseRunId,
  ]
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim()
  }
  return ""
}

export const formatEvalTime = (value: string | number | null | undefined, locale: string) => {
  if (!value) return "-"
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export const buildEvalSummaryCards = (summary: EvalSummaryInput): EvalSummaryCard[] => {
  const totalCompleted = summary.passed + summary.failed
  const passRate = totalCompleted > 0 ? `${Math.round((summary.passed / totalCompleted) * 100)}%` : "0%"

  return [
    { label: "Suites", value: summary.suiteCount, hint: "Active regression suites", tone: "blue" },
    { label: "Cases", value: summary.caseCount, hint: "Enabled and disabled cases", tone: "green" },
    { label: "Pass Rate", value: passRate, hint: `${summary.passed} passed / ${summary.failed} failed`, tone: "yellow" },
    { label: "Failures", value: summary.failed, hint: "Failed samples available for replay", tone: "red" },
    { label: "Performance", value: summary.performanceSamples, hint: "Historical samples only", tone: "blue" },
  ]
}
