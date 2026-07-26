import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, type Dispatch } from 'react'
import { useTranslation } from 'react-i18next'
import { createClientId } from '@/shared/lib/clientId'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { attachLiveSessionStream, cancelRun, streamMessage, unarchiveSession } from './api'
import { abortActiveChatStream, clearChatStream, registerChatStream, updateChatStreamRunId } from './activeChatStream'
import { ApiError } from '@/shared/api/client'
import {
  agentsQuery,
  chatKeys,
  flattenHistoryPages,
  historyQuery,
  modelsQuery,
  refreshLatestHistoryPage,
  SerialAsyncQueue,
  sessionMetaQuery,
  sessionsQuery,
} from './queries'
import { markSessionActiveInCaches } from './sessionCache'
import { formatAttachmentLimitError, validateChatAttachments } from './attachmentLimits'
import { chatReducer, defaultReasoningEffort, initialChatState, previousPrompt } from './utils'
import type { ChatAction, ChatRunEvent, ChatSession, Message } from './types'
import type { ReasoningEffort } from '@/shared/types/common'
import { buildTraceSearch, emptyTraceFilters } from '@/features/trace/utils'

const EMPTY_SESSIONS: ChatSession[] = []
const SSE_BATCH_FALLBACK_MS = 80

function bestEffortCancelRun(runId: string | null | undefined) {
  if (!runId) return
  void cancelRun(runId).catch((error: unknown) => {
    // Leaving the session: soft-error would be cleared by reset and is noisy.
    if (error instanceof ApiError && error.status === 404) return
    const detail = error instanceof Error ? error.message : String(error)
    console.warn(`[chat] cancel on session switch failed for ${runId}: ${detail}`)
  })
}

const isTerminalChatEvent = (event: ChatRunEvent) =>
  event.type === 'run.paused' || event.type === 'run.completed' || event.type === 'run.cancelled' || event.type === 'run.failed'

/** Batch high-frequency SSE updates to one reducer dispatch per animation frame. */
function useRafChatEventQueue(dispatch: Dispatch<ChatAction>, onFlushedEventIndex: (eventIndex: number) => void) {
  const pendingRef = useRef<Array<{ id: string; event: ChatRunEvent; eventIndex?: number }>>([])
  const frameRef = useRef<number | null>(null)
  const timeoutRef = useRef<number | null>(null)

  const cancelScheduledFlush = useCallback(() => {
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  const flush = useCallback(() => {
    cancelScheduledFlush()
    const pending = pendingRef.current
    pendingRef.current = []
    if (!pending.length) return
    const batches = new Map<string, ChatRunEvent[]>()
    let maxEventIndex: number | null = null
    for (const { id, event, eventIndex } of pending) {
      const events = batches.get(id)
      if (events) events.push(event)
      else batches.set(id, [event])
      if (typeof eventIndex === 'number' && Number.isFinite(eventIndex)) {
        maxEventIndex = maxEventIndex === null ? eventIndex : Math.max(maxEventIndex, eventIndex)
      }
    }
    for (const [id, events] of batches) {
      dispatch({ type: 'events', id, events })
    }
    // An event becomes resumable only after it has entered the reducer queue.
    // ``discard`` intentionally leaves unflushed indices untouched so a live
    // re-attach can replay those events instead of silently skipping a delta.
    if (maxEventIndex !== null) onFlushedEventIndex(maxEventIndex)
  }, [cancelScheduledFlush, dispatch, onFlushedEventIndex])

  const enqueue = useCallback(
    (id: string, event: ChatRunEvent, eventIndex?: number) => {
      pendingRef.current.push({ id, event, eventIndex })
      // Do not leave completion/error state visually stale for a frame.
      if (isTerminalChatEvent(event)) {
        flush()
        return
      }
      if (frameRef.current !== null) return
      frameRef.current = window.requestAnimationFrame(() => {
        frameRef.current = null
        flush()
      })
      // requestAnimationFrame can be paused indefinitely in a background tab.
      // Keep the queue bounded in wall-clock time without abandoning frame
      // batching in the normal foreground path.
      timeoutRef.current = window.setTimeout(() => {
        if (frameRef.current !== null) {
          window.cancelAnimationFrame(frameRef.current)
          frameRef.current = null
        }
        timeoutRef.current = null
        flush()
      }, SSE_BATCH_FALLBACK_MS)
    },
    [flush]
  )

  const discard = useCallback(() => {
    cancelScheduledFlush()
    pendingRef.current = []
  }, [cancelScheduledFlush])

  useEffect(() => discard, [discard])
  return { enqueue, flush, discard }
}

/** Team identity is server-catalog metadata, never an id naming convention. */
export const isTeamCatalogItem = (item: { id?: string; kind?: string; category?: string } | undefined) =>
  item?.kind === 'team' || item?.category === 'team'

export function useChat() {
  const { t } = useTranslation('chat')
  const queryClient = useQueryClient()
  const router = useRouter()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const sessionId = new URLSearchParams(searchStr).get('session')
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  /** Highest fully-dispatched SSE ``event_index`` seen in this tab. */
  const lastEventIndexRef = useRef<{
    current: number | null
    flushPendingEvents?: () => void
  }>({ current: null })
  const advanceFlushedEventIndex = useCallback((eventIndex: number) => {
    const previous = lastEventIndexRef.current.current
    if (previous === null || eventIndex > previous) lastEventIndexRef.current.current = eventIndex
  }, [])
  const {
    enqueue: enqueueChatEvent,
    flush: flushChatEvents,
    discard: discardChatEvents,
  } = useRafChatEventQueue(dispatch, advanceFlushedEventIndex)
  // API parsing may encounter non-visual frames after visual frames have been
  // queued for the next animation frame. It must flush that queue before it
  // advances the shared resume cursor past the ignored frame.
  lastEventIndexRef.current.flushPendingEvents = flushChatEvents
  const [attachments, setAttachments] = useState<File[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const activeRunIdRef = useRef<string | null>(null)
  /** When true, AbortError means leave/unmount — do not mark cancelled or cancel server. */
  const detachOnlyRef = useRef(false)
  /** Files from the last submitted user turn (for regenerate while still in session). */
  const lastTurnFilesRef = useRef<File[]>([])
  // Track URL session for abort-on-change (sidebar navigates URL; this hook owns the SSE).
  const prevSessionIdRef = useRef<string | null>(sessionId)
  // Active (non-archived) list only — shares RQ cache with ChatTaskPanel recents.
  const sessionsQueryResult = useQuery(sessionsQuery({}))
  const sessionItems = sessionsQueryResult.data?.data ?? EMPTY_SESSIONS
  const sessions = {
    ...sessionsQueryResult,
    data: sessionItems,
  }
  const listSessionMeta = useMemo(
    () => (sessionId ? sessionItems.find((item) => item.session_id === sessionId) : undefined),
    [sessionId, sessionItems]
  )
  // Deep links / older sessions may sit outside the loaded recents window.
  const sessionMetaResult = useQuery(sessionMetaQuery(sessionId ?? '', Boolean(sessionId) && !listSessionMeta))
  const activeSessionMeta = listSessionMeta ?? sessionMetaResult.data ?? undefined
  const isWorkflowSession = String(activeSessionMeta?.session_type || '').toLowerCase() === 'workflow'
  // Wait for meta when missing from list so we do not load agent history for a workflow session.
  const metaResolved = !sessionId || Boolean(listSessionMeta) || sessionMetaResult.isFetched
  // Network/5xx on meta: do not treat as missing (404) or load history as agent blindly.
  const sessionMetaFailed = Boolean(sessionId) && !listSessionMeta && Boolean(sessionMetaResult.isError)
  // 404 meta → null data with success; treat as missing for empty-state UX.
  const sessionMissing =
    Boolean(sessionId) && metaResolved && !listSessionMeta && sessionMetaResult.isSuccess && sessionMetaResult.data == null
  const historyQueryResult = useInfiniteQuery(
    historyQuery(sessionId ?? '', Boolean(sessionId) && metaResolved && !sessionMetaFailed && !isWorkflowSession && !sessionMissing)
  )
  // React Query's infinite-page fetch commits a snapshot captured at request
  // start. Serialize it with newest-page reconciliation so a late older-page
  // response cannot overwrite a freshly shifted page boundary.
  const historyOperationQueueRef = useRef<SerialAsyncQueue | null>(null)
  if (historyOperationQueueRef.current === null) {
    historyOperationQueueRef.current = new SerialAsyncQueue()
  }
  const historyOperationCountRef = useRef(0)
  const [historyOperationPending, setHistoryOperationPending] = useState(false)
  const [olderHistoryPageVersion, setOlderHistoryPageVersion] = useState(0)
  const enqueueHistoryOperation = useCallback(<T>(operation: () => Promise<T>): Promise<T> => {
    historyOperationCountRef.current += 1
    setHistoryOperationPending(true)
    const run = async () => {
      try {
        return await operation()
      } finally {
        historyOperationCountRef.current -= 1
        if (historyOperationCountRef.current === 0) setHistoryOperationPending(false)
      }
    }
    const result = historyOperationQueueRef.current?.enqueue(run)
    if (!result) throw new Error('history operation queue is unavailable')
    return result
  }, [])
  const fetchOlderHistory = useCallback(async () => {
    const result = await enqueueHistoryOperation(() => historyQueryResult.fetchNextPage())
    if (!result.isFetchNextPageError) {
      setOlderHistoryPageVersion((version) => version + 1)
    }
    return result
  }, [enqueueHistoryOperation, historyQueryResult])
  const pagedHistoryMessages = useMemo(() => {
    return flattenHistoryPages(historyQueryResult.data?.pages)
  }, [historyQueryResult.data?.pages])
  // Infinite pages arrive newest → older; expose one chronological transcript
  // to the reducer and existing ChatPage consumers.
  const history = {
    ...historyQueryResult,
    data: pagedHistoryMessages,
    fetchNextPage: fetchOlderHistory,
    isOperationPending: historyOperationPending,
    olderPageVersion: olderHistoryPageVersion,
  }
  const historyMessagesRef = useRef<Message[]>([])
  // The live attach callback can run immediately after a paginated render;
  // synchronize before passive effects so it never revives an old one-page
  // snapshot over newly prepended history.
  useLayoutEffect(() => {
    historyMessagesRef.current = history.data ?? []
  }, [history.data])
  const refreshLatestHistory = useCallback(
    (targetSessionId: string) => {
      void enqueueHistoryOperation(() => refreshLatestHistoryPage(queryClient, targetSessionId)).catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return
        const detail = error instanceof Error ? error.message : String(error)
        console.warn(`[chat] newest history refresh failed for ${targetSessionId}: ${detail}`)
      })
    },
    [enqueueHistoryOperation, queryClient]
  )
  const models = useQuery(modelsQuery())
  const agents = useQuery(agentsQuery())
  const activeSessionType = String(activeSessionMeta?.session_type || '').toLowerCase()
  const activeSessionTeamId = String(activeSessionMeta?.team_id || '').trim()
  const isTeamSession = activeSessionType === 'team' && Boolean(activeSessionTeamId)
  // A Team session must never silently continue through a fallback Agent after
  // its feature flag/catalog entry disappears. Wait for the catalog, then
  // fail closed and let the user start a new ordinary chat instead.
  const teamCatalogSettled = Boolean(agents.isFetched || agents.isError)
  const teamSessionChecking = Boolean(isTeamSession && !teamCatalogSettled)
  const teamSessionUnavailable = Boolean(
    isTeamSession && teamCatalogSettled && !(agents.data ?? []).some((row) => row.id === activeSessionTeamId && isTeamCatalogItem(row))
  )

  // URL session changed (sidebar, deep link, browser history): abort live SSE
  // so history can load and the server run is cancelled best-effort.
  useEffect(() => {
    const prev = prevSessionIdRef.current
    prevSessionIdRef.current = sessionId
    if (prev === sessionId) return
    discardChatEvents()
    const { runId } = abortActiveChatStream()
    abortRef.current = null
    // Keep activeRunIdRef for submit's AbortError → run.cancelled payload; submit finally clears it.
    bestEffortCancelRun(runId)
    // null → new session is first-message submit (keep streaming UI). A→B or A→null needs clear.
    if (prev != null) {
      dispatch({ type: 'session-switch' })
      lastTurnFilesRef.current = []
      lastEventIndexRef.current.current = null
      setAttachments([])
    }
  }, [discardChatEvents, sessionId])

  // Leaving Chat detaches the SSE consumer only. The server run continues so the
  // user can return and load completed history. Explicit Stop / session switch still cancel.
  useEffect(() => {
    return () => {
      const local = abortRef.current
      if (!local) return
      detachOnlyRef.current = true
      discardChatEvents()
      clearChatStream(local)
      try {
        local.abort()
      } catch {
        // ignore
      }
      abortRef.current = null
      // Do not call cancelRun — backend finishes and persists the turn.
    }
  }, [discardChatEvents])

  useEffect(() => {
    if (!sessionId || !history.data) return
    // Avoid replacing an in-flight stream with a concurrent history fetch.
    if (state.requesting) return
    dispatch({ type: 'history', messages: history.data })
  }, [history.data, sessionId, state.requesting])

  // After leave-page: re-attach to the detached server stream so the user sees
  // catch-up + live tokens (history alone only updates when Agno persists COMPLETED).
  useEffect(() => {
    if (!sessionId) return
    if (isWorkflowSession || sessionMissing || sessionMetaFailed) return
    if (!history.isFetched) return
    // Own submit already holds the SSE; do not double-attach.
    if (state.requesting && abortRef.current) return

    let cancelled = false
    const controller = new AbortController()
    const attachSession = sessionId
    let assistantId: string = createClientId()
    let attachedUi = false

    const ensureAssistant = (runId?: string) => {
      if (runId) assistantId = runId
      if (attachedUi) return
      attachedUi = true
      const prior = historyMessagesRef.current.filter((message) => !(message.role === 'assistant' && message.id === assistantId))
      // Drop trailing incomplete assistant bubbles from a failed prior attach.
      const cleaned = [...prior]
      while (cleaned.length && cleaned[cleaned.length - 1]?.role === 'assistant' && !cleaned[cleaned.length - 1]?.final) {
        cleaned.pop()
      }
      dispatch({ type: 'attach-live', messages: cleaned, assistantId })
    }

    const run = async () => {
      detachOnlyRef.current = false
      abortRef.current = controller
      registerChatStream(controller, attachSession)
      try {
        await attachLiveSessionStream(
          attachSession,
          (event, eventIndex) => {
            if (cancelled || prevSessionIdRef.current !== attachSession) return
            const eventRunId = 'runId' in event ? event.runId : undefined
            if (typeof eventRunId === 'string' && eventRunId) {
              activeRunIdRef.current = eventRunId
              updateChatStreamRunId(eventRunId)
              ensureAssistant(eventRunId)
            } else {
              ensureAssistant()
            }
            enqueueChatEvent(assistantId, event, eventIndex)
          },
          controller.signal,
          {
            lastEventIndex: lastEventIndexRef.current.current,
            eventIndexCursor: lastEventIndexRef.current,
          }
        )
      } catch (error) {
        if (cancelled || (error as Error).name === 'AbortError') {
          if (detachOnlyRef.current) detachOnlyRef.current = false
          return
        }
        console.warn(`[chat] live attach failed for ${attachSession}: ${error instanceof Error ? error.message : String(error)}`)
        flushChatEvents()
        refreshLatestHistory(attachSession)
      } finally {
        if (!cancelled) {
          flushChatEvents()
          clearChatStream(controller)
          if (abortRef.current === controller) abortRef.current = null
          activeRunIdRef.current = null
          lastEventIndexRef.current.current = null
          refreshLatestHistory(attachSession)
          void queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
        }
      }
    }

    void run()
    return () => {
      cancelled = true
      detachOnlyRef.current = true
      discardChatEvents()
      clearChatStream(controller)
      try {
        controller.abort()
      } catch {
        // ignore
      }
      if (abortRef.current === controller) abortRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- attach once per session visit
  }, [sessionId, history.isFetched, isWorkflowSession, sessionMissing, sessionMetaFailed, refreshLatestHistory])

  // Drop stale agent ids (e.g. Team beta off but localStorage still has team id).
  useEffect(() => {
    const rows = agents.data
    if (!rows?.length) return
    if (teamSessionChecking || teamSessionUnavailable) return
    if (rows.some((row) => row.id === state.selectedAgentId)) return
    const fallback = rows[0]?.id || 'security-operations'
    try {
      localStorage.setItem('agno-aios-chat-agent-id', fallback)
    } catch {
      // ignore
    }
    dispatch({ type: 'agent', value: fallback })
  }, [agents.data, state.selectedAgentId, teamSessionChecking, teamSessionUnavailable])

  // Restore agent/team selector when opening an existing session (team_id wins for team sessions).
  useEffect(() => {
    if (!sessionId || !activeSessionMeta) return
    if (state.requesting) return
    const sessionType = String(activeSessionMeta.session_type || '').toLowerCase()
    if (sessionType === 'workflow') return
    const teamId = String(activeSessionMeta.team_id || '').trim()
    const agentId = String(activeSessionMeta.agent_id || '').trim()
    const preferred = sessionType === 'team' ? teamId || agentId : agentId || teamId
    if (!preferred || preferred === state.selectedAgentId) return
    const known = (agents.data ?? []).some((row) => row.id === preferred)
    // When Team beta is off, team ids won't be in catalog — keep local preference.
    if (!known) return
    try {
      localStorage.setItem('agno-aios-chat-agent-id', preferred)
    } catch {
      // ignore
    }
    dispatch({ type: 'agent', value: preferred })
  }, [activeSessionMeta, agents.data, sessionId, state.requesting, state.selectedAgentId])

  // Workflow sessions are not agent transcripts — open Studio when known, else Trace.
  useEffect(() => {
    if (!sessionId || !isWorkflowSession) return
    const workflowId = String(activeSessionMeta?.workflow_id || '').trim()
    if (workflowId) {
      void router.history.replace(`/workflow?workflow_id=${encodeURIComponent(workflowId)}`)
      return
    }
    const filters = { ...emptyTraceFilters(), session_id: sessionId }
    const search = buildTraceSearch(filters, sessionId, '')
    void router.history.replace(`/trace${search ? `?${search}` : ''}`)
  }, [activeSessionMeta?.workflow_id, isWorkflowSession, router.history, sessionId])
  const hasPausedRun = state.messages.some((message) => message.role === 'assistant' && message.status === 'paused')
  useEffect(() => {
    if (!sessionId || !hasPausedRun || isWorkflowSession) return
    const refreshHistory = () => refreshLatestHistory(sessionId)
    const interval = window.setInterval(refreshHistory, 2_000)
    return () => window.clearInterval(interval)
  }, [hasPausedRun, isWorkflowSession, refreshLatestHistory, sessionId])
  useEffect(() => {
    if (!models.data?.models.length) return
    const runnable = models.data.models.filter((model) => model.enabled && model.configured)
    const selected =
      runnable.find((model) => model.id === state.selectedModelId) ??
      runnable.find((model) => model.id === models.data.active_model_id) ??
      runnable[0]
    if (!selected) return
    const effort = defaultReasoningEffort(selected)
    if (state.selectedModelId !== selected.id) dispatch({ type: 'model', value: selected.id, reasoningEffort: effort })
    else if (state.reasoningEffort === null && effort !== null) dispatch({ type: 'reasoning-effort', value: effort })
  }, [models.data, state.reasoningEffort, state.selectedModelId])

  const selectedModel = useMemo(
    () => models.data?.models.find((model) => model.id === state.selectedModelId) ?? null,
    [models.data, state.selectedModelId]
  )
  const setSession = (value: string | null) => {
    const next = value
    const same = (next == null && !sessionId) || (next != null && next === sessionId)
    // Switching sessions mid-stream aborts the live SSE (sidebar may change URL first).
    if (!same) {
      const { runId } = abortActiveChatStream()
      abortRef.current = null
      // Keep activeRunIdRef for submit's AbortError → run.cancelled payload; submit finally clears it.
      bestEffortCancelRun(runId)
    }
    if (same) return
    void router.history.push(next ? `/chat?session=${encodeURIComponent(next)}` : '/chat')
  }
  const setModel = (value: string) => {
    localStorage.setItem('agno-aios-chat-model-id', value)
    const model = models.data?.models.find((item) => item.id === value) ?? null
    dispatch({ type: 'model', value, reasoningEffort: defaultReasoningEffort(model) })
  }

  const submit = async (prompt: string, appendUser = true, filesOverride?: File[]) => {
    const text = prompt.trim()
    const pendingFiles = (filesOverride ?? attachments).slice()
    const hasPendingApproval = state.messages.some((message) => message.role === 'assistant' && message.status === 'paused')
    if (
      (!text && pendingFiles.length === 0) ||
      state.requesting ||
      hasPendingApproval ||
      !selectedModel?.enabled ||
      !selectedModel.configured
    )
      return
    const limitError = validateChatAttachments(pendingFiles)
    if (limitError) {
      dispatch({ type: 'soft-error', message: formatAttachmentLimitError(limitError, t) })
      return
    }
    // Existing deep-link session: wait for meta (and never send on workflow sessions).
    if (sessionId && (!metaResolved || sessionMetaFailed || isWorkflowSession || teamSessionChecking || teamSessionUnavailable)) return
    const activeSession = sessionId ?? createClientId()
    if (!sessionId) {
      prevSessionIdRef.current = activeSession
      setSession(activeSession)
      const now = Date.now() / 1_000
      const agentId = state.selectedAgentId || 'security-operations'
      const catalogRow = (agents.data ?? []).find((row) => row.id === agentId)
      const looksTeam = isTeamCatalogItem(catalogRow)
      const optimisticSession: ChatSession = {
        session_id: activeSession,
        preview: text || (pendingFiles.length ? pendingFiles.map((f) => f.name).join(', ') : '新对话'),
        created_at: now,
        updated_at: now,
        archived: false,
        session_type: looksTeam ? 'team' : 'agent',
        agent_id: looksTeam ? null : agentId,
        team_id: looksTeam ? agentId : null,
      }
      markSessionActiveInCaches(queryClient, optimisticSession)
    } else if (activeSessionMeta?.archived) {
      // Continuing a thread should bring it back to recents.
      markSessionActiveInCaches(queryClient, {
        ...activeSessionMeta,
        preview: text || activeSessionMeta.preview,
        updated_at: Date.now() / 1_000,
      })
      void unarchiveSession(activeSession).catch((error: unknown) => {
        const detail = error instanceof Error ? error.message : String(error)
        console.warn(`[chat] auto-unarchive failed for ${activeSession}: ${detail}`)
        // Keep optimistic active caches; list invalidate will reconcile.
        void queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
      })
    }
    const assistantId = createClientId()
    const user: Message = {
      id: createClientId(),
      role: 'user',
      content: text,
      final: true,
      session_id: activeSession,
      attachments: pendingFiles.map((file) => ({
        name: file.name,
        mime: file.type || undefined,
        kind: file.type.startsWith('image/')
          ? 'image'
          : file.type.startsWith('audio/')
            ? 'audio'
            : file.type.startsWith('video/')
              ? 'video'
              : 'document',
      })),
    }
    lastTurnFilesRef.current = pendingFiles
    setAttachments([])
    const assistant: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      final: false,
      status: 'streaming',
      session_id: activeSession,
      tool_steps: [],
      sources: [],
      followups: [],
    }
    dispatch({ type: 'start', user: appendUser ? user : undefined, assistant, modelId: selectedModel.id })
    const controller = new AbortController()
    abortRef.current = controller
    activeRunIdRef.current = null
    lastEventIndexRef.current.current = null
    detachOnlyRef.current = false
    registerChatStream(controller, activeSession)
    try {
      await streamMessage(
        {
          message: text,
          session_id: activeSession,
          model_id: selectedModel.id,
          agent_id: state.selectedAgentId,
          ...(state.reasoningEffort ? { reasoning_effort: state.reasoningEffort } : {}),
          // Tools-off / lean path ignores these server-side; send false for clarity.
          search_knowledge: state.enableTools ? state.searchKnowledge : false,
          live_search: state.enableTools ? state.liveSearch : false,
          enable_tools: state.enableTools,
          ...(pendingFiles.length ? { files: pendingFiles } : {}),
        },
        (event: ChatRunEvent, eventIndex?: number) => {
          // Drop late chunks if the user switched sessions mid-stream.
          if (prevSessionIdRef.current !== activeSession) return
          // Keep cancel targets current across retries / late run_id attachment.
          const eventRunId = 'runId' in event ? event.runId : undefined
          if (typeof eventRunId === 'string' && eventRunId) {
            activeRunIdRef.current = eventRunId
            updateChatStreamRunId(eventRunId)
          }
          enqueueChatEvent(assistantId, event, eventIndex)
        },
        controller.signal,
        lastEventIndexRef.current
      )
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        // Leave/unmount: drop the client stream; server keeps running.
        // Keep lastEventIndexRef so re-attach can skip already-rendered events.
        if (detachOnlyRef.current) {
          detachOnlyRef.current = false
        } else if (prevSessionIdRef.current === activeSession) {
          // Explicit stop or session switch on the same view.
          lastEventIndexRef.current.current = null
          dispatch({ type: 'clear-error' })
          enqueueChatEvent(assistantId, {
            type: 'run.cancelled',
            runId: activeRunIdRef.current ?? undefined,
            reason: t('stoppedGenerating'),
          })
        }
      } else if (prevSessionIdRef.current === activeSession) {
        lastEventIndexRef.current.current = null
        flushChatEvents()
        dispatch({
          type: 'network-error',
          id: assistantId,
          message: error instanceof Error ? error.message : t('errorRequestFailed'),
        })
      }
    } finally {
      flushChatEvents()
      clearChatStream(controller)
      abortRef.current = null
      activeRunIdRef.current = null
      // Natural terminal: clear resume cursor. Leave-page abort keeps the cursor.
      if (!controller.signal.aborted) {
        lastEventIndexRef.current.current = null
      }
      // Refresh after success, cancel, or failure (partial/cancelled runs may be stored).
      refreshLatestHistory(activeSession)
      void queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
    }
  }

  const retry = (assistantId: string) => {
    if (state.requesting) return
    const prompt = previousPrompt(state.messages, assistantId)
    const index = state.messages.findIndex((message) => message.id === assistantId)
    if (index < 0) return
    // Allow attachment-only turns: empty text is OK when last-turn files remain in memory.
    const retryFiles = lastTurnFilesRef.current
    if (!prompt && retryFiles.length === 0) return
    // Supersede any leave-page detached run for this turn so regenerate is the only writer.
    const previous = state.messages[index]
    const previousRunId =
      (previous?.run_id && String(previous.run_id)) || (previous?.id && previous.role === 'assistant' ? String(previous.id) : null)
    if (previousRunId && !previousRunId.includes(':')) {
      bestEffortCancelRun(previousRunId)
    }
    const base = state.messages.slice(0, index)
    dispatch({ type: 'history', messages: base })
    void submit(prompt, false, retryFiles)
  }
  const cancel = useCallback(async () => {
    // Prefer process-wide stream (this instance or the sibling useChat owner).
    const global = abortActiveChatStream()
    // Local backup if registry was already cleared mid-flight.
    abortRef.current?.abort()
    abortRef.current = null
    const runId = global.runId ?? activeRunIdRef.current
    // Leave activeRunIdRef for submit's AbortError path; submit finally clears it.
    if (!runId) return
    try {
      await cancelRun(runId)
    } catch (error) {
      // Best-effort server cancel; client stream is already aborted.
      // 404 = run already finished or never registered (race with terminal event).
      if (error instanceof ApiError && error.status === 404) return
      const detail = error instanceof Error ? error.message : String(error)
      console.warn(`[chat] server cancel failed for run ${runId}: ${detail}`)
      dispatch({ type: 'soft-error', message: t('cancelServerFailed') })
    }
  }, [t])
  const setReasoningEffort = (value: ReasoningEffort | null) => dispatch({ type: 'reasoning-effort', value })
  const setSearchKnowledge = (value: boolean) => {
    try {
      localStorage.setItem('agno-aios-chat-search-knowledge', String(value))
    } catch {
      // ignore
    }
    dispatch({ type: 'search-knowledge', value })
  }
  const setEnableTools = (value: boolean) => {
    try {
      localStorage.setItem('agno-aios-chat-enable-tools', String(value))
      if (!value) {
        localStorage.setItem('agno-aios-chat-live-search', 'false')
      }
    } catch {
      // ignore
    }
    dispatch({ type: 'enable-tools', value })
  }
  const setLiveSearch = (value: boolean) => {
    try {
      localStorage.setItem('agno-aios-chat-live-search', String(value))
    } catch {
      // ignore
    }
    dispatch({ type: 'live-search', value })
  }
  const setSelectedAgent = (value: string) => {
    const next = (value || 'security-operations').trim() || 'security-operations'
    try {
      localStorage.setItem('agno-aios-chat-agent-id', next)
    } catch {
      // ignore
    }
    dispatch({ type: 'agent', value: next })
    // Research / Team profiles prefer Live Search when tools are on and the model supports it.
    const profile = (agents.data ?? []).find((row) => row.id === next)
    const modelSupports = Boolean(
      (models.data?.models ?? []).find((m) => m.id === state.selectedModelId)?.capabilities?.supports_live_search
    )
    if (profile?.prefer_live_search && state.enableTools && modelSupports && !state.liveSearch) {
      try {
        localStorage.setItem('agno-aios-chat-live-search', 'true')
      } catch {
        // ignore
      }
      dispatch({ type: 'live-search', value: true })
    }
  }
  const newChat = () => {
    dispatch({ type: 'reasoning-effort', value: defaultReasoningEffort(selectedModel) })
    // setSession aborts any in-flight run before clearing the URL session.
    setSession(null)
  }
  return {
    state,
    dispatch,
    sessionId,
    sessions,
    activeSessionMeta,
    sessionMetaLoading: Boolean(sessionId) && !listSessionMeta && !sessionMetaResult.isFetched,
    sessionMetaFailed,
    sessionMetaError:
      sessionMetaFailed && sessionMetaResult.error instanceof Error
        ? sessionMetaResult.error
        : sessionMetaFailed
          ? new Error('session meta failed')
          : null,
    sessionMetaRefetch: () => void sessionMetaResult.refetch(),
    sessionMissing,
    teamSessionChecking,
    teamSessionUnavailable,
    attachments,
    setAttachments,
    history,
    models,
    agents,
    selectedModel,
    selectedAgentId: state.selectedAgentId,
    setSelectedAgent,
    setSession,
    setModel,
    setReasoningEffort,
    setSearchKnowledge,
    setEnableTools,
    setLiveSearch,
    submit,
    retry,
    newChat,
    cancel,
  }
}
