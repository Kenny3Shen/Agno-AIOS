export type StepKind = 'agent' | 'team' | 'workflow'
export interface Step {
  id: string
  kind: StepKind
  targetId: string
  name: string
  instructions: string
}
export interface WorkflowState {
  name: string
  description: string
  input: string
  sessionId: string
  steps: Step[]
  selectedId: string | null
}
