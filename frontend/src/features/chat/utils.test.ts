import { describe, expect, it } from 'vitest'
import { chatReducer, consumeSse, defaultReasoningEffort, initialChatState, previousPrompt, supportedReasoningEfforts } from './utils'
import type { Message } from './types'

describe('chat behavior', () => {
  it('keeps stream chunks in arrival order', async () => {
    const encoded = new TextEncoder().encode('data: first\n\ndata: second\n\ndata: [DONE]\n\n')
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoded.slice(0, 17))
        controller.enqueue(encoded.slice(17))
        controller.close()
      },
    })
    const chunks: string[] = []
    await consumeSse(stream, ({ data }) => {
      if (data !== '[DONE]') chunks.push(data)
    })
    expect(chunks).toEqual(['first', 'second'])
  })

  it('preserves a partial answer when a request fails', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false }
    const started = chatReducer(initialChatState, {
      type: 'start',
      user: { id: 'u', role: 'user', content: 'prompt', final: true },
      assistant,
      modelId: 'model',
    })
    const streamed = chatReducer(started, { type: 'event', id: 'a', event: { type: 'content.delta', delta: 'partial' } })
    const failed = chatReducer(streamed, {
      type: 'event',
      id: 'a',
      event: { type: 'run.failed', code: 'NETWORK', message: 'offline', retryable: true },
    })
    expect(failed.messages[failed.messages.length - 1]?.content).toBe('partial')
    expect(failed.messages[failed.messages.length - 1]?.final).toBe(true)
  })

  it('finds the prompt that belongs to a retried answer', () => {
    const messages: Message[] = [
      { id: 'u', role: 'user', content: 'inspect', final: true },
      { id: 'a', role: 'assistant', content: 'result', final: true },
    ]
    expect(previousPrompt(messages, 'a')).toBe('inspect')
  })

  it('updates the reasoning effort when changing the model or starting a new chat', () => {
    const selected = chatReducer(initialChatState, { type: 'reasoning-effort', value: 'max' })
    expect(chatReducer(selected, { type: 'model', value: 'model-2', reasoningEffort: 'low' }).reasoningEffort).toBe('low')
    expect(chatReducer(selected, { type: 'reset' }).reasoningEffort).toBeNull()
  })

  it('uses only supported explicit reasoning strengths and selects the configured default', () => {
    const model = {
      id: 'openai',
      name: 'OpenAI',
      model_id: 'gpt',
      provider: 'openai' as const,
      api_protocol: 'responses' as const,
      structured_output_mode: 'native' as const,
      default_reasoning_effort: 'medium' as const,
      base_url: '',
      api_key: '',
      description: '',
      enabled: true,
      builtin: false,
    }
    expect(supportedReasoningEfforts(model)).toEqual(['minimal', 'low', 'medium', 'high'])
    expect(defaultReasoningEffort(model)).toBe('medium')
    expect(defaultReasoningEffort({ ...model, provider: 'openai-compatible' })).toBeNull()
  })

  it('keeps protocol metadata separate from markdown content', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const withTool = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'tool.update', tool: { id: 'lookup', name: 'CVE lookup', status: 'loading' } },
    })
    const completed = chatReducer(withTool, {
      type: 'event',
      id: 'a',
      event: { type: 'run.completed', runId: 'run-1', metrics: { total_tokens: 10 }, followups: ['Assess impact'] },
    })
    expect(completed.messages[0]).toMatchObject({
      content: '',
      run_id: 'run-1',
      status: 'completed',
      tool_steps: [{ id: 'lookup', name: 'CVE lookup', status: 'loading' }],
      followups: ['Assess impact'],
    })
  })
})
