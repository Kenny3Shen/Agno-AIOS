export type StepKind = 'agent'

export interface WorkflowStep {
  id: string
  type: 'step'
  kind: StepKind
  targetId: string
  name: string
  instructions: string
}

export interface WorkflowDefinition {
  name: string
  description: string
  steps: Array<{
    id: string
    type: 'step'
    name: string
    executor: { kind: 'agent'; ref: string }
    instructions: string
  }>
}

export interface WorkflowRecord {
  id: string
  name: string
  description: string
  owner_user_id: string
  definition: WorkflowDefinition
  enabled: boolean
  version: number
  created_at: number
  updated_at: number
}

export interface ExecutorOption {
  ref: string
  kind: string
  name: string
  description: string
}

export interface WorkflowState {
  workflowId: string | null
  name: string
  description: string
  input: string
  sessionId: string
  modelId: string | null
  steps: WorkflowStep[]
  selectedId: string | null
  dirty: boolean
  saving: boolean
  running: boolean
  runLog: WorkflowRunLogItem[]
  error: string | null
  lastRunId: string | null
  lastSessionId: string | null
}

export type WorkflowRunEventType =
  | 'workflow.started'
  | 'workflow.completed'
  | 'workflow.failed'
  | 'workflow.cancelled'
  | 'workflow.paused'
  | 'step.started'
  | 'step.completed'
  | 'step.error'

export interface WorkflowRunLogItem {
  id: string
  type: WorkflowRunEventType | string
  message: string
  stepName?: string | null
  content?: string | null
  at: number
}
