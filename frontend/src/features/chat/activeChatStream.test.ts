import { afterEach, describe, expect, it } from 'vitest'
import {
  abortActiveChatStream,
  clearChatStream,
  getActiveChatStream,
  registerChatStream,
  updateChatStreamRunId,
} from './activeChatStream'

afterEach(() => {
  abortActiveChatStream()
})

describe('activeChatStream', () => {
  it('registers run id and aborts previous stream on re-register', () => {
    const first = new AbortController()
    const second = new AbortController()
    registerChatStream(first, 'sess-a')
    updateChatStreamRunId('run-1')
    expect(getActiveChatStream()).toMatchObject({ runId: 'run-1', sessionId: 'sess-a' })

    registerChatStream(second, 'sess-b')
    expect(first.signal.aborted).toBe(true)
    expect(getActiveChatStream()?.controller).toBe(second)
  })

  it('abortActiveChatStream returns run/session and clears registry', () => {
    const controller = new AbortController()
    registerChatStream(controller, 'sess-a')
    updateChatStreamRunId('run-42')
    expect(abortActiveChatStream()).toEqual({ runId: 'run-42', sessionId: 'sess-a' })
    expect(controller.signal.aborted).toBe(true)
    expect(getActiveChatStream()).toBeNull()
    expect(abortActiveChatStream()).toEqual({ runId: null, sessionId: null })
  })

  it('clearChatStream detaches without aborting (leave-page path)', () => {
    const controller = new AbortController()
    registerChatStream(controller, 's-leave')
    updateChatStreamRunId('run-leave')
    clearChatStream(controller)
    expect(controller.signal.aborted).toBe(false)
    expect(getActiveChatStream()).toBeNull()
  })
})
