/**
 * Workflow Studio HTTP client (CRUD, templates, run SSE, cancel).
 * Pure transport: no React state. Parsing stays aligned with Agno-style envelopes.
 */
import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import { consumeSse } from '@/features/chat/utils'
import type {
  ExecutorOption,
  WorkflowDefinition,
  WorkflowDefinitionNode,
  WorkflowNodePreset,
  WorkflowNodeType,
  WorkflowRecord,
  WorkflowRunLogItem,
} from './types'

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null

const isNonNegativeInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

const isWorkflowHistoryId = (value: unknown): value is string | number =>
  (typeof value === 'string' && Boolean(value.trim())) ||
  (typeof value === 'number' && Number.isFinite(value))

type WorkflowChoice = NonNullable<WorkflowDefinitionNode['choices']>[number]
type WorkflowParseLabel = 'workflow payload' | 'workflow definition'

const workflowNodeTypes = new Set<WorkflowNodeType>([
  'step',
  'parallel',
  'condition',
  'loop',
  'router',
  'workflow_ref',
])

const invalidWorkflowValue = (context: string, label: WorkflowParseLabel): never => {
  throw new Error(`${context}: invalid ${label}`)
}

const requireWorkflowRecord = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): Record<string, unknown> => {
  const row = asRecord(value)
  if (!row) return invalidWorkflowValue(context, label)
  return row
}

const requireWorkflowString = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): string => {
  if (typeof value !== 'string') return invalidWorkflowValue(context, label)
  return value
}

const requireWorkflowIdentifier = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): string => {
  const text = requireWorkflowString(value, context, label)
  if (!text.trim()) return invalidWorkflowValue(context, label)
  return text
}

const requireWorkflowNumber = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): number => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return invalidWorkflowValue(context, label)
  }
  return value
}

const requireWorkflowInteger = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): number => {
  const number = requireWorkflowNumber(value, context, label)
  if (!Number.isInteger(number) || number < 0) return invalidWorkflowValue(context, label)
  return number
}

const optionalWorkflowString = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): string | undefined => {
  if (value === undefined) return undefined
  return requireWorkflowString(value, context, label)
}

const optionalWorkflowPosition = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): WorkflowDefinitionNode['position'] => {
  if (value === undefined) return undefined
  const row = requireWorkflowRecord(value, context, label)
  return {
    x: requireWorkflowNumber(row.x, context, label),
    y: requireWorkflowNumber(row.y, context, label),
  }
}

const optionalWorkflowSkills = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): string[] | undefined => {
  if (value === undefined) return undefined
  if (!Array.isArray(value)) return invalidWorkflowValue(context, label)
  return value.map((skill) => requireWorkflowIdentifier(skill, context, label))
}

const optionalUserInputSchema = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): NonNullable<WorkflowDefinitionNode['user_input_schema']> | undefined => {
  if (value === undefined) return undefined
  if (!Array.isArray(value)) return invalidWorkflowValue(context, label)
  return value.map((field) => {
    const row = requireWorkflowRecord(field, context, label)
    const description = optionalWorkflowString(row.description, context, label)
    if (typeof row.required !== 'boolean') return invalidWorkflowValue(context, label)
    return {
      name: requireWorkflowIdentifier(row.name, context, label),
      field_type: requireWorkflowIdentifier(row.field_type, context, label),
      required: row.required,
      ...(description === undefined ? {} : { description }),
    }
  })
}

const parseWorkflowExecutor = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): NonNullable<WorkflowDefinitionNode['executor']> => {
  const row = requireWorkflowRecord(value, context, label)
  if (row.kind !== 'agent') return invalidWorkflowValue(context, label)
  return {
    kind: 'agent',
    ref: requireWorkflowIdentifier(row.ref, context, label),
  }
}

const parseWorkflowEvaluator = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): NonNullable<WorkflowDefinitionNode['evaluator']> => {
  const row = requireWorkflowRecord(value, context, label)
  if (typeof row.cel === 'string' && row.cel.trim() && row.value === undefined) {
    return { cel: row.cel }
  }
  if (typeof row.value === 'boolean' && row.cel === undefined) {
    return { value: row.value }
  }
  return invalidWorkflowValue(context, label)
}

function parseWorkflowNodeList(
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
  minimumLength: number,
): WorkflowDefinitionNode[] {
  if (!Array.isArray(value) || value.length < minimumLength) {
    return invalidWorkflowValue(context, label)
  }
  return value.map((node) => parseWorkflowNode(node, context, label))
}

function parseWorkflowChoices(
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): WorkflowChoice[] {
  if (!Array.isArray(value) || value.length < 2) return invalidWorkflowValue(context, label)
  return value.map((choice) => {
    const row = requireWorkflowRecord(choice, context, label)
    return {
      id: requireWorkflowIdentifier(row.id, context, label),
      name: requireWorkflowIdentifier(row.name, context, label),
      steps: parseWorkflowNodeList(row.steps, context, label, 1),
    }
  })
}

function parseWorkflowNode(
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): WorkflowDefinitionNode {
  const row = requireWorkflowRecord(value, context, label)
  const type = requireWorkflowIdentifier(row.type, context, label)
  if (!workflowNodeTypes.has(type as WorkflowNodeType)) return invalidWorkflowValue(context, label)
  const position = optionalWorkflowPosition(row.position, context, label)
  const common = {
    id: requireWorkflowIdentifier(row.id, context, label),
    type: type as WorkflowNodeType,
    name: requireWorkflowIdentifier(row.name, context, label),
    ...(position === undefined ? {} : { position }),
  }

  if (type === 'step') {
    const confirmationMessage = optionalWorkflowString(row.confirmation_message, context, label)
    const userInputMessage = optionalWorkflowString(row.user_input_message, context, label)
    const outputReviewMessage = optionalWorkflowString(row.output_review_message, context, label)
    const skills = optionalWorkflowSkills(row.skills, context, label)
    const userInputSchema = optionalUserInputSchema(row.user_input_schema, context, label)
    // Sparse definitions (templates + toDefinition) omit false HITL flags.
    const requiresConfirmation =
      row.requires_confirmation === undefined ? false : row.requires_confirmation
    const requiresUserInput =
      row.requires_user_input === undefined ? false : row.requires_user_input
    const requiresOutputReview =
      row.requires_output_review === undefined ? false : row.requires_output_review
    if (
      typeof requiresConfirmation !== 'boolean' ||
      typeof requiresUserInput !== 'boolean' ||
      typeof requiresOutputReview !== 'boolean'
    ) {
      return invalidWorkflowValue(context, label)
    }
    return {
      ...common,
      type: 'step',
      executor: parseWorkflowExecutor(row.executor, context, label),
      // Templates may omit empty instructions; treat missing as "".
      instructions: requireWorkflowString(
        row.instructions === undefined ? '' : row.instructions,
        context,
        label,
      ),
      requires_confirmation: requiresConfirmation,
      requires_user_input: requiresUserInput,
      requires_output_review: requiresOutputReview,
      ...(confirmationMessage === undefined ? {} : { confirmation_message: confirmationMessage }),
      ...(userInputMessage === undefined ? {} : { user_input_message: userInputMessage }),
      ...(outputReviewMessage === undefined ? {} : { output_review_message: outputReviewMessage }),
      ...(skills === undefined ? {} : { skills }),
      ...(userInputSchema === undefined ? {} : { user_input_schema: userInputSchema }),
    }
  }
  if (type === 'parallel') {
    return {
      ...common,
      type: 'parallel',
      steps: parseWorkflowNodeList(row.steps, context, label, 2),
    }
  }
  if (type === 'condition') {
    return {
      ...common,
      type: 'condition',
      evaluator: parseWorkflowEvaluator(row.evaluator, context, label),
      steps: parseWorkflowNodeList(row.steps, context, label, 1),
      else: parseWorkflowNodeList(row.else, context, label, 0),
    }
  }
  if (type === 'loop') {
    const maxIterations = requireWorkflowInteger(row.max_iterations, context, label)
    if (maxIterations < 1) return invalidWorkflowValue(context, label)
    const endCondition =
      row.end_condition === null
        ? null
        : parseWorkflowEvaluator(row.end_condition, context, label)
    return {
      ...common,
      type: 'loop',
      max_iterations: maxIterations,
      end_condition: endCondition,
      steps: parseWorkflowNodeList(row.steps, context, label, 1),
    }
  }
  if (type === 'router') {
    const selector = requireWorkflowRecord(row.selector, context, label)
    return {
      ...common,
      type: 'router',
      selector: { cel: requireWorkflowIdentifier(selector.cel, context, label) },
      choices: parseWorkflowChoices(row.choices, context, label),
    }
  }
  return {
    ...common,
    type: 'workflow_ref',
    workflow_id: requireWorkflowIdentifier(row.workflow_id, context, label),
  }
}

const parseWorkflowDefinition = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): WorkflowDefinition => {
  const row = requireWorkflowRecord(value, context, label)
  return {
    name: requireWorkflowIdentifier(row.name, context, label),
    description: requireWorkflowString(row.description, context, label),
    steps: parseWorkflowNodeList(row.steps, context, label, 1),
  }
}

const parseWorkflowTriggers = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): NonNullable<WorkflowRecord['triggers']> => {
  const row = requireWorkflowRecord(value, context, label)
  const webhook = requireWorkflowRecord(row.webhook, context, label)
  const cron = requireWorkflowRecord(row.cron, context, label)
  if (typeof webhook.enabled !== 'boolean' || typeof cron.enabled !== 'boolean') {
    return invalidWorkflowValue(context, label)
  }
  return {
    webhook: {
      enabled: webhook.enabled,
      secret: requireWorkflowString(webhook.secret, context, label),
    },
    cron: {
      enabled: cron.enabled,
      expression: requireWorkflowString(cron.expression, context, label),
      last_run_at: requireWorkflowNumber(cron.last_run_at, context, label),
    },
  }
}

const parseNullableWorkflowInteger = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): number | null => {
  if (value === null) return null
  return requireWorkflowInteger(value, context, label)
}

const parseNullableWorkflowNumber = (
  value: unknown,
  context: string,
  label: WorkflowParseLabel,
): number | null => {
  if (value === null) return null
  return requireWorkflowNumber(value, context, label)
}

const parseWorkflow = (value: unknown, context: string): WorkflowRecord => {
  const label: WorkflowParseLabel = 'workflow payload'
  const row = requireWorkflowRecord(value, context, label)
  const version = requireWorkflowInteger(row.version, context, label)
  if (version < 1 || typeof row.enabled !== 'boolean' || typeof row.has_published !== 'boolean') {
    return invalidWorkflowValue(context, label)
  }
  const publishedVersion = parseNullableWorkflowInteger(row.published_version, context, label)
  if (publishedVersion !== null && publishedVersion < 1) return invalidWorkflowValue(context, label)
  return {
    id: requireWorkflowIdentifier(row.id, context, label),
    name: requireWorkflowIdentifier(row.name, context, label),
    description: requireWorkflowString(row.description, context, label),
    owner_user_id: requireWorkflowIdentifier(row.owner_user_id, context, label),
    definition: parseWorkflowDefinition(row.definition, context, label),
    triggers: parseWorkflowTriggers(row.triggers, context, label),
    enabled: row.enabled,
    version,
    published_version: publishedVersion,
    published_at: parseNullableWorkflowInteger(row.published_at, context, label),
    has_published: row.has_published,
    next_cron_at: parseNullableWorkflowNumber(row.next_cron_at, context, label),
    created_at: requireWorkflowInteger(row.created_at, context, label),
    updated_at: requireWorkflowInteger(row.updated_at, context, label),
  }
}

const requireWorkflow = (value: unknown, context: string): WorkflowRecord =>
  parseWorkflow(value, context)

const requireDefinition = (value: unknown, context: string): WorkflowDefinition =>
  parseWorkflowDefinition(value, context, 'workflow definition')

const parseExecutorOption = (value: unknown, context: string): ExecutorOption => {
  const row = asRecord(value)
  if (!row) throw new Error(`${context}: invalid workflow executor payload`)
  const ref = typeof row.ref === 'string' ? row.ref.trim() : ''
  const kind = typeof row.kind === 'string' ? row.kind.trim() : ''
  const name = typeof row.name === 'string' ? row.name.trim() : ''
  if (
    !ref ||
    !kind ||
    !name ||
    typeof row.description !== 'string' ||
    typeof row.category !== 'string' ||
    typeof row.capabilities !== 'string' ||
    typeof row.recommended_for !== 'string' ||
    typeof row.role !== 'string'
  ) {
    throw new Error(`${context}: invalid workflow executor payload`)
  }
  return {
    ref,
    kind,
    name,
    description: row.description,
    category: row.category,
    capabilities: row.capabilities,
    recommendedFor: row.recommended_for,
    role: row.role,
    attachSkills: row.attach_skills === undefined ? undefined : Boolean(row.attach_skills),
    supportsHitl: row.supports_hitl === undefined ? undefined : Boolean(row.supports_hitl),
    connectMcp: row.connect_mcp === undefined ? undefined : Boolean(row.connect_mcp),
  }
}

const parseNodePreset = (value: unknown, context: string): WorkflowNodePreset => {
  const row = asRecord(value)
  if (!row) throw new Error(`${context}: invalid workflow node preset payload`)
  const id = typeof row.id === 'string' ? row.id.trim() : ''
  const name = typeof row.name === 'string' ? row.name.trim() : ''
  const source = row.source === 'user' || row.source === 'builtin' ? row.source : ''
  const definition = asRecord(row.definition)
  const executor = asRecord(definition?.executor)
  const ref = typeof executor?.ref === 'string' ? executor.ref.trim() : ''
  if (
    !id ||
    !name ||
    !source ||
    !definition ||
    typeof row.description !== 'string' ||
    typeof row.color !== 'string' ||
    definition.type !== 'step' ||
    !ref
  ) {
    throw new Error(`${context}: invalid workflow node preset payload`)
  }
  const skills = Array.isArray(definition.skills)
    ? definition.skills.filter((item): item is string => typeof item === 'string')
    : []
  return {
    id,
    name,
    description: row.description,
    color: row.color || '#1677ff',
    source,
    definition: {
      type: 'step',
      name: typeof definition.name === 'string' ? definition.name : name,
      executor: { kind: 'agent', ref },
      instructions: typeof definition.instructions === 'string' ? definition.instructions : '',
      skills,
      requires_confirmation: Boolean(definition.requires_confirmation),
      confirmation_message:
        typeof definition.confirmation_message === 'string'
          ? definition.confirmation_message
          : undefined,
      requires_user_input: Boolean(definition.requires_user_input),
      user_input_message:
        typeof definition.user_input_message === 'string' ? definition.user_input_message : undefined,
      user_input_schema: optionalUserInputSchema(
        definition.user_input_schema,
        context,
        'workflow definition',
      ),
      requires_output_review: Boolean(definition.requires_output_review),
      output_review_message:
        typeof definition.output_review_message === 'string'
          ? definition.output_review_message
          : undefined,
    },
    created_at: typeof row.created_at === 'number' ? row.created_at : undefined,
    updated_at: typeof row.updated_at === 'number' ? row.updated_at : undefined,
  }
}

const parseWorkflowVersion = (value: unknown, context: string) => {
  const row = asRecord(value)
  if (!row) throw new Error(`${context}: invalid workflow version payload`)
  const id = typeof row.id === 'string' ? row.id.trim() : ''
  const workflowId = typeof row.workflow_id === 'string' ? row.workflow_id.trim() : ''
  const version = row.version
  const createdAt = row.created_at
  if (
    !id ||
    !workflowId ||
    !isNonNegativeInteger(version) ||
    version < 1 ||
    typeof row.name !== 'string' ||
    typeof row.description !== 'string' ||
    !isNonNegativeInteger(createdAt) ||
    typeof row.created_by !== 'string'
  ) {
    throw new Error(`${context}: invalid workflow version payload`)
  }
  return {
    id,
    workflow_id: workflowId,
    version,
    name: row.name,
    description: row.description,
    definition: requireDefinition(row.definition, context),
    created_at: createdAt,
    created_by: row.created_by,
  }
}

const parseWorkflowTemplate = (value: unknown, context: string) => {
  const row = asRecord(value)
  if (!row) throw new Error(`${context}: invalid workflow template payload`)
  const id = typeof row.id === 'string' ? row.id.trim() : ''
  const name = typeof row.name === 'string' ? row.name.trim() : ''
  const category = typeof row.category === 'string' ? row.category.trim() : ''
  const tags = row.tags
  if (
    !id ||
    !name ||
    !category ||
    typeof row.description !== 'string' ||
    !Array.isArray(tags) ||
    tags.some((tag) => typeof tag !== 'string')
  ) {
    throw new Error(`${context}: invalid workflow template payload`)
  }
  return {
    id,
    name,
    description: row.description,
    category,
    tags,
    definition: requireDefinition(row.definition, context),
  }
}

const parseWorkflowTriggerHistoryItem = (
  value: unknown,
  context: string,
): WorkflowTriggerHistoryItem => {
  const row = asRecord(value)
  const id = row?.id
  if (
    !row ||
    !isWorkflowHistoryId(id) ||
    typeof row.action !== 'string' ||
    !row.action.trim() ||
    typeof row.status !== 'string' ||
    !row.status.trim() ||
    typeof row.source !== 'string' ||
    !row.source.trim() ||
    typeof row.run_id !== 'string' ||
    typeof row.session_id !== 'string' ||
    typeof row.expression !== 'string' ||
    typeof row.created_at !== 'string' ||
    !row.created_at.trim()
  ) {
    throw new Error(`${context}: invalid workflow trigger history payload`)
  }
  return {
    id,
    action: row.action,
    status: row.status,
    source: row.source,
    run_id: row.run_id,
    session_id: row.session_id,
    expression: row.expression,
    created_at: row.created_at,
  }
}

export const listWorkflows = async (page = 1, limit = 100, q = '') => {
  const safePage = Math.max(1, page)
  const safeLimit = Math.min(100, Math.max(1, limit))
  const needle = q.trim()
  const params = new URLSearchParams({ page: String(safePage), limit: String(safeLimit) })
  if (needle) params.set('q', needle)
  const raw = await requestJson<unknown>(`/workflows?${params.toString()}`)
  return normalizePaginatedList(raw, {
    mapItem: (item) => requireWorkflow(item, 'listWorkflows'),
  })
}

export const getWorkflow = async (id: string) => {
  return requireWorkflow(
    await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}`),
    'getWorkflow',
  )
}

export const createWorkflow = async (body: {
  name: string
  description: string
  definition: WorkflowRecord['definition']
  triggers?: WorkflowRecord['triggers']
}) => {
  return requireWorkflow(
    await requestJson<unknown>('/workflows', jsonInit('POST', body)),
    'createWorkflow',
  )
}

export const updateWorkflow = async (
  id: string,
  body: {
    name?: string
    description?: string
    definition?: WorkflowRecord['definition']
    enabled?: boolean
    triggers?: WorkflowRecord['triggers']
  }
) => {
  return requireWorkflow(
    await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}`, jsonInit('PATCH', body)),
    'updateWorkflow',
  )
}


export const publishWorkflow = async (id: string) => {
  return requireWorkflow(
    await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}/publish`, jsonInit('POST', {})),
    'publishWorkflow',
  )
}

export const deleteWorkflow = async (id: string) =>
  requestJson<{ success: boolean }>(`/workflows/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const listExecutors = async () => {
  const raw = await requestJson<unknown>('/workflows/executors')
  const { data } = normalizePaginatedList(raw, {
    mapItem: (item) => parseExecutorOption(item, 'listExecutors'),
  })
  return data
}

export const listNodePresets = async () => {
  const raw = await requestJson<unknown>('/workflows/node-presets')
  const { data } = normalizePaginatedList(raw, {
    mapItem: (item) => parseNodePreset(item, 'listNodePresets'),
  })
  return data
}

export const createCustomNode = async (body: {
  name: string
  description?: string
  color?: string
  definition: WorkflowNodePreset['definition']
}) =>
  parseNodePreset(
    await requestJson<unknown>('/workflows/custom-nodes', jsonInit('POST', body)),
    'createCustomNode',
  )

export const updateCustomNode = async (
  id: string,
  body: {
    name: string
    description?: string
    color?: string
    definition: WorkflowNodePreset['definition']
  },
) =>
  parseNodePreset(
    await requestJson<unknown>(
      `/workflows/custom-nodes/${encodeURIComponent(id)}`,
      jsonInit('PUT', body),
    ),
    'updateCustomNode',
  )

export const deleteCustomNode = async (id: string) =>
  requestJson<{ success: boolean }>(
    `/workflows/custom-nodes/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  )

type WorkflowSseHandler = (item: WorkflowRunLogItem) => void

export const cancelWorkflowRun = (runId: string) =>
  requestJson<{ success?: boolean }>(
    `/workflows/runs/${encodeURIComponent(runId)}/cancel`,
    jsonInit('POST'),
  )

export const streamWorkflowRun = async (
  workflowId: string,
  payload: {
    input: string
    session_id?: string
    model_id?: string | null
    run_id?: string
  },
  onEvent: WorkflowSseHandler,
  signal: AbortSignal
) => {
  const body = {
    ...payload,
    input: (payload.input || '').trim() || 'workflow run',
  }
  const response = await apiFetch(`/workflows/${encodeURIComponent(workflowId)}/runs`, {
    ...jsonInit('POST', body),
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) {
    let detail = `Workflow run failed (${response.status})`
    try {
      const err = (await response.json()) as { detail?: unknown }
      if (typeof err.detail === 'string' && err.detail.trim()) detail = err.detail
      else if (Array.isArray(err.detail) && err.detail[0]) {
        const first = err.detail[0] as { msg?: string }
        if (first.msg) detail = first.msg
      }
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  let terminal = false
  await consumeSse(response.body, ({ event, data }) => {
    let parsed: Record<string, unknown> = {}
    try {
      parsed = JSON.parse(data) as Record<string, unknown>
    } catch {
      parsed = { message: data }
    }
    const type = (event || String(parsed.event || 'message')).trim()
    const stepName = parsed.step_name != null ? String(parsed.step_name) : null
    const content = parsed.content != null ? String(parsed.content) : null
    const message =
      parsed.message != null
        ? String(parsed.message)
        : stepName
          ? `${type} · ${stepName}`
          : type
    onEvent({
      id: crypto.randomUUID(),
      type,
      message,
      stepName,
      stepId: parsed.step_id != null ? String(parsed.step_id) : null,
      content,
      approvalId: parsed.approval_id != null ? String(parsed.approval_id) : null,
      pauseType: parsed.pause_type != null ? String(parsed.pause_type) : null,
      runId: parsed.run_id != null ? String(parsed.run_id) : null,
      sessionId: parsed.session_id != null ? String(parsed.session_id) : null,
      at: Date.now(),
    })
    terminal ||=
      type === 'workflow.completed' ||
      type === 'workflow.failed' ||
      type === 'workflow.cancelled' ||
      type === 'workflow.paused'
  })
  if (!terminal) throw new Error('Workflow stream ended before a terminal event')
}


export const listWorkflowVersions = async (workflowId: string, page = 1, limit = 100) => {
  const safePage = Math.max(1, page)
  const safeLimit = Math.min(100, Math.max(1, limit))
  const raw = await requestJson<unknown>(
    `/workflows/${encodeURIComponent(workflowId)}/versions?page=${safePage}&limit=${safeLimit}`,
  )
  const { data } = normalizePaginatedList(raw, {
    mapItem: (item) => parseWorkflowVersion(item, 'listWorkflowVersions'),
  })
  return data
}

export const restoreWorkflowVersion = async (workflowId: string, version: number) => {
  return requireWorkflow(
    await requestJson<unknown>(
      `/workflows/${encodeURIComponent(workflowId)}/versions/${version}/restore`,
      jsonInit('POST', {})
    ),
    'restoreWorkflowVersion',
  )
}

export type WorkflowTriggerHistoryItem = {
  id: string | number
  action: string
  status: string
  source: string
  run_id: string
  session_id: string
  expression?: string
  created_at: string
}

export const listWorkflowTriggerHistory = async (
  id: string,
  opts?: { page?: number; limit?: number }
): Promise<{ data: WorkflowTriggerHistoryItem[]; meta: import('@/shared/lib/pagination').ListPaginationMeta }> => {
  const page = opts?.page ?? 1
  const limit = opts?.limit ?? 20
  const raw = await requestJson<unknown>(
    `/workflows/${encodeURIComponent(id)}/triggers/history?page=${page}&limit=${limit}`
  )
  return normalizePaginatedList(raw, {
    mapItem: (item) => parseWorkflowTriggerHistoryItem(item, 'listWorkflowTriggerHistory'),
  })
}

export const listWorkflowTemplates = async () => {
  const raw = await requestJson<unknown>('/workflows/templates')
  const { data } = normalizePaginatedList(raw, {
    mapItem: (item) => parseWorkflowTemplate(item, 'listWorkflowTemplates'),
  })
  return data
}
