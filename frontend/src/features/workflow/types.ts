/**
 * Shared Workflow Studio types (nodes, triggers, run log, React Query state).
 */
export type UserInputSchemaField = {
  name: string
  field_type?: string
  description?: string
  required?: boolean
}

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
  /** Bound skill directory/metadata names (enabled ∩ bound at run). */
  skills?: string[]
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
  /** Agno-style field schema for user_input HITL */
  userInputSchema?: UserInputSchemaField[]
  requiresOutputReview?: boolean
  outputReviewMessage?: string
  /** canvas layout */
  position?: { x: number; y: number }
}

export type WorkflowDefinitionNode = {
  id: string
  type: WorkflowNodeType
  name: string
  executor?: { kind: 'agent'; ref: string }
  instructions?: string
  skills?: string[]
  steps?: WorkflowDefinitionNode[]
  evaluator?: { cel?: string; value?: boolean }
  else?: WorkflowDefinitionNode[]
  max_iterations?: number
  end_condition?: { cel?: string; value?: boolean } | null
  selector?: { cel?: string }
  choices?: Array<{ id: string; name: string; steps: WorkflowDefinitionNode[] }>
  workflow_id?: string
  requires_confirmation?: boolean
  confirmation_message?: string
  requires_user_input?: boolean
  user_input_message?: string
  user_input_schema?: UserInputSchemaField[]
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
  cron: { enabled: boolean; expression: string; last_run_at?: number }
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
  published_version?: number | null
  published_at?: number | null
  has_published?: boolean
  /** Unix seconds for next cron fire when cron enabled (server-computed). */
  next_cron_at?: number | null
  created_at: number
  updated_at: number
}

export type ExecutorOption = {
  ref: string
  kind: string
  name: string
  description: string
  category?: string
  capabilities?: string
  recommendedFor?: string
  role?: string
  attachSkills: boolean
  supportsHitl: boolean
}

/** Built-in business preset or user custom step node for the Studio palette. */
export type WorkflowNodePreset = {
  id: string
  name: string
  description: string
  color: string
  source: 'builtin' | 'user'
  definition: {
    type: 'step'
    name: string
    executor: { kind: 'agent'; ref: string }
    instructions?: string
    skills?: string[]
    requires_confirmation?: boolean
    confirmation_message?: string
    requires_user_input?: boolean
    user_input_message?: string
    user_input_schema?: UserInputSchemaField[]
    requires_output_review?: boolean
    output_review_message?: string
  }
  created_at?: number
  updated_at?: number
}

export type WorkflowState = {
  workflowId: string | null
  name: string
  description: string
  input: string
  sessionId: string
  modelId: string | null
  /** Draft revision counter from API (bumps on save). */
  version: number
  /** Live revision used by webhook/cron; null when never published. */
  publishedVersion: number | null
  /** Unix seconds when published revision was set. */
  publishedAt: number | null
  hasPublished: boolean
  /** Server next cron fire (unix sec); refreshed on load/save. */
  nextCronAt: number | null
  steps: WorkflowNode[]
  triggers: WorkflowTriggers
  selectedId: string | null
  /** Multi-select (includes selectedId when set). */
  selectedIds: string[]
  dirty: boolean
  /** Loading a saved workflow by id (deep link / library). */
  loading: boolean
  saving: boolean
  running: boolean
  runLog: WorkflowRunLogItem[]
  /** Per-node run visualization: running | ok | error | paused */
  nodeRunStatus: Record<string, WorkflowNodeRunStatus>
  runHistory: WorkflowRunHistoryItem[]
  error: string | null
  /** Client-side save validation (node-linked). */
  validationIssues: Array<{ nodeId: string | null; code: string; message: string }>
  /** Bumped on each failed validation so canvas can re-focus. */
  validationEpoch: number
  /** Bumped when a workflow is loaded/template-applied so canvas can fitView. */
  focusEpoch: number
  lastRunId: string | null
  lastSessionId: string | null
  lastApprovalId: string | null
}

type WorkflowRunEventType =
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

export type WorkflowNodeRunStatus = 'running' | 'ok' | 'error' | 'paused'

export interface WorkflowRunLogItem {
  id: string
  type: WorkflowRunEventType | string
  message: string
  stepName?: string | null
  stepId?: string | null
  content?: string | null
  approvalId?: string | null
  pauseType?: string | null
  runId?: string | null
  sessionId?: string | null
  at: number
}

export interface WorkflowRunHistoryItem {
  id: string
  runId: string
  sessionId: string
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'paused'
  startedAt: number
  finishedAt?: number
  approvalId?: string | null
  summary?: string
}
