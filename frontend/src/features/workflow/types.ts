export type WorkflowNodeType =
  | 'step'
  | 'parallel'
  | 'condition'
  | 'loop'
  | 'router'
  | 'workflow_ref'

export type WorkflowNode = {
  id: string
  type: WorkflowNodeType
  name: string
  kind?: 'agent'
  targetId?: string
  instructions?: string
  steps?: WorkflowNode[]
  evaluatorCel?: string
  thenSteps?: WorkflowNode[]
  elseSteps?: WorkflowNode[]
  maxIterations?: number
  endConditionCel?: string
  /** router */
  selectorCel?: string
  choices?: Array<{ id: string; name: string; steps: WorkflowNode[] }>
  /** nested workflow */
  workflowId?: string
  /** HITL */
  requiresConfirmation?: boolean
  confirmationMessage?: string
  requiresUserInput?: boolean
  userInputMessage?: string
  requiresOutputReview?: boolean
  outputReviewMessage?: string
  /** canvas layout */
  position?: { x: number; y: number }
}

export type WorkflowStep = WorkflowNode

export type WorkflowDefinitionNode = {
  id: string
  type: WorkflowNodeType
  name: string
  executor?: { kind: 'agent'; ref: string }
  instructions?: string
  steps?: WorkflowDefinitionNode[]
  evaluator?: { cel?: string; value?: boolean }
  then_steps?: WorkflowDefinitionNode[]
  else_steps?: WorkflowDefinitionNode[]
  max_iterations?: number
  end_condition?: { cel?: string; value?: boolean } | null
  selector?: { cel?: string }
  choices?: Array<{ id: string; name: string; steps: WorkflowDefinitionNode[] }>
  workflow_id?: string
  requires_confirmation?: boolean
  confirmation_message?: string
  requires_user_input?: boolean
  user_input_message?: string
  requires_output_review?: boolean
  output_review_message?: string
  position?: { x: number; y: number }
}

export type WorkflowDefinition = {
  name: string
  description: string
  steps: WorkflowDefinitionNode[]
}

export type WorkflowTriggers = {
  webhook: { enabled: boolean; secret: string }
  cron: { enabled: boolean; expression: string }
}

export type WorkflowRecord = {
  id: string
  name: string
  description: string
  owner_user_id: string
  definition: WorkflowDefinition
  triggers?: WorkflowTriggers
  enabled: boolean
  version: number
  created_at: number
  updated_at: number
}

export type WorkflowVersionRecord = {
  id: string
  workflow_id: string
  version: number
  name: string
  description: string
  definition: WorkflowDefinition
  triggers?: WorkflowTriggers
  created_at: number
  created_by: string
}

export type ExecutorOption = {
  ref: string
  kind: string
  name: string
  description: string
}

export type WorkflowState = {
  workflowId: string | null
  name: string
  description: string
  input: string
  sessionId: string
  modelId: string | null
  steps: WorkflowNode[]
  triggers: WorkflowTriggers
  selectedId: string | null
  /** Multi-select (includes selectedId when set). */
  selectedIds: string[]
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
  | 'parallel.started'
  | 'parallel.completed'
  | 'condition.started'
  | 'condition.completed'
  | 'loop.started'
  | 'loop.completed'
  | 'loop.iteration.started'
  | 'loop.iteration.completed'
  | 'router.started'
  | 'router.completed'

export interface WorkflowRunLogItem {
  id: string
  type: WorkflowRunEventType | string
  message: string
  stepName?: string | null
  content?: string | null
  at: number
}
