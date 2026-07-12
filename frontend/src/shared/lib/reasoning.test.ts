import { describe, expect, it } from 'vitest'
import { openaiReasoningEfforts, reasoningEffortLabel } from './reasoning'

describe('reasoning effort labels', () => {
  it('uses Agno OpenAI reasoning effort values by protocol', () => {
    expect(openaiReasoningEfforts('responses')).toEqual(['minimal', 'low', 'medium', 'high'])
    expect(openaiReasoningEfforts('chat-completions')).toEqual(['low', 'medium', 'high'])
  })

  it('keeps labels literal', () => {
    expect(reasoningEffortLabel('minimal')).toBe('Minimal')
    expect(reasoningEffortLabel('high')).toBe('High')
    expect(reasoningEffortLabel('max')).toBe('Max')
  })
})
