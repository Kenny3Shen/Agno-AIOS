import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getModels } from '@/features/settings/api'
import {
  createWorkflow,
  deleteWorkflow,
  listExecutors,
  listWorkflowVersions,
  listWorkflows,
  listWorkflowTemplates,
  restoreWorkflowVersion,
  publishWorkflow,
  streamWorkflowRun,
  updateWorkflow,
} from './api'
import type {
  WorkflowNode,
  WorkflowNodeType,
  WorkflowRunHistoryItem,
  WorkflowState,
  WorkflowTriggers,
} from './types'
import { appendRunLog, applyNodeRunStatusEvent, historyStatusFromEvent } from './runStatus'
import {
  addChildToNode,
  applyAutoLayout,
  cloneNodeDeep,
  createNode,
  defaultTriggers,
  findNode,
  fromDefinition,
  fromRecord,
  insertChild,
  moveNodeAfter,
  moveStep,
  parseEmptySlot,
  removeNodeInTree,
  removeNodesInTree,
  reorderRootsByPositions,
  reparentNode,
  reparentTargetFromHandle,
  toDefinition,
  updateNodeInTree,
  validateWorkflowDraft,
  type ReparentTarget,
} from './utils'

const HISTORY_LIMIT = 40

type HistorySnap = {
  steps: WorkflowNode[]
  selectedId: string | null
  selectedIds: string[]
}

const initialState = (): WorkflowState => ({
  workflowId: null,
  name: '',
  description: '',
  input: '',
  sessionId: crypto.randomUUID(),
  modelId: null,
  steps: [],
  triggers: defaultTriggers(),
  selectedId: null,
  selectedIds: [],
  dirty: false,
  saving: false,
  running: false,
  runLog: [],
  nodeRunStatus: {},
  runHistory: [],
  error: null,
  validationIssues: [],
  lastRunId: null,
  lastSessionId: null,
  lastApprovalId: null,
})

const snapOf = (state: Pick<WorkflowState, 'steps' | 'selectedId' | 'selectedIds'>): HistorySnap => ({
  steps: structuredClone(state.steps),
  selectedId: state.selectedId,
  selectedIds: [...state.selectedIds],
})

export function useWorkflow() {
  const [state, setState] = useState<WorkflowState>(initialState)
  const abortRef = useRef<AbortController | null>(null)
  const pastRef = useRef<HistorySnap[]>([])
  const futureRef = useRef<HistorySnap[]>([])
  const clipboardRef = useRef<WorkflowNode[]>([])
  const [historyTick, setHistoryTick] = useState(0)

  const workflowsQuery = useQuery({
    queryKey: ['workflows', 'list'],
    queryFn: () => listWorkflows(),
  })
  const executorsQuery = useQuery({
    queryKey: ['workflows', 'executors'],
    queryFn: listExecutors,
  })
  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: getModels,
  })
  const versionsQuery = useQuery({
    queryKey: ['workflows', 'versions', state.workflowId],
    queryFn: () => listWorkflowVersions(state.workflowId!),
    enabled: Boolean(state.workflowId),
  })
  const templatesQuery = useQuery({
    queryKey: ['workflows', 'templates'],
    queryFn: listWorkflowTemplates,
  })

  useEffect(() => {
    const active = modelsQuery.data?.active_model_id
    if (active && !state.modelId) {
      setState((current) => ({ ...current, modelId: active }))
    }
  }, [modelsQuery.data?.active_model_id, state.modelId])

  const bumpHistory = () => setHistoryTick((n) => n + 1)

  const pushHistory = useCallback((current: WorkflowState) => {
    pastRef.current = [...pastRef.current.slice(-(HISTORY_LIMIT - 1)), snapOf(current)]
    futureRef.current = []
    bumpHistory()
  }, [])

  const withHistory = useCallback(
    (recipe: (current: WorkflowState) => WorkflowState) => {
      setState((current) => {
        const next = recipe(current)
        if (next === current) return current
        pushHistory(current)
        return { ...next, validationIssues: [] }
      })
    },
    [pushHistory]
  )

  const canUndo = pastRef.current.length > 0
  const canRedo = futureRef.current.length > 0
  // historyTick forces re-render of canUndo/canRedo consumers
  void historyTick

  const undo = useCallback(() => {
    setState((current) => {
      const prev = pastRef.current.pop()
      if (!prev) return current
      futureRef.current.push(snapOf(current))
      bumpHistory()
      return {
        ...current,
        steps: prev.steps,
        selectedId: prev.selectedId,
        selectedIds: prev.selectedIds,
        dirty: true,
      }
    })
  }, [])

  const redo = useCallback(() => {
    setState((current) => {
      const next = futureRef.current.pop()
      if (!next) return current
      pastRef.current.push(snapOf(current))
      bumpHistory()
      return {
        ...current,
        steps: next.steps,
        selectedId: next.selectedId,
        selectedIds: next.selectedIds,
        dirty: true,
      }
    })
  }, [])

  const patch = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value, dirty: value.dirty !== false }))
  }, [])

  const patchMeta = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value }))
  }, [])

  const select = useCallback((id: string | null, multi = false) => {
    setState((current) => {
      if (!id) {
        return { ...current, selectedId: null, selectedIds: [] }
      }
      if (multi) {
        const exists = current.selectedIds.includes(id)
        const selectedIds = exists
          ? current.selectedIds.filter((item) => item !== id)
          : [...current.selectedIds, id]
        return {
          ...current,
          selectedId: selectedIds[selectedIds.length - 1] ?? null,
          selectedIds,
        }
      }
      return { ...current, selectedId: id, selectedIds: [id] }
    })
  }, [])

  const selectMany = useCallback((ids: string[]) => {
    setState((current) => ({
      ...current,
      selectedId: ids[ids.length - 1] ?? null,
      selectedIds: ids,
    }))
  }, [])

  const add = (type: WorkflowNodeType = 'step') => {
    const node = createNode(type)
    withHistory((current) => ({
      ...current,
      steps: [...current.steps, node],
      selectedId: node.id,
      selectedIds: [node.id],
      dirty: true,
    }))
  }

  const addAt = (
    type: WorkflowNodeType,
    position: { x: number; y: number },
    target?: ReparentTarget | null
  ) => {
    const node = createNode(type)
    node.position = { x: position.x, y: position.y }
    withHistory((current) => {
      const steps = target
        ? insertChild(current.steps, target, node)
        : [...current.steps, node]
      return {
        ...current,
        steps,
        selectedId: node.id,
        selectedIds: [node.id],
        dirty: true,
      }
    })
  }

  const addChild = (
    parentId: string,
    branch: 'steps' | 'thenSteps' | 'elseSteps' = 'steps',
    type: WorkflowNodeType = 'step'
  ) => {
    const child = createNode(type)
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: addChildToNode(current.steps, parentId, branch, child),
      selectedId: child.id,
      selectedIds: [child.id],
    }))
  }

  const addToSlot = (parentId: string, slotKey: string, type: WorkflowNodeType = 'step') => {
    withHistory((current) => {
      const parent = findNode(current.steps, parentId)
      if (!parent) return current
      const target = parseEmptySlot(parent, slotKey)
      if (!target) return current
      const child = createNode(type)
      const parentPos = parent.position
      if (parentPos) {
        child.position = { x: parentPos.x + 220, y: parentPos.y + 40 }
      }
      return {
        ...current,
        dirty: true,
        steps: insertChild(current.steps, target, child),
        selectedId: child.id,
        selectedIds: [child.id],
      }
    })
  }

  // Inspector field edits: push one undo snapshot per burst (typing does not spam history).
  const inspectorHistoryNodeRef = useRef<string | null>(null)
  const inspectorHistoryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const update = (node: WorkflowNode) => {
    setState((current) => {
      if (inspectorHistoryNodeRef.current !== node.id) {
        pushHistory(current)
        inspectorHistoryNodeRef.current = node.id
      }
      if (inspectorHistoryTimerRef.current) clearTimeout(inspectorHistoryTimerRef.current)
      inspectorHistoryTimerRef.current = setTimeout(() => {
        inspectorHistoryNodeRef.current = null
        inspectorHistoryTimerRef.current = null
      }, 600)
      return {
        ...current,
        dirty: true,
        validationIssues: [],
        steps: updateNodeInTree(current.steps, node.id, () => node),
      }
    })
  }

  const remove = (id: string) =>
    withHistory((current) => {
      const selectedIds = current.selectedIds.filter((item) => item !== id)
      return {
        ...current,
        dirty: true,
        steps: removeNodeInTree(current.steps, id),
        selectedId: current.selectedId === id ? selectedIds[0] ?? null : current.selectedId,
        selectedIds,
      }
    })

  const removeSelected = () => {
    withHistory((current) => {
      const ids = current.selectedIds.length
        ? current.selectedIds
        : current.selectedId
          ? [current.selectedId]
          : []
      if (!ids.length) return current
      return {
        ...current,
        dirty: true,
        steps: removeNodesInTree(current.steps, ids),
        selectedId: null,
        selectedIds: [],
      }
    })
  }

  const move = (id: string, direction: -1 | 1) =>
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: moveStep(current.steps, id, direction),
    }))

  const applyPositions = (positions: Record<string, { x: number; y: number }>) => {
    // Position-only updates: no history spam while dragging ends once.
    withHistory((current) => {
      let steps = current.steps
      for (const [id, position] of Object.entries(positions)) {
        steps = updateNodeInTree(steps, id, (node) => ({ ...node, position }))
      }
      steps = reorderRootsByPositions(steps)
      return { ...current, steps, dirty: true }
    })
  }

  const reparent = (nodeId: string, target: ReparentTarget) => {
    withHistory((current) => {
      const steps = reparentNode(current.steps, nodeId, target)
      if (steps === current.steps) return current
      return { ...current, steps, dirty: true, selectedId: nodeId, selectedIds: [nodeId] }
    })
  }

  const connectSequence = (sourceId: string, targetId: string) => {
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: moveNodeAfter(current.steps, targetId, sourceId),
    }))
  }

  /** Wire target under source's branch handle (condition/router/parallel). */
  const connectBranch = (sourceId: string, targetId: string, sourceHandle?: string | null) => {
    withHistory((current) => {
      const source = findNode(current.steps, sourceId)
      if (!source) return current
      const target = reparentTargetFromHandle(source, sourceHandle)
      if (!target) return current
      const steps = reparentNode(current.steps, targetId, target)
      if (steps === current.steps) return current
      return {
        ...current,
        dirty: true,
        steps,
        selectedId: targetId,
        selectedIds: [targetId],
      }
    })
  }

  const organizeLayout = () => {
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: applyAutoLayout(current.steps),
    }))
  }

  const copySelected = () => {
    const ids = state.selectedIds.length
      ? state.selectedIds
      : state.selectedId
        ? [state.selectedId]
        : []
    const nodes = ids
      .map((id) => findNode(state.steps, id))
      .filter((node): node is WorkflowNode => Boolean(node))
    // Prefer top-most selection only (skip nodes nested under another selected node).
    const tops = nodes.filter(
      (node) => !nodes.some((other) => other.id !== node.id && Boolean(findNode([other], node.id)))
    )
    clipboardRef.current = (tops.length ? tops : nodes).map(cloneNodeDeep)
  }

  const pasteClipboard = () => {
    const items = clipboardRef.current
    if (!items.length) return
    withHistory((current) => {
      const clones = items.map((node) => {
        const clone = cloneNodeDeep(node)
        const pos = clone.position
        clone.position = pos
          ? { x: pos.x + 40, y: pos.y + 40 }
          : { x: 80, y: 80 }
        return clone
      })
      // refresh clipboard offsets for repeated paste
      clipboardRef.current = clones.map(cloneNodeDeep)
      const ids = clones.map((c) => c.id)
      return {
        ...current,
        dirty: true,
        steps: [...current.steps, ...clones],
        selectedId: ids[ids.length - 1] ?? null,
        selectedIds: ids,
      }
    })
  }

  const duplicateSelected = () => {
    // snapshot selection into clipboard then paste with offset
    const ids = state.selectedIds.length
      ? state.selectedIds
      : state.selectedId
        ? [state.selectedId]
        : []
    const nodes = ids
      .map((id) => findNode(state.steps, id))
      .filter((node): node is WorkflowNode => Boolean(node))
    const tops = nodes.filter(
      (node) => !nodes.some((other) => other.id !== node.id && Boolean(findNode([other], node.id)))
    )
    clipboardRef.current = (tops.length ? tops : nodes).map(cloneNodeDeep)
    pasteClipboard()
  }

  const patchTriggers = (triggers: WorkflowTriggers) => {
    setState((current) => ({ ...current, triggers, dirty: true }))
  }

  const load = (id: string) => {
    const record = (workflowsQuery.data ?? []).find((item) => item.id === id)
    if (!record) return
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    const loaded = fromRecord(record)
    setState((current) => ({
      ...current,
      ...loaded,
      selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
      input: current.input,
      sessionId: crypto.randomUUID(),
      runLog: [],
      error: null,
      validationIssues: [],
      dirty: false,
    }))
  }

  const applyTemplate = (templateId: string) => {
    const template = (templatesQuery.data ?? []).find((item) => item.id === templateId)
    if (!template) return
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    const loaded = fromDefinition(template.definition, {
      name: template.definition.name || template.name,
      description: template.definition.description || template.description,
    })
    setState((current) => ({
      ...current,
      ...loaded,
      selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
      input: current.input,
      sessionId: crypto.randomUUID(),
      modelId: current.modelId,
      runLog: [],
      nodeRunStatus: {},
      runHistory: [],
      error: null,
      validationIssues: [],
      dirty: true,
      lastRunId: null,
      lastSessionId: null,
      lastApprovalId: null,
    }))
  }

  const reset = () => {
    abortRef.current?.abort()
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    setState(initialState())
  }

  const save = async () => {
    const issues = validateWorkflowDraft(state.steps)
    if (issues.length) {
      setState((current) => ({
        ...current,
        validationIssues: issues,
        error: issues[0]?.message ?? 'Fix validation errors before saving',
        selectedId: issues[0]?.nodeId ?? current.selectedId,
        selectedIds: issues[0]?.nodeId ? [issues[0].nodeId] : current.selectedIds,
      }))
      return
    }
    setState((current) => ({ ...current, saving: true, error: null, validationIssues: [] }))
    try {
      const definition = toDefinition(state)
      const body = {
        name: definition.name,
        description: definition.description,
        definition,
        triggers: state.triggers,
      }
      const record = state.workflowId
        ? await updateWorkflow(state.workflowId, body)
        : await createWorkflow(body)
      const loaded = fromRecord(record)
      setState((current) => ({
        ...current,
        ...loaded,
        selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
        saving: false,
        dirty: false,
        error: null,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
    } catch (error) {
      setState((current) => ({
        ...current,
        saving: false,
        error: error instanceof Error ? error.message : 'Save failed',
      }))
    }
  }

  const publish = async () => {
    if (!state.workflowId) {
      setState((current) => ({ ...current, error: 'Save the workflow before publishing' }))
      return
    }
    if (state.dirty) {
      setState((current) => ({ ...current, error: 'Save changes before publishing' }))
      return
    }
    setState((current) => ({ ...current, saving: true, error: null }))
    try {
      const record = await publishWorkflow(state.workflowId)
      const loaded = fromRecord(record)
      setState((current) => ({
        ...current,
        ...loaded,
        selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
        saving: false,
        dirty: false,
        error: null,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
    } catch (error) {
      setState((current) => ({
        ...current,
        saving: false,
        error: error instanceof Error ? error.message : 'Publish failed',
      }))
    }
  }

  const restoreVersion = async (version: number) => {
    if (!state.workflowId) return
    try {
      const record = await restoreWorkflowVersion(state.workflowId, version)
      pastRef.current = []
      futureRef.current = []
      bumpHistory()
      const loaded = fromRecord(record)
      setState((current) => ({
        ...current,
        ...loaded,
        selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
        dirty: false,
        error: null,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : 'Restore failed',
      }))
    }
  }

  const removeSaved = async () => {
    if (!state.workflowId) return
    await deleteWorkflow(state.workflowId)
    reset()
    await workflowsQuery.refetch()
  }

  const run = async () => {
    if (!state.workflowId) {
      setState((current) => ({ ...current, error: 'Save the workflow before running' }))
      return
    }
    if (state.dirty) {
      setState((current) => ({ ...current, error: 'Save changes before running' }))
      return
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const sessionId = crypto.randomUUID()
    const historyId = crypto.randomUUID()
    setState((current) => ({
      ...current,
      running: true,
      error: null,
      runLog: [],
      nodeRunStatus: {},
      sessionId,
      lastSessionId: sessionId,
      lastRunId: null,
      lastApprovalId: null,
      runHistory: [
        {
          id: historyId,
          runId: '',
          sessionId,
          status: 'running' as const,
          startedAt: Date.now(),
        } satisfies WorkflowRunHistoryItem,
        ...current.runHistory,
      ].slice(0, 20),
    }))
    try {
      await streamWorkflowRun(
        state.workflowId,
        { input: state.input, session_id: sessionId, model_id: state.modelId },
        (item) => {
          setState((current) => {
            const runLog = appendRunLog(current.runLog, item, 200)
            const nodeRunStatus = applyNodeRunStatusEvent(
              current.steps,
              current.nodeRunStatus,
              item
            )
            const histStatus = historyStatusFromEvent(item.type)
            let runHistory = current.runHistory
            if (histStatus || item.runId || item.approvalId) {
              runHistory = current.runHistory.map((entry) => {
                if (entry.id !== historyId) return entry
                return {
                  ...entry,
                  runId: item.runId || entry.runId,
                  sessionId: item.sessionId || entry.sessionId,
                  status: histStatus ?? entry.status,
                  finishedAt:
                    histStatus && histStatus !== 'running'
                      ? Date.now()
                      : entry.finishedAt,
                  approvalId: item.approvalId ?? entry.approvalId,
                  summary: item.message || entry.summary,
                }
              })
            }
            return {
              ...current,
              runLog,
              nodeRunStatus,
              runHistory,
              lastRunId: item.runId || current.lastRunId,
              lastSessionId: item.sessionId || current.lastSessionId,
              lastApprovalId: item.approvalId ?? current.lastApprovalId,
              // stream ends on pause; treat as not actively streaming
              running:
                item.type === 'workflow.paused' ||
                item.type === 'workflow.completed' ||
                item.type === 'workflow.failed' ||
                item.type === 'workflow.cancelled'
                  ? false
                  : current.running,
            }
          })
        },
        controller.signal
      )
      setState((current) => ({ ...current, running: false }))
    } catch (error) {
      if (controller.signal.aborted) {
        setState((current) => ({ ...current, running: false }))
        return
      }
      setState((current) => ({
        ...current,
        running: false,
        error: error instanceof Error ? error.message : 'Run failed',
      }))
    }
  }

  const stop = () => {
    abortRef.current?.abort()
    setState((current) => ({
      ...current,
      running: false,
      runHistory: current.runHistory.map((entry, index) =>
        index === 0 && entry.status === 'running'
          ? { ...entry, status: 'cancelled', finishedAt: Date.now() }
          : entry
      ),
    }))
  }

  const selected = useMemo(
    () => (state.selectedId ? findNode(state.steps, state.selectedId) : null),
    [state.selectedId, state.steps]
  )

  return {
    state,
    selected,
    canUndo,
    canRedo,
    workflowsQuery,
    executorsQuery,
    modelsQuery,
    versionsQuery,
    templatesQuery,
    patch,
    patchMeta,
    patchTriggers,
    select,
    selectMany,
    add,
    addAt,
    addChild,
    addToSlot,
    update,
    remove,
    removeSelected,
    move,
    applyPositions,
    reparent,
    connectSequence,
    connectBranch,
    organizeLayout,
    copySelected,
    pasteClipboard,
    duplicateSelected,
    undo,
    redo,
    load,
    applyTemplate,
    reset,
    save,
    publish,
    restoreVersion,
    removeSaved,
    run,
    stop,
  }
}
