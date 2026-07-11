import type { JsonRecord, ModelConfig, ReasoningEffort } from '@/shared/types/common'

export interface RunMetrics {
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  duration?: number | null
}

export type RunStatus = 'streaming' | 'completed' | 'cancelled' | 'failed'
export type ToolStatus = 'loading' | 'success' | 'error' | 'abort'

export interface ToolStep {
  id: string
  name: string
  status: ToolStatus
  summary?: string | null
  duration?: number | null
  input?: unknown
  output?: unknown
}
export interface ThoughtStep { id: string; title: string; status: ToolStatus; summary?: string | null; duration?: number | null }
export interface ChatSource { id: string; title: string; url?: string | null; snippet?: string | null }

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  final: boolean
  status?: RunStatus
  run_id?: string | null
  session_id?: string | null
  user_id?: string | null
  metrics?: RunMetrics | null
  sources?: ChatSource[] | null
  tool_steps?: ToolStep[] | null
  thought_chain?: ThoughtStep[] | null
  reasoning?: string | null
  followups?: string[] | null
  error?: { code?: string; message: string; retryable?: boolean } | null
  raw_run?: JsonRecord | null
  tools?: unknown[] | null
}

export interface ChatSession { session_id: string; preview: string; title?: string | null; created_at: number; updated_at: number; archived?: boolean; runs?: JsonRecord[] }
export interface ChatState {
  messages: Message[]
  input: string
  requesting: boolean
  error: string | null
  selectedModelId: string | null
  reasoningEffort: ReasoningEffort | null
}

export type ChatRunEvent =
  | { type: 'run.started'; runId: string; sessionId?: string; model?: string; provider?: string }
  | { type: 'content.delta'; runId?: string; delta: string }
  | { type: 'tool.update'; runId?: string; tool: ToolStep }
  | { type: 'reasoning.delta'; runId?: string; delta: string }
  | { type: 'thought.update'; runId?: string; thought: ThoughtStep }
  | { type: 'sources'; runId?: string; items: ChatSource[] }
  | { type: 'run.completed'; runId?: string; sessionId?: string; metrics?: RunMetrics | null; followups?: string[] }
  | { type: 'run.cancelled'; runId?: string; reason?: string }
  | { type: 'run.failed'; runId?: string; code?: string; message: string; retryable?: boolean }

export type ChatAction =
  | { type: 'history'; messages: Message[] }
  | { type: 'input'; value: string }
  | { type: 'start'; user?: Message; assistant: Message; modelId: string | null }
  | { type: 'event'; id: string; event: ChatRunEvent }
  | { type: 'network-error'; id: string; message: string }
  | { type: 'model'; value: string | null }
  | { type: 'reasoning-effort'; value: ReasoningEffort | null }
  | { type: 'reset' }

export type { ModelConfig }
