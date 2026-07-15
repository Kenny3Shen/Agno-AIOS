import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { WorkflowState, WorkflowStep } from './types'
import { createStep, fromRecord, moveStep, toDefinition } from './utils'
import {
  createWorkflow,
  deleteWorkflow,
  listExecutors,
  listWorkflows,
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

  useEffect(() => {
    const active = modelsQuery.data?.active_model_id
    if (active && !state.modelId) {
      setState((current) => ({ ...current, modelId: active }))
    }
  }, [modelsQuery.data?.active_model_id, state.modelId])

  const patch = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value, dirty: value.dirty === false ? false : true }))
  }, [])

  const patchMeta = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value }))
  }, [])

  const add = (kind: WorkflowStep['kind'] = 'agent') => {
    const step = createStep(kind)
    setState((current) => ({
      ...current,
      steps: [...current.steps, step],
      selectedId: step.id,
      dirty: true,
    }))
  }

  const update = (step: WorkflowStep) =>
    setState((current) => ({
      ...current,
      dirty: true,
      steps: current.steps.map((item) => (item.id === step.id ? step : item)),
    }))

  const remove = (id: string) =>
    setState((current) => ({
      ...current,
      dirty: true,
      steps: current.steps.filter((item) => item.id !== id),
      selectedId: current.selectedId === id ? null : current.selectedId,
    }))

  const move = (id: string, direction: -1 | 1) =>
    setState((current) => ({ ...current, dirty: true, steps: moveStep(current.steps, id, direction) }))

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
    } catch (error) {
      setState((current) => ({
        ...current,
        saving: false,
        error: error instanceof Error ? error.message : 'Save failed',
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
            lastRunId:
              item.type === 'workflow.started' || item.type === 'step.started'
                ? current.lastRunId
                : current.lastRunId,
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
    () => state.steps.find((step) => step.id === state.selectedId) ?? null,
    [state.selectedId, state.steps]
  )

  return {
    state,
    selected,
    workflowsQuery,
    executorsQuery,
    modelsQuery,
    patch,
    patchMeta,
    add,
    update,
    remove,
    move,
    load,
    reset,
    save,
    removeSaved,
    run,
    stop,
  }
}
