export type ResourceVisibility = 'private' | 'public'
export type ReasoningEffort = 'minimal' | 'low' | 'medium' | 'high' | 'max'

export interface ModelConfig {
  id: string
  name: string
  model_id: string
  provider: 'deepseek' | 'openai' | 'openai-compatible' | 'xai'
  api_protocol: 'chat-completions' | 'responses'
  structured_output_mode: 'native' | 'json'
  default_reasoning_effort?: ReasoningEffort | null
  /** Leave unset to use the provider default. */
  parallel_tool_calls?: boolean | null
  /** xAI / compatible live search (search_parameters). */
  live_search_enabled?: boolean
  /** Agno Model retries for 429/5xx (0 disables). */
  retries?: number
  delay_between_retries?: number
  exponential_backoff?: boolean
  /** OpenAI SDK HTTP client max_retries; leave unset for SDK default. */
  http_max_retries?: number | null
  base_url: string
  api_key: string
  description: string
  enabled: boolean
  builtin: boolean
  configured?: boolean
}

export interface ModelConfigResponse {
  active_model_id: string
  models: ModelConfig[]
}

export type JsonRecord = Record<string, unknown>
