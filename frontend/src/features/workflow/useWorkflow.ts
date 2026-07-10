import { useState } from 'react'
import type { Step, WorkflowState } from './types'
import { createStep, moveStep } from './utils'
export function useWorkflow() {
  const [state, setState] = useState<WorkflowState>({ name: 'Security response workflow', description: '', input: 'Analyze the incident and propose containment steps.', sessionId: crypto.randomUUID(), steps: [], selectedId: null })
  const patch = (value: Partial<WorkflowState>) => setState((current) => ({ ...current, ...value }))
  const add = (kind: Step['kind']) => { const step = createStep(kind); setState((current) => ({ ...current, steps: [...current.steps, step], selectedId: step.id })) }
  const update = (step: Step) => setState((current) => ({ ...current, steps: current.steps.map((item) => item.id === step.id ? step : item) }))
  const remove = (id: string) => setState((current) => ({ ...current, steps: current.steps.filter((item) => item.id !== id), selectedId: current.selectedId === id ? null : current.selectedId }))
  const move = (id: string, direction: -1 | 1) => setState((current) => ({ ...current, steps: moveStep(current.steps, id, direction) }))
  return { state, selected: state.steps.find((step) => step.id === state.selectedId) ?? null, patch, add, update, remove, move }
}
