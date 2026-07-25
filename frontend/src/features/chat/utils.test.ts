import { describe, expect, it } from 'vitest'
import { chatReducer, initialChatState } from './utils'
import type { Message } from './types'

const assistant = (overrides: Partial<Message> = {}): Message => ({
  id: 'a1',
  role: 'assistant',
  content: '',
  final: false,
  status: 'streaming',
  ...overrides,
})

describe('chatReducer business events', () => {
  it('attach-live marks requesting and a streaming assistant bubble', () => {
    const attached = chatReducer(initialChatState, {
      type: 'attach-live',
      messages: [{ id: 'u1', role: 'user', content: 'hi', final: true }],
      assistantId: 'run-live',
    })
    expect(attached.requesting).toBe(true)
    expect(attached.messages).toHaveLength(2)
    expect(attached.messages[1]).toMatchObject({
      id: 'run-live',
      role: 'assistant',
      status: 'streaming',
      final: false,
    })
  })

  it('marks a run cancelled and clears requesting', () => {
    const started = chatReducer(initialChatState, {
      type: 'start',
      assistant: assistant({ id: 'run-1' }),
      modelId: 'm1',
    })
    const cancelled = chatReducer(started, {
      type: 'event',
      id: 'run-1',
      event: { type: 'run.cancelled', runId: 'run-1', reason: 'Generation stopped' },
    })
    expect(cancelled.requesting).toBe(false)
    expect(cancelled.messages[0]).toMatchObject({ status: 'cancelled', final: true })
  })

  it('appends content deltas while streaming', () => {
    const started = chatReducer(initialChatState, {
      type: 'start',
      assistant: assistant({ id: 'run-1', content: 'Hel' }),
      modelId: 'm1',
    })
    const next = chatReducer(started, {
      type: 'event',
      id: 'run-1',
      event: { type: 'content.delta', runId: 'run-1', delta: 'lo' },
    })
    expect(next.messages[0]?.content).toBe('Hello')
    expect(next.requesting).toBe(true)
  })

  it('applies one animation-frame batch in event order', () => {
    const started = chatReducer(initialChatState, {
      type: 'start',
      assistant: assistant({ id: 'run-1' }),
      modelId: 'm1',
    })
    const next = chatReducer(started, {
      type: 'events',
      id: 'run-1',
      events: [
        { type: 'content.delta', runId: 'run-1', delta: 'Hel' },
        { type: 'content.delta', runId: 'run-1', delta: 'lo' },
        { type: 'run.completed', runId: 'run-1', sessionId: 's1' },
      ],
    })
    expect(next.messages[0]).toMatchObject({ content: 'Hello', status: 'completed', final: true })
    expect(next.requesting).toBe(false)
  })

  it('run.completed finalizes the assistant message', () => {
    const started = chatReducer(initialChatState, {
      type: 'start',
      assistant: assistant({ id: 'run-1', content: 'done' }),
      modelId: 'm1',
    })
    const completed = chatReducer(started, {
      type: 'event',
      id: 'run-1',
      event: { type: 'run.completed', runId: 'run-1', sessionId: 's1' },
    })
    expect(completed.requesting).toBe(false)
    expect(completed.messages[0]).toMatchObject({ status: 'completed', final: true })
  })
})
