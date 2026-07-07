import assert from "node:assert/strict"
import {
  agentOsScheduleRunsToScheduleRunsResponse,
  agentOsSchedulesToOsControlResponse,
  buildAgentOsScheduleCreateBody,
  buildAgentOsScheduleUpdateBody,
} from "./schedulerAgentOsApi.ts"

const scheduleList = {
  data: [
    {
      id: "schedule-1",
      name: "Nightly research",
      description: "Run research agent",
      method: "POST",
      endpoint: "/agents/research-agent/runs",
      payload: { message: "Summarize the queue" },
      cron_expr: "0 2 * * *",
      timezone: "UTC",
      timeout_seconds: 120,
      max_retries: 2,
      retry_delay_seconds: 30,
      enabled: true,
      next_run_at: 1767223200,
      created_at: 1767136800,
      updated_at: 1767136900,
    },
    {
      id: "schedule-2",
      name: "Workflow cleanup",
      method: "POST",
      endpoint: "/workflows/cleanup/runs",
      payload: null,
      cron_expr: "15 * * * *",
      timezone: "Asia/Shanghai",
      timeout_seconds: 3600,
      max_retries: 0,
      retry_delay_seconds: 60,
      enabled: false,
    },
  ],
}

const payload = agentOsSchedulesToOsControlResponse(scheduleList, "2026-01-01T00:00:00.000Z")

assert.equal(payload.module, "scheduler")
assert.equal(payload.status, "ready")
assert.equal(payload.generated_at, "2026-01-01T00:00:00.000Z")
assert.equal(payload.schedules?.length, 2)
assert.equal(payload.metrics[0]?.value, 2)
assert.equal(payload.metrics[1]?.value, 1)
assert.equal(payload.metrics[2]?.value, 1)
assert.equal(payload.schedules?.[0]?.target_type, "agent")
assert.equal(payload.schedules?.[0]?.target_id, "research-agent")
assert.equal(payload.schedules?.[0]?.next_run_at_iso, "2025-12-31T23:20:00.000Z")
assert.equal(payload.schedules?.[1]?.target_type, "workflow")
assert.deepEqual(payload.schedules?.[1]?.payload, {})
assert.equal(payload.records[0]?.subtitle, "/agents/research-agent/runs")
assert.equal(payload.records[1]?.status, "disabled")

assert.deepEqual(
  buildAgentOsScheduleCreateBody({
    name: "Team digest",
    target_type: "team",
    target_id: "security-team",
    cron_expr: "*/10 * * * *",
    description: "  Team run  ",
    payload: { message: "digest" },
    timeout_seconds: 45,
    max_retries: 1,
    retry_delay_seconds: 5,
    enabled: false,
  }),
  {
    name: "Team digest",
    cron_expr: "*/10 * * * *",
    endpoint: "/teams/security-team/runs",
    method: "POST",
    description: "Team run",
    payload: { message: "digest" },
    timezone: "UTC",
    timeout_seconds: 45,
    max_retries: 1,
    retry_delay_seconds: 5,
  },
)

assert.throws(
  () => buildAgentOsScheduleCreateBody({
    name: "Bad",
    target_type: "agent",
    target_id: "nested/id",
    cron_expr: "* * * * *",
  }),
  /target_id/,
)

assert.deepEqual(
  buildAgentOsScheduleUpdateBody({
    description: "  ",
    target_type: "workflow",
    target_id: "daily-check",
    payload: { message: "check" },
  }),
  {
    description: null,
    payload: { message: "check" },
    endpoint: "/workflows/daily-check/runs",
    method: "POST",
  },
)

const runs = agentOsScheduleRunsToScheduleRunsResponse({
  data: [
    {
      id: "run-1",
      schedule_id: "schedule-1",
      attempt: 2,
      triggered_at: 1767223200,
      completed_at: 1767223260,
      status: "success",
      status_code: 200,
      run_id: "agent-run-1",
      input: { message: "go" },
      output: { ok: true },
      requirements: [{ scope: "agents:run" }, "ignored"],
      created_at: 1767223199,
    },
  ],
  meta: { page: 3, limit: 25 },
})

assert.equal(runs.page, 3)
assert.equal(runs.limit, 25)
assert.equal(runs.items[0]?.triggered_at_iso, "2025-12-31T23:20:00.000Z")
assert.deepEqual(runs.items[0]?.requirements, [{ scope: "agents:run" }])
