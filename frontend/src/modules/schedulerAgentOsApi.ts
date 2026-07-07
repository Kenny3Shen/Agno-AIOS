import type {
  OsControlResponse,
  ScheduleCreateRequest,
  ScheduleRunsResponse,
  ScheduleTargetType,
  ScheduleUpdateRequest,
  SchedulerRun,
  SchedulerSchedule,
} from '../types'

const scheduleEndpointPrefixes = {
  agent: 'agents',
  team: 'teams',
  workflow: 'workflows',
} as const

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const stringValue = (value: unknown, fallback = '') => {
  return typeof value === 'string' ? value : fallback
}

const numberValue = (value: unknown): number | null => {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

const intValue = (value: unknown, fallback: number) => {
  return typeof value === 'number' && Number.isFinite(value) ? Math.trunc(value) : fallback
}

const epochIso = (value: unknown) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return ''
  return new Date(value * 1000).toISOString()
}

const parseScheduleEndpoint = (endpoint: string): [ScheduleTargetType | '', string] => {
  const parts = endpoint.trim().replace(/^\/+|\/+$/g, '').split('/')
  if (parts.length !== 3 || parts[2] !== 'runs') return ['', '']
  const entry = Object.entries(scheduleEndpointPrefixes).find(([, prefix]) => prefix === parts[0])
  return entry ? [entry[0] as ScheduleTargetType, parts[1]] : ['', '']
}

const buildScheduleEndpoint = (targetType: ScheduleTargetType, targetId: string) => {
  const cleanId = targetId.trim().replace(/^\/+|\/+$/g, '')
  if (!cleanId || cleanId.includes('/') || cleanId.includes('://')) {
    throw new Error('target_id must be a non-empty Agno resource id')
  }
  return `/${scheduleEndpointPrefixes[targetType]}/${cleanId}/runs`
}

const paginatedData = (value: unknown) => {
  if (isRecord(value) && Array.isArray(value.data)) return value.data
  return Array.isArray(value) ? value : []
}

const paginatedMeta = (value: unknown) => {
  return isRecord(value) && isRecord(value.meta) ? value.meta : {}
}

export const normalizeAgentOsSchedule = (value: unknown): SchedulerSchedule => {
  const record = isRecord(value) ? value : {}
  const endpoint = stringValue(record.endpoint)
  const [target_type, target_id] = parseScheduleEndpoint(endpoint)
  const payload = isRecord(record.payload) ? record.payload : {}
  const nextRunAt = numberValue(record.next_run_at)
  const createdAt = numberValue(record.created_at)
  const updatedAt = numberValue(record.updated_at)

  return {
    id: stringValue(record.id),
    name: stringValue(record.name),
    description: typeof record.description === 'string' ? record.description : null,
    method: stringValue(record.method, 'POST'),
    endpoint,
    target_type,
    target_id,
    payload,
    cron_expr: stringValue(record.cron_expr),
    timezone: stringValue(record.timezone, 'UTC'),
    timeout_seconds: intValue(record.timeout_seconds, 3600),
    max_retries: intValue(record.max_retries, 0),
    retry_delay_seconds: intValue(record.retry_delay_seconds, 60),
    enabled: Boolean(record.enabled),
    next_run_at: nextRunAt,
    next_run_at_iso: epochIso(nextRunAt),
    created_at: createdAt,
    created_at_iso: epochIso(createdAt),
    updated_at: updatedAt,
    updated_at_iso: epochIso(updatedAt),
  }
}

export const normalizeAgentOsScheduleRun = (value: unknown): SchedulerRun => {
  const record = isRecord(value) ? value : {}
  const triggeredAt = numberValue(record.triggered_at)
  const completedAt = numberValue(record.completed_at)
  const createdAt = numberValue(record.created_at)

  return {
    id: stringValue(record.id),
    schedule_id: stringValue(record.schedule_id),
    attempt: intValue(record.attempt, 1),
    triggered_at: triggeredAt,
    triggered_at_iso: epochIso(triggeredAt),
    completed_at: completedAt,
    completed_at_iso: epochIso(completedAt),
    status: stringValue(record.status),
    status_code: numberValue(record.status_code),
    run_id: typeof record.run_id === 'string' ? record.run_id : null,
    session_id: typeof record.session_id === 'string' ? record.session_id : null,
    error: typeof record.error === 'string' ? record.error : null,
    input: isRecord(record.input) ? record.input : null,
    output: isRecord(record.output) ? record.output : null,
    requirements: Array.isArray(record.requirements) ? record.requirements.filter(isRecord) : null,
    created_at: createdAt,
    created_at_iso: epochIso(createdAt),
  }
}

export const buildAgentOsScheduleCreateBody = (payload: ScheduleCreateRequest): Record<string, unknown> => {
  return {
    name: payload.name,
    cron_expr: payload.cron_expr,
    endpoint: buildScheduleEndpoint(payload.target_type, payload.target_id),
    method: 'POST',
    description: payload.description?.trim() || null,
    payload: payload.payload ?? {},
    timezone: payload.timezone || 'UTC',
    timeout_seconds: payload.timeout_seconds ?? 3600,
    max_retries: payload.max_retries ?? 0,
    retry_delay_seconds: payload.retry_delay_seconds ?? 60,
  }
}

export const buildAgentOsScheduleUpdateBody = (payload: ScheduleUpdateRequest): Record<string, unknown> => {
  const body: Record<string, unknown> = {}
  if (payload.name !== undefined) body.name = payload.name
  if (payload.cron_expr !== undefined) body.cron_expr = payload.cron_expr
  if (payload.description !== undefined) body.description = payload.description.trim() || null
  if (payload.payload !== undefined) body.payload = payload.payload
  if (payload.timezone !== undefined) body.timezone = payload.timezone
  if (payload.timeout_seconds !== undefined) body.timeout_seconds = payload.timeout_seconds
  if (payload.max_retries !== undefined) body.max_retries = payload.max_retries
  if (payload.retry_delay_seconds !== undefined) body.retry_delay_seconds = payload.retry_delay_seconds
  if (payload.target_type !== undefined || payload.target_id !== undefined) {
    if (!payload.target_type || !payload.target_id) {
      throw new Error('target_type and target_id must be updated together')
    }
    body.endpoint = buildScheduleEndpoint(payload.target_type, payload.target_id)
    body.method = 'POST'
  }
  return body
}

const schedulerPayloadFromSchedules = (
  schedules: SchedulerSchedule[],
  generatedAt: string,
): OsControlResponse => {
  const enabled = schedules.filter((schedule) => schedule.enabled).length
  const disabled = schedules.length - enabled
  return {
    module: 'scheduler',
    title: 'Scheduler',
    description: 'Agno Scheduler cron jobs and run history.',
    status: 'ready',
    metrics: [
      { label: 'Schedules', value: schedules.length, hint: 'Agno schedule rows', tone: 'blue' },
      { label: 'Enabled', value: enabled, hint: 'Enabled schedules', tone: enabled ? 'green' : 'yellow' },
      { label: 'Disabled', value: disabled, hint: 'Disabled schedules', tone: 'yellow' },
    ],
    records: schedules.map((schedule) => ({
      id: schedule.id,
      title: schedule.name,
      subtitle: schedule.endpoint,
      status: schedule.enabled ? 'enabled' : 'disabled',
      meta: {
        description: schedule.description,
        target_type: schedule.target_type,
        target_id: schedule.target_id,
        endpoint: schedule.endpoint,
        cron_expr: schedule.cron_expr,
        timezone: schedule.timezone,
        next_run_at: schedule.next_run_at_iso,
        timeout_seconds: schedule.timeout_seconds,
        max_retries: schedule.max_retries,
        retry_delay_seconds: schedule.retry_delay_seconds,
        payload: schedule.payload,
      },
      updated_at: schedule.updated_at_iso || schedule.created_at_iso,
    })),
    schedules,
    generated_at: generatedAt,
  }
}

export const agentOsSchedulesToOsControlResponse = (
  value: unknown,
  generatedAt = new Date().toISOString(),
): OsControlResponse => {
  return schedulerPayloadFromSchedules(paginatedData(value).map(normalizeAgentOsSchedule), generatedAt)
}

export const agentOsScheduleRunsToScheduleRunsResponse = (value: unknown): ScheduleRunsResponse => {
  const meta = paginatedMeta(value)
  const items = paginatedData(value).map(normalizeAgentOsScheduleRun)
  return {
    items,
    page: intValue(meta.page, 1),
    limit: intValue(meta.limit, items.length || 100),
  }
}
