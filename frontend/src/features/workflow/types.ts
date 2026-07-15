export type WorkflowNodeType = 'step' | 'parallel' | 'condition' | 'loop'

export type WorkflowNode = {
  id: string
  type: WorkflowNodeType
  name: string
  /** Leaf agent step */
  kind?: 'agent'
  targetId?: string
  instructions?: string
  /** parallel / loop children */
  steps?: WorkflowNode[]
  /** condition */
  evaluatorCel?: string
  thenSteps?: WorkflowNode[]
  elseSteps?: WorkflowNode[]
  /** loop */
  maxIterations?: number
  endConditionCel?: string
}

/** @deprecated prefer WorkflowNode; kept as alias for leaf steps */
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
}

export type WorkflowDefinition = {
  name: string
  description: string
  steps: WorkflowDefinitionNode[]
}

export type WorkflowRecord = {
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
  | 'parallel.started'
  | 'parallel.completed'
  | 'condition.started'
  | 'condition.completed'
  | 'loop.started'
  | 'loop.completed'
  | 'loop.iteration.started'
  | 'loop.iteration.completed'

export interface WorkflowRunLogItem {
  id: string
  type: WorkflowRunEventType | string
  message: string
  stepName?: string | null
  content?: string | null
  at: number
}
