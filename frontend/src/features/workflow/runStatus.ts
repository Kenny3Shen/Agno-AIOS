import type {
  WorkflowNode,
  WorkflowNodeRunStatus,
  WorkflowRunHistoryItem,
  WorkflowRunLogItem,
} from './types'
import { findNode } from './utils'

/** Resolve a canvas node id from SSE payload (prefer step_id, fall back to name match). */
export const resolveNodeId = (
  steps: WorkflowNode[],
  stepId?: string | null,
  stepName?: string | null
): string | null => {
  if (stepId) {
    const byId = findNode(steps, stepId)
    if (byId) return byId.id
  }
  if (!stepName) return null
  const needle = stepName.trim().toLowerCase()
  const walk = (nodes: WorkflowNode[]): string | null => {
    for (const node of nodes) {
      if ((node.name || '').trim().toLowerCase() === needle) return node.id
      if (node.type === 'step' && (node.targetId || '').toLowerCase() === needle) return node.id
      for (const list of [node.steps, node.thenSteps, node.elseSteps]) {
        if (list?.length) {
          const found = walk(list)
          if (found) return found
        }
      }
      for (const choice of node.choices ?? []) {
        const found = walk(choice.steps)
        if (found) return found
      }
    }
    return null
  }
  return walk(steps)
}

const mark = (
  map: Record<string, WorkflowNodeRunStatus>,
  id: string | null,
  status: WorkflowNodeRunStatus
) => {
  if (!id) return map
  return { ...map, [id]: status }
}

/** Reduce SSE log items into per-node status map. */
export const reduceNodeRunStatus = (
  steps: WorkflowNode[],
  log: WorkflowRunLogItem[]
): Record<string, WorkflowNodeRunStatus> => {
  let map: Record<string, WorkflowNodeRunStatus> = {}
  for (const item of log) {
    const id = resolveNodeId(steps, item.stepId, item.stepName)
    const type = item.type
    if (type.endsWith('.started') || type === 'loop.iteration.started') {
      map = mark(map, id, 'running')
    } else if (type.endsWith('.completed') || type === 'loop.iteration.completed') {
      map = mark(map, id, 'ok')
    } else if (type.endsWith('.error') || type === 'workflow.failed') {
      map = mark(map, id, 'error')
      if (type === 'workflow.failed' && !id) {
        // leave last running as error
        const runningIds = Object.entries(map)
          .filter(([, status]) => status === 'running')
          .map(([nodeId]) => nodeId)
        for (const nodeId of runningIds) map = mark(map, nodeId, 'error')
      }
    } else if (type === 'workflow.paused') {
      map = mark(map, id, 'paused')
      // any still-running nodes stay running except the paused one
    } else if (type === 'workflow.completed') {
      // promote remaining running → ok
      for (const [nodeId, status] of Object.entries(map)) {
        if (status === 'running') map = mark(map, nodeId, 'ok')
      }
    } else if (type === 'workflow.cancelled') {
      for (const [nodeId, status] of Object.entries(map)) {
        if (status === 'running' || status === 'paused') map = mark(map, nodeId, 'error')
      }
    }
  }
  return map
}

export const historyStatusFromEvent = (
  type: string
): WorkflowRunHistoryItem['status'] | null => {
  if (type === 'workflow.started') return 'running'
  if (type === 'workflow.completed') return 'completed'
  if (type === 'workflow.failed') return 'failed'
  if (type === 'workflow.cancelled') return 'cancelled'
  if (type === 'workflow.paused') return 'paused'
  return null
}
