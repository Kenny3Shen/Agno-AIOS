import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  __resetActiveChatStreamForTests,
  abortActiveChatStream,
  clearChatStream,
  getActiveChatStream,
  registerChatStream,
  updateChatStreamRunId,
} from './activeChatStream'

afterEach(() => {
  __resetActiveChatStreamForTests()
})

describe('activeChatStream registry', () => {
  it('registers a stream and tracks run id', () => {
    const controller = new AbortController()
    registerChatStream(controller, 'sess-a')
    expect(getActiveChatStream()).toMatchObject({
      controller,
      runId: null,
      sessionId: 'sess-a',
    })
    updateChatStreamRunId('run-1')
    expect(getActiveChatStream()?.runId).toBe('run-1')
  })

  it('aborts the previous controller when a new stream registers', () => {
    const first = new AbortController()
    const second = new AbortController()
    registerChatStream(first, 'sess-a')
    registerChatStream(second, 'sess-b')
    expect(first.signal.aborted).toBe(true)
    expect(second.signal.aborted).toBe(false)
    expect(getActiveChatStream()?.controller).toBe(second)
  })

  it('abortActiveChatStream aborts, returns run id, and clears registry', () => {
    const controller = new AbortController()
    registerChatStream(controller, 'sess-a')
    updateChatStreamRunId('run-42')
    const result = abortActiveChatStream()
    expect(result).toEqual({ runId: 'run-42', sessionId: 'sess-a' })
    expect(controller.signal.aborted).toBe(true)
    expect(getActiveChatStream()).toBeNull()
    // Second abort is a no-op
    expect(abortActiveChatStream()).toEqual({ runId: null, sessionId: null })
  })

  it('clearChatStream only clears the matching controller', () => {
    const controller = new AbortController()
    const other = new AbortController()
    registerChatStream(controller, 'sess-a')
    clearChatStream(other)
    expect(getActiveChatStream()?.controller).toBe(controller)
    clearChatStream(controller)
    expect(getActiveChatStream()).toBeNull()
  })

  it('supports dual-instance session switch: idle panel aborts page-owned stream', () => {
    // Simulates ChatPage owning the SSE while ChatTaskPanel setSession aborts globally.
    const pageController = new AbortController()
    registerChatStream(pageController, 'sess-streaming')
    updateChatStreamRunId('run-live')

    const fromPanel = abortActiveChatStream()
    expect(fromPanel.runId).toBe('run-live')
    expect(pageController.signal.aborted).toBe(true)
    expect(getActiveChatStream()).toBeNull()
  })

  it('does not throw when aborting an already-aborted controller', () => {
    const controller = new AbortController()
    registerChatStream(controller, 'sess-a')
    controller.abort()
    expect(() => abortActiveChatStream()).not.toThrow()
    expect(getActiveChatStream()).toBeNull()
  })

  it('clearChatStream with no arg clears current stream', () => {
    const controller = new AbortController()
    registerChatStream(controller, 'sess-a')
    clearChatStream()
    expect(getActiveChatStream()).toBeNull()
  })

  it('registering the same controller does not re-abort it', () => {
    const controller = new AbortController()
    const abortSpy = vi.spyOn(controller, 'abort')
    registerChatStream(controller, 'sess-a')
    registerChatStream(controller, 'sess-a')
    expect(abortSpy).not.toHaveBeenCalled()
    expect(controller.signal.aborted).toBe(false)
  })
})
