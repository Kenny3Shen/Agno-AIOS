import type { Step, WorkflowState } from './types'
export const createStep = (kind: Step['kind'] = 'agent'): Step => ({ id: crypto.randomUUID(), kind, targetId: '', name: '', instructions: '' })
export const moveStep = (steps: Step[], id: string, direction: -1 | 1) => { const index = steps.findIndex((step) => step.id === id); const target = index + direction; if (index < 0 || target < 0 || target >= steps.length) return steps; const next = [...steps]; [next[index], next[target]] = [next[target]!, next[index]!]; return next }
export const buildWorkflowCode = (state: WorkflowState) => {
  const steps = state.steps.map((step) => `    ${JSON.stringify({ name: step.name || step.targetId, executor_type: step.kind, executor_id: step.targetId, instructions: step.instructions })},`).join('\n')
  return `from agno.workflow import Workflow\n\nworkflow = Workflow(\n    name=${JSON.stringify(state.name || 'Security workflow')},\n    description=${JSON.stringify(state.description)},\n    steps=[\n${steps}\n    ],\n)\n\nworkflow.print_response(\n    input=${JSON.stringify(state.input)},\n    session_id=${JSON.stringify(state.sessionId)},\n    stream=True,\n    stream_events=True,\n)`
}
