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
): Record<string, WorkflowNodeRunStatus> => {
  if (!id) return map
  if (map[id] === status) return map
  return { ...map, [id]: status }
}

/** Apply a single SSE event onto an existing status map (O(nodes) worst-case, not O(log length)). */
export const applyNodeRunStatusEvent = (
  steps: WorkflowNode[],
  map: Record<string, WorkflowNodeRunStatus>,
  item: Pick<WorkflowRunLogItem, 'type' | 'stepId' | 'stepName'> | WorkflowRunLogItem
): Record<string, WorkflowNodeRunStatus> => {
  const id = resolveNodeId(steps, item.stepId, item.stepName)
  const type = item.type
  if (type.endsWith('.started') || type === 'loop.iteration.started') {
    return mark(map, id, 'running')
  }
  if (type.endsWith('.completed') || type === 'loop.iteration.completed') {
    return mark(map, id, 'ok')
  }
  if (type.endsWith('.error') || type === 'workflow.failed') {
    let next = mark(map, id, 'error')
    if (type === 'workflow.failed' && !id) {
      for (const [nodeId, status] of Object.entries(next)) {
        if (status === 'running') next = mark(next, nodeId, 'error')
      }
    }
    return next
  }
  if (type === 'workflow.paused') {
    return mark(map, id, 'paused')
  }
  if (type === 'workflow.completed') {
    let next = map
    let changed = false
    for (const [nodeId, status] of Object.entries(map)) {
      if (status === 'running') {
        if (!changed) {
          next = { ...map }
          changed = true
        }
        next[nodeId] = 'ok'
      }
    }
    return next
  }
  if (type === 'workflow.cancelled') {
    let next = map
    let changed = false
    for (const [nodeId, status] of Object.entries(map)) {
      if (status === 'running' || status === 'paused') {
        if (!changed) {
          next = { ...map }
          changed = true
        }
        next[nodeId] = 'error'
      }
    }
    return next
  }
  return map
}

/** Reduce SSE log items into per-node status map. */
export const reduceNodeRunStatus = (
  steps: WorkflowNode[],
  log: Array<Pick<WorkflowRunLogItem, 'type' | 'stepId' | 'stepName'> | WorkflowRunLogItem>
): Record<string, WorkflowNodeRunStatus> => {
  let map: Record<string, WorkflowNodeRunStatus> = {}
  for (const item of log) {
    map = applyNodeRunStatusEvent(steps, map, item)
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

/** Keep the run log bounded for UI memory (newest retained when over cap). */
export const appendRunLog = (
  log: WorkflowRunLogItem[],
  item: WorkflowRunLogItem,
  limit = 200
): WorkflowRunLogItem[] => {
  if (log.length < limit) return [...log, item]
  // drop oldest chunk when full
  const keepFrom = Math.max(0, log.length - limit + 1)
  return [...log.slice(keepFrom), item]
}
