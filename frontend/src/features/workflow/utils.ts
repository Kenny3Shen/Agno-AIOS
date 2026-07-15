import type { WorkflowDefinition, WorkflowRecord, WorkflowStep, WorkflowState } from './types'

export const createStep = (kind: WorkflowStep['kind'] = 'agent'): WorkflowStep => ({
  id: crypto.randomUUID(),
  type: 'step',
  kind,
  targetId: 'security-operations',
  name: '',
  instructions: '',
})

export const moveStep = (steps: WorkflowStep[], id: string, direction: -1 | 1) => {
  const index = steps.findIndex((step) => step.id === id)
  const target = index + direction
  if (index < 0 || target < 0 || target >= steps.length) return steps
  const next = [...steps]
  ;[next[index], next[target]] = [next[target]!, next[index]!]
  return next
}

export const toDefinition = (state: Pick<WorkflowState, 'name' | 'description' | 'steps'>): WorkflowDefinition => ({
  name: state.name || 'Untitled workflow',
  description: state.description || '',
  steps: state.steps.map((step) => ({
    id: step.id,
    type: 'step' as const,
    name: step.name || step.targetId || 'step',
    executor: { kind: 'agent' as const, ref: step.targetId || 'security-operations' },
    instructions: step.instructions || '',
  })),
})

export const fromRecord = (record: WorkflowRecord): Partial<WorkflowState> => {
  const steps = (record.definition?.steps ?? []).map((step) => ({
    id: step.id || crypto.randomUUID(),
    type: 'step' as const,
    kind: 'agent' as const,
    targetId: step.executor?.ref || 'security-operations',
    name: step.name || '',
    instructions: step.instructions || '',
  }))
  return {
    workflowId: record.id,
    name: record.name || record.definition?.name || '',
    description: record.description || record.definition?.description || '',
    steps,
    selectedId: steps[0]?.id ?? null,
    dirty: false,
  }
}

export const buildWorkflowCode = (state: WorkflowState) => {
  const definition = toDefinition(state)
  const steps = definition.steps
    .map(
      (step) =>
        `    Step(name=${JSON.stringify(step.name)}, step_id=${JSON.stringify(step.id)}, agent=agents[${JSON.stringify(step.executor.ref)}]),`
    )
    .join('\n')
  return [
    'from agno.workflow import Workflow, Step',
    '',
    `# Compiled from workbench definition (PR1 linear steps)`,
    `# workflow_id=${JSON.stringify(state.workflowId ?? '')}`,
    `workflow = Workflow(`,
    `    name=${JSON.stringify(definition.name)},`,
    `    description=${JSON.stringify(definition.description)},`,
    `    steps=[`,
    steps || '        # no steps',
    `    ],`,
    `)`,
    '',
    `workflow.print_response(`,
    `    input=${JSON.stringify(state.input)},`,
    `    session_id=${JSON.stringify(state.sessionId)},`,
    `    stream=True,`,
    `    stream_events=True,`,
    `)`,
  ].join('\n')
}
