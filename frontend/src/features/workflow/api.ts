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
    enabled: row.enabled !== false,
    version: Number(row.version ?? 1),
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

export const getWorkflow = async (id: string) => {
  const row = normalizeWorkflow(await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}`))
  if (!row) throw new Error('Invalid workflow payload')
  return row
}

export const createWorkflow = async (body: {
  name: string
  description: string
  definition: WorkflowRecord['definition']
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
  }
) => {
  const row = normalizeWorkflow(
    await requestJson<unknown>(`/workflows/${encodeURIComponent(id)}`, jsonInit('PATCH', body))
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
  const response = await apiFetch(`/workflows/${encodeURIComponent(workflowId)}/runs`, {
    ...jsonInit('POST', payload),
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`Workflow run failed (${response.status})`)
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
      content,
      at: Date.now(),
    })
    terminal ||=
      type === 'workflow.completed' || type === 'workflow.failed' || type === 'workflow.cancelled'
  })
  if (!terminal) throw new Error('Workflow stream ended before a terminal event')
}
