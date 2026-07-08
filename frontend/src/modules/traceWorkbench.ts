import type { ChatSession, ChatSessionRun, ParsedSpanDisplay, ParsedSpanEvent, ParsedSpanPayload, SpanItem, SpanTreeNode, TraceItem } from "../types"

export type SessionStatusFilter = "active" | "archived" | "all"
export type RunStatusFilter = "" | "OK" | "ERROR" | "UNSET"
export type TracePayloadViewMode = "text" | "json" | "markdown"

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

export interface TraceDetailMetricItem {
  label: string
  value: string
  displayValue: string
  tone: string
}

export interface TraceMetadataItem {
  label: string
  value: string
  displayValue: string
}

export interface TraceToolCallItem {
  id: string
  name: string
  status: string
  durationMs: number
  arguments: string
  response: string
  metadata: string
}

export interface TraceLogItem {
  name: string
  message: string
}

export interface TraceSessionOpenRequest {
  sessionId: string
  userId?: string | null
  userFilter?: string
  runId: string
}

export interface TraceSessionSelectionResolution {
  keepCurrent: boolean
  nextSession: ChatSession | null
  nextSessionId: string | null
  shouldClearSelection: boolean
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

interface BuildTraceOverviewItemsParams {
  trace: TraceItem | null
  run?: ChatSessionRun | null
  span?: SpanItem | null
  parsedSpan: ParsedSpanDisplay
  metrics: Record<string, unknown>
}

interface BuildTraceMetadataItemsParams {
  trace: TraceItem | null
  run?: ChatSessionRun | null
  session: ChatSession | null
  row?: TraceRunRow | null
  span?: SpanItem | null
  formatAnyDateTime: (value?: unknown) => string
}

interface BuildTraceLogItemsParams {
  parsedEvents: ParsedSpanEvent[]
  rawEvents?: unknown[] | null
}

interface BuildTraceListParamsParams {
  session: ChatSession
  filters: TraceRunFilters
}

interface BuildTraceStoreFiltersParams {
  session: ChatSession
  runId: string
  filters: TraceRunFilters
}

interface ResolveTraceSessionSelectionParams {
  visibleSessions: ChatSession[]
  selectedSessionId: string | null
  selectedSession: ChatSession | null
  requestedSessionId: string
}

const emptyParsedSpan: ParsedSpanDisplay = {
  input: { format: "empty", text: "", data: null },
  output: { format: "empty", text: "", data: null },
  metadata: {
    model: null,
    provider: null,
    tool: null,
    operation: null,
    tokens: {
      prompt: null,
      completion: null,
      total: null,
    },
  },
  events: [],
}

const normalize = (value?: string | null) => (value || "").trim().toLowerCase()

const traceDateTimeOptions = {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
} as const

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
  const safeSessions = Array.isArray(sessions) ? sessions : []
  return safeSessions.filter((session) => {
    if (filters.status === "active" && session.archived) return false
    if (filters.status === "archived" && !session.archived) return false
    if (sessionId && !normalize(session.session_id).includes(sessionId)) return false
    if (userId && !normalize(session.user_id).includes(userId)) return false
    return sessionMatchesKeyword(session, keyword)
  })
}

export const pageTraceSessions = (
  sessions: ChatSession[],
  page: number,
  pageSize: number,
) => {
  const start = (page - 1) * pageSize
  return sessions.slice(start, start + pageSize)
}

export const clampTraceSessionPage = (
  page: number,
  visibleSessionCount: number,
  pageSize: number,
) => {
  const maxPage = Math.max(1, Math.ceil(visibleSessionCount / pageSize))
  return page > maxPage ? maxPage : page
}

export const findTraceSession = (
  sessions: ChatSession[],
  sessionId: string | null,
) => sessions.find((session) => session.session_id === sessionId) || null

export const findExactTraceSession = (
  sessions: ChatSession[],
  sessionId: string,
) => sessions.find((session) => normalize(session.session_id) === normalize(sessionId)) || null

export const resolveTraceSessionSelection = ({
  visibleSessions,
  selectedSessionId,
  selectedSession,
  requestedSessionId,
}: ResolveTraceSessionSelectionParams): TraceSessionSelectionResolution => {
  const currentStillVisible = visibleSessions.some((session) => session.session_id === selectedSessionId)
  if (currentStillVisible && selectedSession) {
    return {
      keepCurrent: true,
      nextSession: null,
      nextSessionId: selectedSessionId,
      shouldClearSelection: false,
    }
  }

  const exactSession = findExactTraceSession(visibleSessions, requestedSessionId)
  const nextSession = exactSession || (visibleSessions.length === 1 ? visibleSessions[0] : null)
  return {
    keepCurrent: false,
    nextSession,
    nextSessionId: nextSession?.session_id || null,
    shouldClearSelection: true,
  }
}

export const normalizeTraceSessionOpenRequest = (
  sessionId: string,
  userId?: string | null,
  runId?: string | null,
): TraceSessionOpenRequest | null => {
  const normalizedSessionId = sessionId.trim()
  if (!normalizedSessionId) return null
  return {
    sessionId: normalizedSessionId,
    userId: userId ?? null,
    userFilter: userId === undefined ? undefined : userId || "",
    runId: (runId || "").trim(),
  }
}

export const ensureTraceSession = (
  sessions: ChatSession[],
  request: TraceSessionOpenRequest,
) => {
  const session = sessions.find((item) => item.session_id === request.sessionId)
  if (session) return { session, sessions }

  const placeholderSession: ChatSession = {
    session_id: request.sessionId,
    user_id: request.userId || null,
    preview: request.sessionId,
    created_at: 0,
    updated_at: 0,
    archived: false,
    archived_at: null,
    runs: [],
  }
  return {
    session: placeholderSession,
    sessions: [placeholderSession, ...sessions],
  }
}

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

export const findTraceRunRow = (
  rows: TraceRunRow[],
  traceId: string | null | undefined,
) => {
  const normalizedTraceId = (traceId || "").trim()
  if (!normalizedTraceId) return null
  return rows.find((row) => row.trace.trace_id === normalizedTraceId) || null
}

export const traceRunMetrics = (row?: TraceRunRow | null): Record<string, unknown> => {
  const metrics = row?.run?.metrics
  return metrics && typeof metrics === "object" ? metrics as Record<string, unknown> : {}
}

export const buildTraceListParams = ({
  session,
  filters,
}: BuildTraceListParamsParams) => ({
  page: 1,
  limit: 50,
  session_id: session.session_id,
  user_id: session.user_id || undefined,
  agent_id: filters.agentId || undefined,
  team_id: filters.teamId || undefined,
  workflow_id: filters.workflowId || undefined,
  status: filters.status,
})

export const buildTraceStoreFilters = ({
  session,
  runId,
  filters,
}: BuildTraceStoreFiltersParams) => ({
  session_id: session.session_id,
  run_id: runId,
  user_id: session.user_id || "",
  agent_id: filters.agentId,
  team_id: filters.teamId,
  workflow_id: filters.workflowId,
  status: filters.status,
})

export const mergePreferredTraceItem = (
  items: TraceItem[],
  preferredTrace: TraceItem | null | undefined,
) => {
  if (!preferredTrace) return items
  return [
    preferredTrace,
    ...items.filter((trace) => trace.trace_id !== preferredTrace.trace_id),
  ]
}

export const findFirstTraceSpan = (
  tree: SpanTreeNode[],
  spans: SpanItem[],
) => tree[0]?.span || spans[0] || null

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

export const traceValueOrDash = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "-"
  return String(value)
}

export const compactTraceId = (value?: string | null) => {
  const text = (value || "").trim()
  if (!text) return "-"
  if (text.length <= 18) return text
  return `${text.slice(0, 8)}...${text.slice(-4)}`
}

export const traceTagType = (status: string) => {
  if (status === "OK") return "success"
  if (status === "ERROR") return "danger"
  if (status === "UNSET") return "info"
  return "warning"
}

export const traceStatusClass = (status: string) => {
  if (status === "OK") return "ok"
  if (status === "ERROR") return "error"
  if (status === "UNSET") return "unset"
  return "other"
}

export const traceStatusLabel = (status: string) => {
  if (status === "OK") return "Success"
  if (status === "ERROR") return "Error"
  if (status === "UNSET") return "Running"
  if (!status) return "-"
  return status
}

export const traceDurationClass = (durationMs: number | string | null | undefined) => {
  const n = Number(durationMs)
  if (!Number.isFinite(n) || n < 0) return "duration-muted"
  if (n < 500) return "duration-fast"
  if (n < 2000) return "duration-medium"
  if (n < 10000) return "duration-slow"
  return "duration-critical"
}

export const formatTraceDuration = (durationMs: number | string | null | undefined): string => {
  const n = Number(durationMs)
  if (!Number.isFinite(n) || n < 0) return "-"

  if (n < 1000) {
    if (n < 10) return `${n.toFixed(2)} ms`
    if (n < 100) return `${n.toFixed(1)} ms`
    return `${Math.round(n)} ms`
  }

  const sec = n / 1000
  if (sec < 60) {
    return sec < 10 ? `${sec.toFixed(2)} s` : `${sec.toFixed(1)} s`
  }

  const min = Math.floor(sec / 60)
  const remSec = sec % 60
  if (min < 60) return `${min}m ${remSec.toFixed(1)}s`

  const hour = Math.floor(min / 60)
  const remMin = min % 60
  return `${hour}h ${remMin}m ${Math.round(remSec)}s`
}

export const prettyTraceJson = (obj: unknown) => {
  try {
    if (!obj) return "{}"
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

export const formatTraceCost = (value: unknown) => {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return "-"
  if (n < 0.01) return `$${n.toFixed(5)}`
  return `$${n.toFixed(2)}`
}

export const formatTraceDateTime = (value?: string | null) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", traceDateTimeOptions)
}

export const formatTraceAnyDateTime = (value?: unknown) => {
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "number") {
    const timestamp = value > 1_000_000_000_000 ? value : value * 1000
    return new Date(timestamp).toLocaleString("zh-CN", traceDateTimeOptions)
  }
  return formatTraceDateTime(String(value))
}

export const formatTraceSessionTime = (timestamp?: number | null) => {
  if (!timestamp) return "-"
  return new Date(timestamp * 1000).toLocaleString("zh-CN", traceDateTimeOptions)
}

export const formatTracePayloadText = (payload: ParsedSpanPayload, fallback: string) => {
  if (!payload.text) return fallback
  if (payload.data !== null && payload.data !== undefined) return prettyTraceJson(payload.data)
  try {
    return JSON.stringify(JSON.parse(payload.text), null, 2)
  } catch {
    return payload.text
  }
}

export const isTraceJsonPayload = (payload: ParsedSpanPayload) => {
  if (payload.format === "json" || payload.data !== null && payload.data !== undefined) return true
  const text = payload.text?.trim()
  if (!text || !["{", "["].includes(text[0])) return false
  try {
    JSON.parse(text)
    return true
  } catch {
    return false
  }
}

export const isTraceToolSpan = (span: SpanItem) => {
  const metadata = span.parsed?.metadata
  const haystack = [span.kind, span.name, metadata?.tool, metadata?.operation]
    .map((value) => String(value || "").toLowerCase())
    .join(" ")
  return Boolean(metadata?.tool) || haystack.includes("tool") || haystack.includes("function")
}

export const tracePayloadTextForMode = (
  payload: ParsedSpanPayload,
  mode: TracePayloadViewMode,
  fallback: string,
) => {
  if (mode === "json") return isTraceJsonPayload(payload) ? formatTracePayloadText(payload, fallback) : payload.text || fallback
  return payload.text || fallback
}

export const buildTraceOverviewItems = ({
  trace,
  run,
  span,
  parsedSpan,
  metrics,
}: BuildTraceOverviewItemsParams): TraceDetailMetricItem[] => {
  const metadata = parsedSpan.metadata || emptyParsedSpan.metadata
  const tokens = metadata.tokens || {}
  const inputTokens = traceValueOrDash(metrics.input_tokens ?? metrics.prompt_tokens ?? tokens.prompt)
  const outputTokens = traceValueOrDash(metrics.output_tokens ?? metrics.completion_tokens ?? tokens.completion)
  const totalTokens = traceValueOrDash(metrics.total_tokens ?? tokens.total)
  const model = traceValueOrDash(run?.model || metadata.model)
  const provider = traceValueOrDash(run?.model_provider || metadata.provider)
  const agent = traceValueOrDash(trace?.agent_id || run?.agent_id || run?.agent_name)
  const workflow = traceValueOrDash(trace?.workflow_id || run?.workflow_id)
  const team = traceValueOrDash(trace?.team_id || run?.team_id)
  const errorText = span?.status_message || (trace?.status === "ERROR" ? trace.name : "")
  return [
    { label: "Status", value: traceValueOrDash(trace?.status), displayValue: traceStatusLabel(trace?.status || ""), tone: trace?.status === "ERROR" ? "error" : "" },
    { label: "Duration", value: formatTraceDuration(trace?.duration_ms), displayValue: formatTraceDuration(trace?.duration_ms), tone: "" },
    { label: "Input Tokens", value: inputTokens, displayValue: inputTokens, tone: "" },
    { label: "Output Tokens", value: outputTokens, displayValue: outputTokens, tone: "" },
    { label: "Tokens", value: totalTokens, displayValue: totalTokens, tone: "" },
    { label: "Model", value: model, displayValue: model, tone: "" },
    { label: "Provider", value: provider, displayValue: provider, tone: "" },
    { label: "Agent", value: agent, displayValue: compactTraceId(agent), tone: "" },
    { label: "Workflow", value: workflow, displayValue: compactTraceId(workflow), tone: "" },
    { label: "Team", value: team, displayValue: compactTraceId(team), tone: "" },
    { label: "Cost", value: formatTraceCost(metrics.cost), displayValue: formatTraceCost(metrics.cost), tone: "" },
    { label: "Error", value: traceValueOrDash(errorText), displayValue: traceValueOrDash(errorText), tone: errorText ? "error" : "" },
  ]
}

export const buildTraceMetadataItems = ({
  trace,
  run,
  session,
  row,
  span,
  formatAnyDateTime,
}: BuildTraceMetadataItemsParams): TraceMetadataItem[] => [
  { label: "Session ID", value: traceValueOrDash(trace?.session_id || row?.sessionId || session?.session_id), displayValue: compactTraceId(trace?.session_id || row?.sessionId || session?.session_id) },
  { label: "User ID", value: traceValueOrDash(trace?.user_id || run?.user_id || session?.user_id), displayValue: compactTraceId(trace?.user_id || run?.user_id || session?.user_id) },
  { label: "Run ID", value: traceValueOrDash(trace?.run_id || run?.run_id), displayValue: compactTraceId(trace?.run_id || run?.run_id) },
  { label: "Trace ID", value: traceValueOrDash(trace?.trace_id), displayValue: compactTraceId(trace?.trace_id) },
  { label: "Span ID", value: traceValueOrDash(span?.span_id), displayValue: compactTraceId(span?.span_id) },
  { label: "Parent Span", value: traceValueOrDash(span?.parent_span_id), displayValue: compactTraceId(span?.parent_span_id) },
  { label: "Created", value: traceValueOrDash(trace?.created_at || run?.created_at), displayValue: formatAnyDateTime(trace?.created_at || run?.created_at) },
  { label: "Started", value: traceValueOrDash(trace?.start_time || span?.start_time), displayValue: formatAnyDateTime(trace?.start_time || span?.start_time) },
  { label: "Ended", value: traceValueOrDash(trace?.end_time || span?.end_time), displayValue: formatAnyDateTime(trace?.end_time || span?.end_time) },
  { label: "Run Updated", value: traceValueOrDash(run?.updated_at), displayValue: formatAnyDateTime(run?.updated_at) },
]

export const buildTraceToolCallItems = (spans: SpanItem[]): TraceToolCallItem[] => spans
  .filter((span) => isTraceToolSpan(span))
  .map((span) => {
    const parsed = span.parsed || emptyParsedSpan
    return {
      id: span.span_id,
      name: parsed.metadata?.tool || span.name || "Tool",
      status: span.status_code,
      durationMs: span.duration_ms,
      arguments: formatTracePayloadText(parsed.input, "No arguments captured"),
      response: formatTracePayloadText(parsed.output, "No response captured"),
      metadata: prettyTraceJson({
        span_id: span.span_id,
        kind: span.kind,
        operation: parsed.metadata?.operation,
        attributes: span.attributes || {},
      }),
    }
  })

export const buildTraceLogItems = ({
  parsedEvents,
  rawEvents,
}: BuildTraceLogItemsParams): TraceLogItem[] => {
  const rawItems = (rawEvents || []).map((event, index) => {
    if (event && typeof event === "object") {
      const record = event as Record<string, unknown>
      return {
        name: traceValueOrDash(record.name || `event-${index + 1}`),
        message: traceValueOrDash(record.message || record.body || record.attributes || event),
      }
    }
    return { name: `event-${index + 1}`, message: traceValueOrDash(event) }
  })
  return parsedEvents.length ? parsedEvents : rawItems
}
