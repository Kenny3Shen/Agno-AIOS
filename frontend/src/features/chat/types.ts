import type { JsonRecord, ModelConfig } from '@/shared/types/common'

export interface RunMetrics { input_tokens?: number | null; output_tokens?: number | null; total_tokens?: number | null; duration?: number | null }
export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  final: boolean
  run_id?: string | null
  session_id?: string | null
  user_id?: string | null
  metrics?: RunMetrics | null
  raw_run?: JsonRecord | null
  tools?: unknown[] | null
}
export interface ChatSession { session_id: string; preview: string; created_at: number; updated_at: number; archived?: boolean; runs?: JsonRecord[] }
export interface ParsedMessage { body: string; thinking: string; sources: string[]; tools: string[] }
export interface ChatState {
  messages: Message[]
  input: string
  requesting: boolean
  error: string | null
  selectedModelId: string | null
}
export type ChatAction =
  | { type: 'history'; messages: Message[] }
  | { type: 'input'; value: string }
  | { type: 'start'; user?: Message; assistant: Message; modelId: string | null }
  | { type: 'chunk'; id: string; chunk: string }
  | { type: 'finish'; id: string }
  | { type: 'error'; id?: string; message: string }
  | { type: 'model'; value: string | null }
  | { type: 'reset' }

export type { ModelConfig }
