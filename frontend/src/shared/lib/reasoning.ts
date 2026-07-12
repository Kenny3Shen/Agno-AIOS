import type { ModelConfig, ReasoningEffort } from '@/shared/types/common'

export const OPENAI_RESPONSES_REASONING_EFFORTS: ReasoningEffort[] = ['minimal', 'low', 'medium', 'high']
export const OPENAI_CHAT_REASONING_EFFORTS: ReasoningEffort[] = ['low', 'medium', 'high']
export const DEEPSEEK_REASONING_EFFORTS: ReasoningEffort[] = ['high', 'max']

const titleCase = (value: string) => value[0]?.toUpperCase() + value.slice(1)

export const openaiReasoningEfforts = (protocol: ModelConfig['api_protocol']) =>
  protocol === 'responses' ? OPENAI_RESPONSES_REASONING_EFFORTS : OPENAI_CHAT_REASONING_EFFORTS

export const reasoningEffortLabel = (value: ReasoningEffort) => titleCase(value)
