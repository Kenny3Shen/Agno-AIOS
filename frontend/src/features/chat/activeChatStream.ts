/**
 * Process-wide handle for the single live Chat SSE stream.
 *
 * ChatPage and ChatTaskPanel each call useChat() with independent reducer
 * state; only one instance owns the in-flight stream. Session switches from
 * the sidebar must abort that stream even when the panel instance is idle.
 */

export type ActiveChatStream = {
  controller: AbortController
  runId: string | null
  sessionId: string | null
}

let active: ActiveChatStream | null = null

export function getActiveChatStream(): ActiveChatStream | null {
  return active
}

/** Register the live stream, aborting any previous controller first. */
export function registerChatStream(controller: AbortController, sessionId: string | null): void {
  if (active && active.controller !== controller) {
    try {
      active.controller.abort()
    } catch {
      // ignore
    }
  }
  active = { controller, runId: null, sessionId }
}

export function updateChatStreamRunId(runId: string): void {
  if (!active || !runId) return
  active.runId = runId
}

/** Clear the registry when this controller finishes (success, cancel, or error). */
export function clearChatStream(controller?: AbortController | null): void {
  if (!active) return
  if (controller && active.controller !== controller) return
  active = null
}

/**
 * Abort the live client SSE (if any) and return its run id for best-effort
 * server cancel. Safe to call when no stream is active.
 */
export function abortActiveChatStream(): { runId: string | null; sessionId: string | null } {
  if (!active) return { runId: null, sessionId: null }
  const { controller, runId, sessionId } = active
  active = null
  try {
    controller.abort()
  } catch {
    // ignore
  }
  return { runId, sessionId }
}

/** Test helper — reset module state between tests. */
export function __resetActiveChatStreamForTests(): void {
  active = null
}
