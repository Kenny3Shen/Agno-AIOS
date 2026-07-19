/**
 * Process-wide handle for the single live Chat SSE stream.
 *
 * ChatPage owns the stream via useChat(); ChatTaskPanel only lists sessions
 * but can abort the live stream when the user switches or archives a session.
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
