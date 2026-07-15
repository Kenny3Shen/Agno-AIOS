import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { consumeSse } from '@/features/chat/utils'
import type { ExecutorOption, WorkflowRecord, WorkflowRunEventType, WorkflowRunLogItem } from './types'

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : null

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
            const item = asRecord(step)
            if (!item) return []
            const executor = asRecord(item.executor) ?? {}
            return [
              {
                id: String(item.id ?? crypto.randomUUID()),
                type: 'step' as const,
                name: String(item.name ?? ''),
                executor: {
                  kind: 'agent' as const,
                  ref: String(executor.ref ?? 'security-operations'),
                },
                instructions: String(item.instructions ?? ''),
              },
            ]
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
    const type = (event || 'message') as WorkflowRunEventType | string
    const stepName = typeof parsed.step_name === 'string' ? parsed.step_name : null
    const content = typeof parsed.content === 'string' ? parsed.content : null
    const message =
      typeof parsed.message === 'string'
        ? parsed.message
        : type === 'step.completed' && content
          ? content.slice(0, 240)
          : type
    onEvent({
      id: crypto.randomUUID(),
      type,
      message,
      stepName,
      content,
      at: Date.now(),
    })
    terminal ||= type === 'workflow.completed' || type === 'workflow.failed' || type === 'workflow.cancelled'
  })
  if (!terminal) throw new Error('Workflow stream ended before a terminal event')
}
