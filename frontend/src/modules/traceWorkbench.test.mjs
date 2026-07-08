import assert from "node:assert/strict"
import {
  buildTraceStoreFilters,
  buildTraceListParams,
  buildTraceLogItems,
  buildTraceMetadataItems,
  buildTraceOverviewItems,
  buildTraceRunRows,
  buildTraceSummaryCards,
  buildTraceToolCallItems,
  clampTraceSessionPage,
  compactTraceId,
  createTraceRunFilters,
  createTraceSessionFilters,
  emptyTraceParsedSpan,
  formatTraceAnyDateTime,
  formatTraceCost,
  formatTraceDateTime,
  formatTraceDuration,
  formatTracePayloadText,
  formatTraceSessionTime,
  filterTraceRunRows,
  filterTraceSessions,
  ensureTraceSession,
  findExactTraceSession,
  findFirstTraceSpan,
  findTraceRunRow,
  isTraceJsonPayload,
  isTraceToolSpan,
  mergePreferredTraceItem,
  normalizeTraceSessionOpenRequest,
  pageTraceSessions,
  resolveTraceSessionSelection,
  traceRunMetrics,
  traceDurationClass,
  tracePayloadTextForMode,
  traceStatusClass,
  traceStatusLabel,
  traceTagType,
  traceDetailTabForSection,
  traceValueOrDash,
  prettyTraceJson,
  summarizeTraceItems,
} from "./traceWorkbench.ts"

const sessionA = {
  session_id: "session-alpha",
  user_id: "user-1",
  preview: "Investigate CVE-2026",
  created_at: 1,
  updated_at: 2,
  archived: false,
  runs: [
    {
      run_id: "run-1",
      agent_id: "agent-from-run",
      agent_name: "SOC Agent",
      metrics: { total_tokens: 42, cost: 0.003 },
    },
    {
      run_id: "run-2",
      team_id: "team-from-run",
      agent_name: "Team Agent",
    },
  ],
}

const sessionB = {
  session_id: "session-archived",
  user_id: "user-2",
  preview: "Old incident",
  created_at: 3,
  updated_at: 4,
  archived: true,
  runs: [],
}

const traceA = {
  trace_id: "trace-a",
  name: "",
  status: "OK",
  duration_ms: 1200,
  start_time: "2026-01-01T00:00:00Z",
  end_time: "2026-01-01T00:00:01Z",
  total_spans: 3,
  run_id: "run-1",
  session_id: "session-alpha",
}

const traceB = {
  trace_id: "trace-b",
  name: "Workflow trace",
  status: "ERROR",
  duration_ms: 300,
  start_time: "2026-01-01T00:01:00Z",
  end_time: "2026-01-01T00:01:01Z",
  total_spans: 2,
  error_count: 4,
  run_id: "run-2",
  session_id: "session-alpha",
  workflow_id: "workflow-from-trace",
}

const sessions = [sessionA, sessionB]

assert.deepEqual(
  filterTraceSessions(sessions, {
    sessionId: "",
    userId: "",
    keyword: "cve",
    status: "active",
  }).map((session) => session.session_id),
  ["session-alpha"],
  "session filters should combine archive status and keyword matching",
)

assert.deepEqual(
  createTraceSessionFilters(),
  {
    sessionId: "",
    userId: "",
    keyword: "",
    status: "active",
  },
  "session filter defaults should live outside the Vue component",
)

assert.deepEqual(
  createTraceRunFilters(),
  {
    runId: "",
    agentId: "",
    teamId: "",
    workflowId: "",
    status: "",
  },
  "run filter defaults should live outside the Vue component",
)

assert.deepEqual(
  filterTraceSessions({ items: sessions }, {
    sessionId: "",
    userId: "",
    keyword: "",
    status: "active",
  }),
  [],
  "session filters should ignore non-array responses instead of crashing the view",
)

assert.deepEqual(
  pageTraceSessions(sessions, 2, 1).map((session) => session.session_id),
  ["session-archived"],
  "session pagination should keep slicing logic outside the Vue component",
)

assert.equal(
  clampTraceSessionPage(3, 12, 5),
  3,
  "session pagination should keep the current page when it remains in range",
)

assert.equal(
  clampTraceSessionPage(9, 12, 5),
  3,
  "session pagination should clamp pages that exceed the visible session count",
)

assert.equal(
  findExactTraceSession(sessions, " SESSION-ALPHA ")?.session_id,
  "session-alpha",
  "exact session lookup should ignore case and surrounding whitespace",
)

const rows = buildTraceRunRows({
  traces: [traceA, traceB],
  selectedSession: sessionA,
  selectedSessionId: sessionA.session_id,
  labels: {
    agentId: "Agent",
    teamId: "Team",
    workflowId: "Workflow",
  },
})

assert.deepEqual(
  rows.map((row) => ({
    key: row.key,
    title: row.title,
    ownerId: row.ownerId,
    ownerLabel: row.ownerLabel,
  })),
  [
    {
      key: "trace-a",
      title: "SOC Agent",
      ownerId: "agent-from-run",
      ownerLabel: "Agent",
    },
    {
      key: "trace-b",
      title: "Workflow trace",
      ownerId: "workflow-from-trace",
      ownerLabel: "Team",
    },
  ],
  "run rows should merge Trace and Chat Session Run ownership consistently",
)

assert.deepEqual(
  filterTraceRunRows(rows, {
    runId: "",
    agentId: "",
    teamId: "team-from-run",
    workflowId: "",
    status: "ERROR",
  }).map((row) => row.key),
  ["trace-b"],
  "run filters should match merged Trace and Run fields",
)

assert.equal(
  findTraceRunRow(rows, " trace-b ")?.key,
  "trace-b",
  "selected run row lookup should normalize external trace ids",
)

assert.equal(
  findTraceRunRow(rows, null),
  null,
  "selected run row lookup should ignore empty trace ids",
)

assert.deepEqual(
  traceRunMetrics(rows[0]),
  { total_tokens: 42, cost: 0.003 },
  "run metrics should expose only object metrics from the selected run row",
)

assert.deepEqual(
  traceRunMetrics({ ...rows[0], run: { metrics: "not-object" } }),
  {},
  "run metrics should ignore non-object metric payloads",
)

assert.deepEqual(
  buildTraceListParams({
    session: sessionA,
    filters: {
      runId: "",
      agentId: "agent-1",
      teamId: "",
      workflowId: "workflow-1",
      status: "ERROR",
    },
  }),
  {
    page: 1,
    limit: 50,
    session_id: "session-alpha",
    user_id: "user-1",
    agent_id: "agent-1",
    team_id: undefined,
    workflow_id: "workflow-1",
    status: "ERROR",
  },
  "trace list params should keep API filter construction outside the Vue component",
)

assert.deepEqual(
  buildTraceStoreFilters({
    session: sessionA,
    runId: "run-1",
    filters: {
      runId: "",
      agentId: "agent-1",
      teamId: "",
      workflowId: "workflow-1",
      status: "ERROR",
    },
  }),
  {
    session_id: "session-alpha",
    run_id: "run-1",
    user_id: "user-1",
    agent_id: "agent-1",
    team_id: "",
    workflow_id: "workflow-1",
    status: "ERROR",
  },
  "trace store filters should preserve empty-string filter values used by the store",
)

assert.deepEqual(
  mergePreferredTraceItem([traceA, traceB], { ...traceB, name: "Preferred trace" }).map((trace) => trace.name),
  ["Preferred trace", ""],
  "preferred trace merge should place the exact match first and remove duplicate trace ids",
)

assert.deepEqual(
  resolveTraceSessionSelection({
    visibleSessions: [sessionA],
    selectedSessionId: "session-alpha",
    selectedSession: sessionA,
    requestedSessionId: "",
  }),
  {
    keepCurrent: true,
    nextSession: null,
    nextSessionId: "session-alpha",
    shouldClearSelection: false,
  },
  "session reconcile should keep the current selected session when it is still visible",
)

assert.deepEqual(
  resolveTraceSessionSelection({
    visibleSessions: [sessionA],
    selectedSessionId: "missing",
    selectedSession: null,
    requestedSessionId: " SESSION-ALPHA ",
  }),
  {
    keepCurrent: false,
    nextSession: sessionA,
    nextSessionId: "session-alpha",
    shouldClearSelection: true,
  },
  "session reconcile should prefer an exact requested session before singleton fallback",
)

assert.deepEqual(
  normalizeTraceSessionOpenRequest(" session-new ", null, " run-9 "),
  {
    sessionId: "session-new",
    userId: null,
    userFilter: "",
    runId: "run-9",
  },
  "external session open requests should normalize ids while preserving explicit empty user filters",
)

assert.equal(
  normalizeTraceSessionOpenRequest("   ", undefined, "run-9"),
  null,
  "external session open requests should ignore empty session ids",
)

assert.deepEqual(
  ensureTraceSession(sessions, {
    sessionId: "session-new",
    userId: "user-new",
    userFilter: "user-new",
    runId: "",
  }),
  {
    session: {
      session_id: "session-new",
      user_id: "user-new",
      preview: "session-new",
      created_at: 0,
      updated_at: 0,
      archived: false,
      archived_at: null,
      runs: [],
    },
    sessions: [
      {
        session_id: "session-new",
        user_id: "user-new",
        preview: "session-new",
        created_at: 0,
        updated_at: 0,
        archived: false,
        archived_at: null,
        runs: [],
      },
      ...sessions,
    ],
  },
  "external session open should create a visible placeholder when the session is not in the latest list",
)

assert.deepEqual(
  summarizeTraceItems([traceA, traceB], 10),
  {
    totalTraces: 10,
    totalSpans: 5,
    errors: 4,
    avgLatencyMs: 750,
    sampleSize: 2,
  },
  "summary should use backend total count and sampled Trace metrics",
)

assert.deepEqual(
  buildTraceSummaryCards({
    sessions,
    visibleSessionCount: 1,
    summary: summarizeTraceItems([traceA, traceB], 10),
    formatLatencySeconds: (durationMs) => `${durationMs / 1000}s`,
    latencyTone: (durationMs) => durationMs > 500 ? "yellow" : "green",
  }),
  [
    { label: "Sessions", value: 2, hint: "1 visible sessions", tone: "blue" },
    { label: "Traces", value: 10, hint: "2 sampled traces", tone: "green" },
    { label: "Spans", value: 5, hint: "Spans observed in sampled traces", tone: "blue" },
    { label: "Errors", value: 4, hint: "Trace or span errors in sampled traces", tone: "red" },
    { label: "Avg Latency(s)", value: "0.75s", hint: "Average trace duration in sampled traces", tone: "yellow" },
  ],
  "summary cards should keep view copy and tone derivation behind one interface",
)

assert.deepEqual(
  [
    traceTagType("OK"),
    traceTagType("ERROR"),
    traceTagType("UNSET"),
    traceStatusClass("UNSET"),
    traceStatusLabel(""),
  ],
  ["success", "danger", "info", "unset", "-"],
  "status presentation helpers should keep Element Plus tag types and labels consistent",
)

assert.deepEqual(
  [
    traceDetailTabForSection("metadata"),
    traceDetailTabForSection("overview"),
    traceDetailTabForSection("logs"),
    traceDetailTabForSection("input"),
  ],
  ["metadata", "overview", "info", "info"],
  "detail section mapping should keep tab selection logic outside the Vue component",
)

assert.deepEqual(
  [
    traceDurationClass(5),
    traceDurationClass(1500),
    traceDurationClass(15000),
    formatTraceDuration(5),
    formatTraceDuration(75),
    formatTraceDuration(1200),
    formatTraceDuration(65_500),
    formatTraceDuration(-1),
  ],
  [
    "duration-fast",
    "duration-medium",
    "duration-critical",
    "5.00 ms",
    "75.0 ms",
    "1.20 s",
    "1m 5.5s",
    "-",
  ],
  "duration helpers should preserve trace latency display buckets",
)

assert.deepEqual(
  [
    compactTraceId("1234567890abcdef123456"),
    compactTraceId(""),
    traceValueOrDash(null),
    traceValueOrDash("value"),
    formatTraceCost(0.00321),
    formatTraceCost(2.5),
    prettyTraceJson({ ok: true }),
  ],
  [
    "12345678...3456",
    "-",
    "-",
    "value",
    "$0.00321",
    "$2.50",
    "{\n  \"ok\": true\n}",
  ],
  "general presentation helpers should stay pure and stable",
)

const zhDateTimeOptions = {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
}

assert.deepEqual(
  [
    formatTraceDateTime(null),
    formatTraceDateTime("not-a-date"),
    formatTraceDateTime("2026-01-01T00:00:00Z"),
    formatTraceAnyDateTime(1_767_225_600),
    formatTraceAnyDateTime(1_767_225_600_000),
    formatTraceAnyDateTime(""),
    formatTraceSessionTime(1_767_225_600),
  ],
  [
    "-",
    "not-a-date",
    new Date("2026-01-01T00:00:00Z").toLocaleString("zh-CN", zhDateTimeOptions),
    new Date(1_767_225_600_000).toLocaleString("zh-CN", zhDateTimeOptions),
    new Date(1_767_225_600_000).toLocaleString("zh-CN", zhDateTimeOptions),
    "-",
    new Date(1_767_225_600_000).toLocaleString("zh-CN", zhDateTimeOptions),
  ],
  "trace date helpers should preserve existing zh-CN minute-level display behavior",
)

const jsonPayload = { format: "text", text: "{\"a\":1}", data: null }
const dataPayload = { format: "json", text: "raw fallback", data: { answer: 42 } }
const plainPayload = { format: "text", text: "hello", data: null }

assert.equal(isTraceJsonPayload(jsonPayload), true, "JSON-looking text payloads should be detected")
assert.equal(isTraceJsonPayload(plainPayload), false, "plain text payloads should not be treated as JSON")
assert.equal(
  formatTracePayloadText(dataPayload, "fallback"),
  "{\n  \"answer\": 42\n}",
  "payload formatter should prefer structured data when present",
)
assert.equal(
  tracePayloadTextForMode(plainPayload, "json", "fallback"),
  "hello",
  "JSON view should fall back to raw text for non-JSON payloads",
)

assert.equal(
  isTraceToolSpan({
    span_id: "span-tool",
    name: "call_function",
    kind: "internal",
    status_code: "OK",
    duration_ms: 10,
    parsed: {
      metadata: { tool: "", operation: "invoke" },
    },
  }),
  true,
  "tool span detection should use span metadata, kind and name",
)

const parsedSpan = {
  input: { format: "json", text: "{\"topic\":\"risk\"}", data: null },
  output: { format: "json", text: "{\"ok\":true}", data: null },
  metadata: {
    model: "gpt-test",
    provider: "openai",
    tool: "risk_lookup",
    operation: "invoke",
    tokens: {
      prompt: 9,
      completion: 4,
      total: 13,
    },
  },
  events: [{ name: "parsed", message: "ready" }],
}

assert.deepEqual(
  emptyTraceParsedSpan,
  {
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
  },
  "empty parsed span shape should be shared by the workbench and Vue component",
)

const selectedSpan = {
  span_id: "span-1234567890abcdef",
  trace_id: "trace-a",
  parent_span_id: "span-parent-123456",
  name: "call_function",
  status_code: "ERROR",
  status_message: "Tool failed",
  duration_ms: 321,
  start_time: "2026-01-01T00:00:00Z",
  end_time: "2026-01-01T00:00:01Z",
  attributes: { retry: false },
  events: [{ name: "raw", message: "unused" }],
  kind: "internal",
  parsed: parsedSpan,
}

assert.equal(
  findFirstTraceSpan([{ span: selectedSpan, children: [] }], []),
  selectedSpan,
  "first span selection should prefer the tree root span",
)

assert.deepEqual(
  buildTraceOverviewItems({
    trace: traceB,
    run: rows[1].run,
    span: selectedSpan,
    parsedSpan,
    metrics: { input_tokens: 10, output_tokens: 5, cost: 0.002 },
  }).map((item) => [item.label, item.value, item.displayValue, item.tone]),
  [
    ["Status", "ERROR", "Error", "error"],
    ["Duration", "300 ms", "300 ms", ""],
    ["Input Tokens", "10", "10", ""],
    ["Output Tokens", "5", "5", ""],
    ["Tokens", "13", "13", ""],
    ["Model", "gpt-test", "gpt-test", ""],
    ["Provider", "openai", "openai", ""],
    ["Agent", "Team Agent", "Team Agent", ""],
    ["Workflow", "workflow-from-trace", "workflow...race", ""],
    ["Team", "team-from-run", "team-from-run", ""],
    ["Cost", "$0.00200", "$0.00200", ""],
    ["Error", "Tool failed", "Tool failed", "error"],
  ],
  "overview builder should merge trace, run, span metadata and metrics for the details panel",
)

assert.deepEqual(
  buildTraceMetadataItems({
    trace: traceB,
    run: rows[1].run,
    session: sessionA,
    row: rows[1],
    span: selectedSpan,
    formatAnyDateTime: (value) => `date:${value}`,
  }).map((item) => [item.label, item.value, item.displayValue]),
  [
    ["Session ID", "session-alpha", "session-alpha"],
    ["User ID", "user-1", "user-1"],
    ["Run ID", "run-2", "run-2"],
    ["Trace ID", "trace-b", "trace-b"],
    ["Span ID", "span-1234567890abcdef", "span-123...cdef"],
    ["Parent Span", "span-parent-123456", "span-parent-123456"],
    ["Created", "-", "date:undefined"],
    ["Started", "2026-01-01T00:01:00Z", "date:2026-01-01T00:01:00Z"],
    ["Ended", "2026-01-01T00:01:01Z", "date:2026-01-01T00:01:01Z"],
    ["Run Updated", "-", "date:undefined"],
  ],
  "metadata builder should keep detail identifiers and date display formatting in one module path",
)

assert.deepEqual(
  buildTraceToolCallItems([selectedSpan])[0],
  {
    id: "span-1234567890abcdef",
    name: "risk_lookup",
    status: "ERROR",
    durationMs: 321,
    arguments: "{\n  \"topic\": \"risk\"\n}",
    response: "{\n  \"ok\": true\n}",
    metadata: "{\n  \"span_id\": \"span-1234567890abcdef\",\n  \"kind\": \"internal\",\n  \"operation\": \"invoke\",\n  \"attributes\": {\n    \"retry\": false\n  }\n}",
  },
  "tool call builder should format arguments, responses and span metadata consistently",
)

assert.deepEqual(
  buildTraceLogItems({
    parsedEvents: [],
    rawEvents: [{ body: "raw body" }, "plain"],
  }),
  [
    { name: "event-1", message: "raw body" },
    { name: "event-2", message: "plain" },
  ],
  "log builder should fall back to raw span events when parsed events are unavailable",
)
