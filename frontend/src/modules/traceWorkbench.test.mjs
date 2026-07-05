import assert from "node:assert/strict"
import {
  buildTraceRunRows,
  buildTraceSummaryCards,
  filterTraceRunRows,
  filterTraceSessions,
  findExactTraceSession,
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
  filterTraceSessions({ items: sessions }, {
    sessionId: "",
    userId: "",
    keyword: "",
    status: "active",
  }),
  [],
  "session filters should ignore non-array responses instead of crashing the view",
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
