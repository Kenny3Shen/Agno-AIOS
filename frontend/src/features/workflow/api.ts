import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { consumeSse } from '@/features/chat/utils'
import type {
  ExecutorOption,
  WorkflowDefinitionNode,
  WorkflowNodeType,
  WorkflowRecord,
  WorkflowRunLogItem,
} from './types'

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : null

const normalizeNode = (value: unknown): WorkflowDefinitionNode | null => {
  const item = asRecord(value)
  if (!item) return null
  const type = (String(item.type || 'step').toLowerCase() || 'step') as WorkflowNodeType
  const id = String(item.id ?? crypto.randomUUID())
  const name = String(item.name ?? id)

  if (type === 'parallel') {
    return {
      id,
      type: 'parallel',
      name,
      steps: Array.isArray(item.steps)
        ? item.steps.flatMap((child) => {
            const node = normalizeNode(child)
            return node ? [node] : []
          })
        : [],
    }
  }
  if (type === 'condition') {
    const evaluator = asRecord(item.evaluator) ?? {}
    const thenRaw = Array.isArray(item.then_steps)
      ? item.then_steps
      : Array.isArray(item["then"])
        ? item["then"]
        : Array.isArray(item.steps)
          ? item.steps
          : []
    const elseRaw = Array.isArray(item.else_steps)
      ? item.else_steps
      : Array.isArray(item["else"])
        ? item["else"]
        : []
    return {
      id,
      type: 'condition',
      name,
      evaluator: {
        cel: evaluator.cel != null ? String(evaluator.cel) : undefined,
        value: typeof evaluator.value === 'boolean' ? evaluator.value : undefined,
      },
      then_steps: thenRaw.flatMap((child) => {
        const node = normalizeNode(child)
        return node ? [node] : []
      }),
      else_steps: elseRaw.flatMap((child) => {
        const node = normalizeNode(child)
        return node ? [node] : []
      }),
    }
  }
  if (type === 'loop') {
    const end = asRecord(item.end_condition) ?? asRecord(item.endCondition)
    return {
      id,
      type: 'loop',
      name,
      max_iterations: Number(item.max_iterations ?? item.maxIterations ?? 3),
      end_condition: end
        ? {
            cel: end.cel != null ? String(end.cel) : undefined,
            value: typeof end.value === 'boolean' ? end.value : undefined,
          }
        : null,
      steps: Array.isArray(item.steps)
        ? item.steps.flatMap((child) => {
            const node = normalizeNode(child)
            return node ? [node] : []
          })
        : [],
      position: asRecord(item.position)
        ? { x: Number(asRecord(item.position)?.x ?? 0), y: Number(asRecord(item.position)?.y ?? 0) }
        : undefined,
    }
  }
  if (type === 'router') {
    const selector = asRecord(item.selector) ?? {}
    const choices = Array.isArray(item.choices) ? item.choices : []
    return {
      id,
      type: 'router',
      name,
      selector: { cel: selector.cel != null ? String(selector.cel) : undefined },
      choices: choices.flatMap((raw) => {
        const choice = asRecord(raw)
        if (!choice) return []
        return [
          {
            id: String(choice.id ?? crypto.randomUUID()),
            name: String(choice.name ?? choice.id ?? 'choice'),
            steps: Array.isArray(choice.steps)
              ? choice.steps.flatMap((child) => {
                  const node = normalizeNode(child)
                  return node ? [node] : []
                })
              : [],
          },
        ]
      }),
      position: asRecord(item.position)
        ? { x: Number(asRecord(item.position)?.x ?? 0), y: Number(asRecord(item.position)?.y ?? 0) }
        : undefined,
    }
  }
  if (type === 'workflow_ref') {
    return {
      id,
      type: 'workflow_ref',
      name,
      workflow_id: String(item.workflow_id ?? item.workflowId ?? ''),
      position: asRecord(item.position)
        ? { x: Number(asRecord(item.position)?.x ?? 0), y: Number(asRecord(item.position)?.y ?? 0) }
        : undefined,
    }
  }

  const executor = asRecord(item.executor) ?? {}
  return {
    id,
    type: 'step',
    name,
    executor: {
      kind: 'agent',
      ref: String(executor.ref ?? item.targetId ?? 'security-operations'),
    },
    instructions: String(item.instructions ?? ''),
    requires_confirmation: Boolean(item.requires_confirmation),
    confirmation_message: item.confirmation_message != null ? String(item.confirmation_message) : undefined,
    requires_user_input: Boolean(item.requires_user_input),
    user_input_message: item.user_input_message != null ? String(item.user_input_message) : undefined,
    requires_output_review: Boolean(item.requires_output_review),
    output_review_message: item.output_review_message != null ? String(item.output_review_message) : undefined,
    position: asRecord(item.position)
      ? { x: Number(asRecord(item.position)?.x ?? 0), y: Number(asRecord(item.position)?.y ?? 0) }
      : undefined,
  }
}

const normalizeWorkflow = (value: unknown): WorkflowRecord | null => {
  const row = asRecord(value)
  if (!row) return null
  const id = String(row.id ?? '').trim()
  if (!id) return null
  const definition = asRecord(row.definition) ?? { name: '', description: '', steps: [] }
  return {
    id,
    name: String(row.name ?? ''),
    description: String(row.description ?? ''),
    owner_user_id: String(row.owner_user_id ?? ''),
    definition: {
      name: String(definition.name ?? row.name ?? ''),
      description: String(definition.description ?? row.description ?? ''),
      steps: Array.isArray(definition.steps)
        ? definition.steps.flatMap((step) => {
            const node = normalizeNode(step)
            return node ? [node] : []
          })
        : [],
    },
    triggers: (() => {
      const triggers = asRecord(row.triggers) ?? {}
      const webhook = asRecord(triggers.webhook) ?? {}
      const cron = asRecord(triggers.cron) ?? {}
      return {
        webhook: {
          enabled: Boolean(webhook.enabled),
          secret: String(webhook.secret ?? ''),
        },
        cron: {
          enabled: Boolean(cron.enabled),
          expression: String(cron.expression ?? ''),
          last_run_at: Number(cron.last_run_at ?? 0) || 0,
        },
      }
    })(),
    enabled: row.enabled !== false,
    version: Number(row.version ?? 1),
    published_version: row.published_version != null ? Number(row.published_version) : null,
    published_at: row.published_at != null ? Number(row.published_at) : null,
    has_published: Boolean(row.has_published),
    next_cron_at: row.next_cron_at != null ? Number(row.next_cron_at) : null,
    created_at: Number(row.created_at ?? 0),
    updated_at: Number(row.updated_at ?? 0),
  }
}

export const listWorkflows = async (page = 1, limit = 50) => {
  const payload = asRecord(await requestJson<unknown>(`/workflows?page=${page}&limit=${limit}`))
  const data = Array.isArray(payload?.data) ? payload.data : []
  return data.flatMap((item) => {
    const row = normalizeWorkflow(item)
    return row ? [row] : []
  })
}

export const createWorkflow = async (body: {
  name: string
  description: string
  definition: WorkflowRecord['definition']
  triggers?: WorkflowRecord['triggers']
}) => {
  const row = normalizeWorkflow(await requestJson<unknown>('/workflows', jsonInit('POST', body)))
  if (!row) throw new Error('Invalid workflow payload')
  return row
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
  const row = normalizeWorkflow(
    await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}`, jsonInit('PATCH', body))
  )
  if (!row) throw new Error('Invalid workflow payload')
  return row
}


export const publishWorkflow = async (id: string) => {
  const row = normalizeWorkflow(
    await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}/publish`, jsonInit('POST', {}))
  )
  if (!row) throw new Error('Invalid workflow payload')
  return row
}

export const deleteWorkflow = async (id: string) =>
  requestJson<{ success: boolean }>(`/workflows/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const listExecutors = async () => {
  const payload = asRecord(await requestJson<unknown>('/workflows/executors'))
  const data = Array.isArray(payload?.data) ? payload.data : []
  return data.flatMap((item): ExecutorOption[] => {
    const row = asRecord(item)
    if (!row?.ref) return []
    return [
      {
        ref: String(row.ref),
        kind: String(row.kind ?? 'agent'),
        name: String(row.name ?? row.ref),
        description: String(row.description ?? ''),
      },
    ]
  })
}

export type WorkflowSseHandler = (item: WorkflowRunLogItem) => void

export const streamWorkflowRun = async (
  workflowId: string,
  payload: { input: string; session_id?: string; model_id?: string | null },
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
    const stepName =
      parsed.step_name != null
        ? String(parsed.step_name)
        : parsed.stepName != null
          ? String(parsed.stepName)
          : null
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
      stepId:
        parsed.step_id != null
          ? String(parsed.step_id)
          : parsed.stepId != null
            ? String(parsed.stepId)
            : null,
      content,
      approvalId:
        parsed.approval_id != null
          ? String(parsed.approval_id)
          : parsed.approvalId != null
            ? String(parsed.approvalId)
            : null,
      pauseType:
        parsed.pause_type != null
          ? String(parsed.pause_type)
          : parsed.pauseType != null
            ? String(parsed.pauseType)
            : null,
      runId:
        parsed.run_id != null
          ? String(parsed.run_id)
          : parsed.runId != null
            ? String(parsed.runId)
            : null,
      sessionId:
        parsed.session_id != null
          ? String(parsed.session_id)
          : parsed.sessionId != null
            ? String(parsed.sessionId)
            : null,
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


export const listWorkflowVersions = async (workflowId: string, page = 1, limit = 20) => {
  const payload = asRecord(
    await requestJson<unknown>(
      `/workflows/${encodeURIComponent(workflowId)}/versions?page=${page}&limit=${limit}`
    )
  )
  const data = Array.isArray(payload?.data) ? payload.data : []
  return data.flatMap((item) => {
    const row = asRecord(item)
    if (!row) return []
    return [
      {
        id: String(row.id ?? ''),
        workflow_id: String(row.workflow_id ?? workflowId),
        version: Number(row.version ?? 0),
        name: String(row.name ?? ''),
        description: String(row.description ?? ''),
        definition: (asRecord(row.definition) as never) ?? { name: '', description: '', steps: [] },
        created_at: Number(row.created_at ?? 0),
        created_by: String(row.created_by ?? ''),
      },
    ]
  })
}

export const restoreWorkflowVersion = async (workflowId: string, version: number) => {
  const row = normalizeWorkflow(
    await requestJson<unknown>(
      `/workflows/${encodeURIComponent(workflowId)}/versions/${version}/restore`,
      jsonInit('POST', {})
    )
  )
  if (!row) throw new Error('Invalid workflow payload')
  return row
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
) => {
  const page = opts?.page ?? 1
  const limit = opts?.limit ?? 20
  const raw = await requestJson<unknown>(
    `/workflows/${encodeURIComponent(id)}/triggers/history?page=${page}&limit=${limit}`
  )
  const row = asRecord(raw) ?? {}
  const data = Array.isArray(row.data) ? row.data : []
  const meta = asRecord(row.meta) ?? {}
  return {
    data: data.flatMap((item) => {
      const r = asRecord(item)
      if (!r) return []
      return [
        {
          id: (r.id as string | number) ?? '',
          action: String(r.action ?? ''),
          status: String(r.status ?? ''),
          source: String(r.source ?? ''),
          run_id: String(r.run_id ?? ''),
          session_id: String(r.session_id ?? ''),
          expression: r.expression != null ? String(r.expression) : '',
          created_at: String(r.created_at ?? ''),
        } satisfies WorkflowTriggerHistoryItem,
      ]
    }),
    meta: {
      page: Number(meta.page ?? page) || page,
      limit: Number(meta.limit ?? limit) || limit,
      total_count: Number(meta.total_count ?? data.length) || 0,
      total_pages: Number(meta.total_pages ?? 0) || 0,
      search_time_ms: Number(meta.search_time_ms ?? 0) || 0,
    },
  }
}

export type WorkflowTemplate = {
  id: string
  name: string
  description: string
  category: string
  tags: string[]
  definition: {
    name: string
    description: string
    steps: WorkflowDefinitionNode[]
  }
}

export const listWorkflowTemplates = async () => {
  const raw = await requestJson<unknown>('/workflows/templates')
  const row = asRecord(raw) ?? {}
  const data = Array.isArray(row.data) ? row.data : Array.isArray(raw) ? (raw as unknown[]) : []
  return data.flatMap((item) => {
    const r = asRecord(item)
    if (!r) return []
    const def = asRecord(r.definition) ?? {}
    const stepsRaw = Array.isArray(def.steps) ? def.steps : []
    return [
      {
        id: String(r.id ?? ''),
        name: String(r.name ?? ''),
        description: String(r.description ?? ''),
        category: String(r.category ?? ''),
        tags: Array.isArray(r.tags) ? r.tags.map(String) : [],
        definition: {
          name: String(def.name ?? r.name ?? ''),
          description: String(def.description ?? ''),
          steps: stepsRaw.flatMap((child) => {
            const node = normalizeNode(child)
            return node ? [node] : []
          }),
        },
      } satisfies WorkflowTemplate,
    ]
  })
}

