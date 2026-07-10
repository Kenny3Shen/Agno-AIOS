import { describe, expect, it } from 'vitest'
import { chatReducer, consumeSse, initialChatState, parseMessage, previousPrompt } from './utils'
import type { Message } from './types'

describe('chat behavior', () => {
  it('keeps stream chunks in arrival order', async () => {
    const encoded = new TextEncoder().encode('data: first\n\ndata: second\n\ndata: [DONE]\n\n')
    const stream = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(encoded.slice(0, 17)); controller.enqueue(encoded.slice(17)); controller.close() } })
    const chunks: string[] = []
    await consumeSse(stream, ({ data }) => { if (data !== '[DONE]') chunks.push(data) })
    expect(chunks).toEqual(['first', 'second'])
  })

  it('preserves a partial answer when a request fails', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false }
    const started = chatReducer(initialChatState, { type: 'start', user: { id: 'u', role: 'user', content: 'prompt', final: true }, assistant, modelId: 'model' })
    const streamed = chatReducer(started, { type: 'chunk', id: 'a', chunk: 'partial' })
    const failed = chatReducer(streamed, { type: 'error', id: 'a', message: 'offline' })
    expect(failed.messages[failed.messages.length - 1]?.content).toBe('partial')
    expect(failed.messages[failed.messages.length - 1]?.final).toBe(true)
  })

  it('finds the prompt that belongs to a retried answer', () => {
    const messages: Message[] = [{ id: 'u', role: 'user', content: 'inspect', final: true }, { id: 'a', role: 'assistant', content: 'result', final: true }]
    expect(previousPrompt(messages, 'a')).toBe('inspect')
  })

  it('separates model-provided reasoning, sources and tools from the answer', () => {
    expect(parseMessage('<think>checking</think>Answer\nSource: advisory\nTool call: search')).toEqual({ body: 'Answer', thinking: 'checking', sources: ['advisory'], tools: ['Tool call: search'] })
  })
})
