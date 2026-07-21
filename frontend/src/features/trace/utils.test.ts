import { describe, expect, it } from 'vitest'
import {
  buildTraceSearch,
  filterSessionsByArchive,
  groupRuns,
  mergeTraceSessions,
  parseTraceSearch,
  previewSpanValue,
} from './utils'
import type { Trace, TraceSessionSummary } from './types'

const traces: Trace[] = [
  {
    trace_id: 't1',
    session_id: 's1',
    run_id: 'r1',
    name: 'run',
    status: 'OK',
    duration: '20ms',
    start_time: '2026-01-01T00:00:00Z',
    end_time: '',
    total_spans: 3,
  },
  {
    trace_id: 't2',
    session_id: 's1',
    run_id: 'r1',
    name: 'model',
    status: 'ERROR',
    duration: '8ms',
    start_time: '2026-01-01T00:00:01Z',
    end_time: '',
    total_spans: 1,
  },
  {
    trace_id: 't3',
    session_id: 's2',
    run_id: 'r2',
    name: 'run',
    status: 'OK',
    duration: '10ms',
    start_time: '2026-01-02T00:00:00Z',
    end_time: '',
  },
]

describe('trace hierarchy', () => {
  it('keeps filter and selected session URL state separate', () => {
    const state = parseTraceSearch('?session_id=filter-session&selected_session=selected-session&trace=trace-1')

    expect(state.filters.session_id).toBe('filter-session')
    expect(state.selectedSession).toBe('selected-session')
    expect(state.traceId).toBe('trace-1')
  })

  it('parses canonical session_id and run_id URL params', () => {
    const state = parseTraceSearch('?session_id=filter-session&run_id=filter-run')
    expect(state.filters).toMatchObject({ session_id: 'filter-session', run_id: 'filter-run' })
  })

  it('builds selected session URLs without writing it as a filter', () => {
    const query = new URLSearchParams(
      buildTraceSearch(
        {
          session_id: '',
          run_id: '',
          user_id: '',
          status: '',
          start_time: '',
          end_time: '',
        },
        'selected-session'
      )
    )

    expect(query.get('selected_session')).toBe('selected-session')
    expect(query.has('session_id')).toBe(false)
  })

  it('filters archived sessions without hiding them by default', () => {
    const sessions = [
      { sessionId: 's2', name: 'Run', context: '', archived: false, traces: [], runCount: 1, latestAt: '' },
      { sessionId: 's1', name: 'Run', context: '', archived: true, traces: [], runCount: 1, latestAt: '' },
    ]
    expect(filterSessionsByArchive(sessions, 'all')).toHaveLength(2)
    expect(filterSessionsByArchive(sessions, 'active').map((session) => session.sessionId)).toEqual(['s2'])
    expect(filterSessionsByArchive(sessions, 'archived').map((session) => session.sessionId)).toEqual(['s1'])
  })

  it('keeps only trace sessions while enriching them with matching chat metadata', () => {
    const chatSessions = [
      { session_id: 'chat-only', preview: 'No trace yet', created_at: 1, updated_at: 2 },
      { session_id: 's1', preview: 'Chat title', title: 'Renamed session', archived: false, created_at: 1, updated_at: 3 },
    ]
    const summaries: TraceSessionSummary[] = [
      {
        session_id: 's1',
        name: '安全运营助手.arun',
        latest_start_time: '2026-01-01T00:00:00Z',
        trace_count: 2,
        run_count: 1,
        error_count: 0,
        status: 'OK',
        user_id: 'u1',
      },
      {
        session_id: 'legacy',
        name: '安全运营助手.arun',
        latest_start_time: '2026-01-02T00:00:00Z',
        trace_count: 1,
        run_count: 1,
        error_count: 0,
        status: 'OK',
        user_id: 'u1',
        agent_id: 'security-operations',
      },
    ]
    const merged = mergeTraceSessions(chatSessions, summaries)
    expect(merged.map((session) => session.sessionId)).toEqual(['legacy', 's1'])
    expect(merged.find((session) => session.sessionId === 's1')).toMatchObject({ name: 'Renamed session', archived: false })
    // Without chat metadata, strip technical .arun and fall back to agent_id.
    expect(merged.find((session) => session.sessionId === 'legacy')?.name).toBe('security-operations')
    expect(merged.find((session) => session.sessionId === 's1')?.runCount).toBe(1)
  })

  it('keeps distinct traces even when they share a run ID', () => {
    const runs = groupRuns(traces, 's1')
    expect(runs).toHaveLength(2)
    expect(runs.map((run) => run.traceId).sort()).toEqual(['t1', 't2'])
    expect(runs.every((run) => run.runId === 'r1')).toBe(true)
  })

  it('keeps Run ID search results when no session is selected', () => {
    expect(groupRuns([traces[2]], '')).toMatchObject([{ runId: 'r2', traceId: 't3' }])
  })

  it('keeps a trace without run ID as a fallback run', () => {
    const fallback = { ...traces[0], trace_id: 'fallback-trace', session_id: 'legacy', run_id: null }
    expect(groupRuns([fallback], 'legacy')[0]).toMatchObject({ runId: 'fallback-trace', traceId: 'fallback-trace' })
  })

  it('previews span content', () => {
    expect(previewSpanValue({ prompt: 'inspect target' })).toBe('JSON · 1 fields')
    expect(previewSpanValue({ format: 'text', text: 'Inspect the target', data: null })).toBe('Inspect the target')
  })
})
