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
