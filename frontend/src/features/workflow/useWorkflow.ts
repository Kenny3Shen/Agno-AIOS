import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { WorkflowNode, WorkflowNodeType, WorkflowState, WorkflowTriggers } from './types'
import {
  addChildToNode,
  createNode,
  defaultTriggers,
  findNode,
  fromRecord,
  moveNodeAfter,
  moveStep,
  removeNodeInTree,
  reorderRootsByPositions,
  toDefinition,
  updateNodeInTree,
} from './utils'
import {
  createWorkflow,
  deleteWorkflow,
  listExecutors,
  listWorkflowVersions,
  listWorkflows,
  restoreWorkflowVersion,
  streamWorkflowRun,
  updateWorkflow,
} from './api'
import { getModels } from '@/features/chat/api'

const initialState = (): WorkflowState => ({
  workflowId: null,
  name: 'Security response workflow',
  description: '',
  input: 'Analyze the incident and propose containment steps.',
  sessionId: crypto.randomUUID(),
  modelId: null,
  steps: [],
  triggers: defaultTriggers(),
  selectedId: null,
  dirty: false,
  saving: false,
  running: false,
  runLog: [],
  error: null,
  lastRunId: null,
  lastSessionId: null,
})

export function useWorkflow() {
  const [state, setState] = useState<WorkflowState>(initialState)
  const abortRef = useRef<AbortController | null>(null)

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

  useEffect(() => {
    const active = modelsQuery.data?.active_model_id
    if (active && !state.modelId) {
      setState((current) => ({ ...current, modelId: active }))
    }
  }, [modelsQuery.data?.active_model_id, state.modelId])

  const patch = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value, dirty: value.dirty !== false }))
  }, [])

  const patchMeta = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value }))
  }, [])

  const add = (type: WorkflowNodeType = 'step') => {
    const node = createNode(type)
    setState((current) => ({
      ...current,
      steps: [...current.steps, node],
      selectedId: node.id,
      dirty: true,
    }))
  }

  const addChild = (
    parentId: string,
    branch: 'steps' | 'thenSteps' | 'elseSteps',
    type: WorkflowNodeType = 'step'
  ) => {
    const child = createNode(type)
    setState((current) => ({
      ...current,
      dirty: true,
      selectedId: child.id,
      steps: addChildToNode(current.steps, parentId, branch, child),
    }))
  }

  const update = (node: WorkflowNode) =>
    setState((current) => ({
      ...current,
      dirty: true,
      steps: updateNodeInTree(current.steps, node.id, () => node),
    }))

  const remove = (id: string) =>
    setState((current) => ({
      ...current,
      dirty: true,
      steps: removeNodeInTree(current.steps, id),
      selectedId: current.selectedId === id ? null : current.selectedId,
    }))

  const move = (id: string, direction: -1 | 1) =>
    setState((current) => ({ ...current, dirty: true, steps: moveStep(current.steps, id, direction) }))

  const applyPositions = (positions: Record<string, { x: number; y: number }>) => {
    setState((current) => {
      let steps = current.steps
      for (const [id, position] of Object.entries(positions)) {
        steps = updateNodeInTree(steps, id, (node) => ({ ...node, position }))
      }
      // reorder roots by Y after drag
      steps = reorderRootsByPositions(steps)
      return { ...current, steps, dirty: true }
    })
  }

  const connectSequence = (sourceId: string, targetId: string) => {
    setState((current) => ({
      ...current,
      dirty: true,
      steps: moveNodeAfter(current.steps, targetId, sourceId),
    }))
  }

  const patchTriggers = (triggers: WorkflowTriggers) => {
    setState((current) => ({ ...current, triggers, dirty: true }))
  }

  const load = (id: string) => {
    const record = (workflowsQuery.data ?? []).find((item) => item.id === id)
    if (!record) return
    setState((current) => ({
      ...current,
      ...fromRecord(record),
      input: current.input,
      sessionId: crypto.randomUUID(),
      runLog: [],
      error: null,
      dirty: false,
    }))
  }

  const reset = () => {
    abortRef.current?.abort()
    setState(initialState())
  }

  const save = async () => {
    if (!state.steps.length) {
      setState((current) => ({ ...current, error: 'Add at least one step before saving' }))
      return
    }
    setState((current) => ({ ...current, saving: true, error: null }))
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
      setState((current) => ({
        ...current,
        ...fromRecord(record),
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

  const restoreVersion = async (version: number) => {
    if (!state.workflowId) return
    try {
      const record = await restoreWorkflowVersion(state.workflowId, version)
      setState((current) => ({
        ...current,
        ...fromRecord(record),
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
    setState((current) => ({
      ...current,
      running: true,
      error: null,
      runLog: [],
      sessionId,
      lastSessionId: sessionId,
      lastRunId: null,
    }))
    try {
      await streamWorkflowRun(
        state.workflowId,
        { input: state.input, session_id: sessionId, model_id: state.modelId },
        (item) => {
          setState((current) => ({
            ...current,
            runLog: [...current.runLog, item],
          }))
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
    setState((current) => ({ ...current, running: false }))
  }

  const selected = useMemo(
    () => (state.selectedId ? findNode(state.steps, state.selectedId) : null),
    [state.selectedId, state.steps]
  )

  return {
    state,
    selected,
    workflowsQuery,
    executorsQuery,
    modelsQuery,
    versionsQuery,
    patch,
    patchMeta,
    patchTriggers,
    add,
    addChild,
    update,
    remove,
    move,
    applyPositions,
    connectSequence,
    load,
    reset,
    save,
    restoreVersion,
    removeSaved,
    run,
    stop,
  }
}
