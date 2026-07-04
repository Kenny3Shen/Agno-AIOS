import type { ChatSession, ChatSessionRun, TraceItem } from "../types"

export type SessionStatusFilter = "active" | "archived" | "all"
export type RunStatusFilter = "" | "OK" | "ERROR" | "UNSET"

export interface TraceSessionFilters {
  sessionId: string
  userId: string
  keyword: string
  status: SessionStatusFilter
}

export interface TraceRunFilters {
  runId: string
  agentId: string
  teamId: string
  workflowId: string
  status: RunStatusFilter
}

export interface TraceOwnerLabels {
  agentId: string
  teamId: string
  workflowId: string
}

export interface TraceRunRow {
  key: string
  title: string
  runId: string
  sessionId: string
  ownerId: string
  ownerLabel: string
  trace: TraceItem
  run?: ChatSessionRun
}

export interface TraceSummaryState {
  totalTraces: number
  totalSpans: number
  errors: number
  avgLatencyMs: number
  sampleSize: number
}

export interface TraceSummaryCard {
  label: string
  value: string | number
  hint: string
  tone: string
}

interface BuildTraceRunRowsParams {
  traces: TraceItem[]
  selectedSession: ChatSession | null
  selectedSessionId: string | null
  labels: TraceOwnerLabels
}

interface BuildTraceSummaryCardsParams {
  sessions: ChatSession[]
  visibleSessionCount: number
  summary: TraceSummaryState
  formatLatencySeconds: (durationMs: number) => string
  latencyTone: (durationMs: number) => string
}

const normalize = (value?: string | null) => (value || "").trim().toLowerCase()

const sessionMatchesKeyword = (session: ChatSession, keyword: string) => {
  if (!keyword) return true
  const haystack = [
    session.preview,
    session.session_id,
    session.user_id,
  ].map(normalize).join(" ")
  return haystack.includes(keyword)
}

const runsByRunId = (session: ChatSession | null) => {
  const map = new Map<string, ChatSessionRun>()
  const runs = session?.runs || []
  for (const run of runs) {
    const runId = typeof run.run_id === "string" ? run.run_id.trim() : ""
    if (runId) map.set(runId, run)
  }
  return map
}

export const filterTraceSessions = (
  sessions: ChatSession[],
  filters: TraceSessionFilters,
) => {
  const sessionId = normalize(filters.sessionId)
  const userId = normalize(filters.userId)
  const keyword = normalize(filters.keyword)
  return sessions.filter((session) => {
    if (filters.status === "active" && session.archived) return false
    if (filters.status === "archived" && !session.archived) return false
    if (sessionId && !normalize(session.session_id).includes(sessionId)) return false
    if (userId && !normalize(session.user_id).includes(userId)) return false
    return sessionMatchesKeyword(session, keyword)
  })
}

export const findTraceSession = (
  sessions: ChatSession[],
  sessionId: string | null,
) => sessions.find((session) => session.session_id === sessionId) || null

export const findExactTraceSession = (
  sessions: ChatSession[],
  sessionId: string,
) => sessions.find((session) => normalize(session.session_id) === normalize(sessionId)) || null

export const buildTraceRunRows = ({
  traces,
  selectedSession,
  selectedSessionId,
  labels,
}: BuildTraceRunRowsParams): TraceRunRow[] => {
  const sessionRuns = runsByRunId(selectedSession)
  return traces.map((trace) => {
    const runId = trace.run_id || ""
    const run = runId ? sessionRuns.get(runId) : undefined
    const ownerId = trace.agent_id || trace.team_id || trace.workflow_id || run?.agent_id || run?.team_id || run?.workflow_id || "-"
    const ownerLabel = trace.agent_id || run?.agent_id
      ? labels.agentId
      : trace.team_id || run?.team_id
        ? labels.teamId
        : labels.workflowId
    return {
      key: trace.trace_id,
      title: trace.name || run?.agent_name || runId || trace.trace_id,
      runId,
      sessionId: trace.session_id || selectedSessionId || "",
      ownerId,
      ownerLabel,
      trace,
      run,
    }
  })
}

export const filterTraceRunRows = (
  rows: TraceRunRow[],
  filters: TraceRunFilters,
) => {
  const runId = normalize(filters.runId)
  const agentId = normalize(filters.agentId)
  const teamId = normalize(filters.teamId)
  const workflowId = normalize(filters.workflowId)
  return rows.filter((row) => {
    const trace = row.trace
    const run = row.run
    if (filters.status && trace.status !== filters.status) return false
    if (runId && !normalize(row.runId).includes(runId)) return false
    if (agentId && !normalize(trace.agent_id || run?.agent_id).includes(agentId)) return false
    if (teamId && !normalize(trace.team_id || run?.team_id).includes(teamId)) return false
    if (workflowId && !normalize(trace.workflow_id || run?.workflow_id).includes(workflowId)) return false
    return true
  })
}

export const summarizeTraceItems = (
  items: TraceItem[],
  totalCount = items.length,
): TraceSummaryState => {
  const durations = items
    .map((trace) => Number(trace.duration_ms))
    .filter((value) => Number.isFinite(value) && value >= 0)
  const totalDuration = durations.reduce((sum, value) => sum + value, 0)
  return {
    totalTraces: Number(totalCount || items.length || 0),
    totalSpans: items.reduce((sum, trace) => sum + Number(trace.total_spans || 0), 0),
    errors: items.reduce((sum, trace) => sum + Number(trace.error_count ?? (trace.status === "ERROR" ? 1 : 0)), 0),
    avgLatencyMs: durations.length ? totalDuration / durations.length : 0,
    sampleSize: items.length,
  }
}

export const buildTraceSummaryCards = ({
  sessions,
  visibleSessionCount,
  summary,
  formatLatencySeconds,
  latencyTone,
}: BuildTraceSummaryCardsParams): TraceSummaryCard[] => [
  {
    label: "Sessions",
    value: sessions.length,
    hint: `${visibleSessionCount} visible sessions`,
    tone: "blue",
  },
  {
    label: "Traces",
    value: summary.totalTraces,
    hint: `${summary.sampleSize} sampled traces`,
    tone: "green",
  },
  {
    label: "Spans",
    value: summary.totalSpans,
    hint: "Spans observed in sampled traces",
    tone: "blue",
  },
  {
    label: "Errors",
    value: summary.errors,
    hint: "Trace or span errors in sampled traces",
    tone: summary.errors > 0 ? "red" : "green",
  },
  {
    label: "Avg Latency(s)",
    value: formatLatencySeconds(summary.avgLatencyMs),
    hint: "Average trace duration in sampled traces",
    tone: latencyTone(summary.avgLatencyMs),
  },
]
