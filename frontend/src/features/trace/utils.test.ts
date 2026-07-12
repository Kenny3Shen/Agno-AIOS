import { describe, expect, it } from 'vitest'
import { buildTraceSearch, filterSessionsByArchive, firstSpanId, groupRuns, groupSessions, mergeTraceSessions, parseTraceSearch, previewSpanValue } from './utils'
import type { Trace, TraceSessionSummary } from './types'

const traces: Trace[] = [
  { trace_id: 't1', session_id: 's1', run_id: 'r1', name: 'run', status: 'OK', duration_ms: 20, start_time: '2026-01-01T00:00:00Z', end_time: '', total_spans: 3 },
  { trace_id: 't2', session_id: 's1', run_id: 'r1', name: 'model', status: 'ERROR', duration_ms: 8, start_time: '2026-01-01T00:00:01Z', end_time: '', total_spans: 1 },
  { trace_id: 't3', session_id: 's2', run_id: 'r2', name: 'run', status: 'OK', duration_ms: 10, start_time: '2026-01-02T00:00:00Z', end_time: '' },
]

describe('trace hierarchy', () => {
  it('keeps filter and selected session URL state separate', () => {
    const state = parseTraceSearch('?session_id=filter-session&selected_session=selected-session&trace=trace-1')

    expect(state.filters.session_id).toBe('filter-session')
    expect(state.selectedSession).toBe('selected-session')
    expect(state.traceId).toBe('trace-1')
  })

  it('parses legacy session and run URL params as filters', () => {
    const state = parseTraceSearch('?session=legacy-session&run=legacy-run')

    expect(state.filters).toMatchObject({ session_id: 'legacy-session', run_id: 'legacy-run' })
    expect(state.selectedSession).toBe('legacy-session')
  })

  it('builds selected session URLs without writing it as a filter', () => {
    const query = new URLSearchParams(buildTraceSearch({
      session_id: '',
      run_id: '',
      user_id: '',
      status: '',
      start_time: '',
      end_time: '',
    }, 'selected-session'))

    expect(query.get('selected_session')).toBe('selected-session')
    expect(query.has('session_id')).toBe(false)
  })

  it('orders sessions by their latest trace', () => {
    expect(groupSessions(traces).map((session) => session.sessionId)).toEqual(['s2', 's1'])
  })

  it('uses the latest trace name as session text', () => {
    expect(groupSessions(traces)[0]).toMatchObject({ sessionId: 's2', name: 'run' })
  })

  it('prefers the chat preview when it is available', () => {
    expect(groupSessions(traces, { s2: 'Investigate the alert' })[0].name).toBe('Investigate the alert')
  })

  it('filters archived sessions without hiding them by default', () => {
    const sessions = groupSessions(traces, {}, { s1: true })
    expect(filterSessionsByArchive(sessions, 'all')).toHaveLength(2)
    expect(filterSessionsByArchive(sessions, 'active').map((session) => session.sessionId)).toEqual(['s2'])
    expect(filterSessionsByArchive(sessions, 'archived').map((session) => session.sessionId)).toEqual(['s1'])
  })

  it('treats trace-only sessions as legacy archived sessions after session data loads', () => {
    const sessions = groupSessions(traces, { s2: 'Active session' }, { s2: false }, true)
    expect(sessions.find((session) => session.sessionId === 's1')?.archived).toBe(true)
    expect(sessions.find((session) => session.sessionId === 's2')?.archived).toBe(false)
  })

  it('keeps only trace sessions while enriching them with matching chat metadata', () => {
    const chatSessions = [
      { session_id: 'chat-only', preview: 'No trace yet', created_at: 1, updated_at: 2 },
      { session_id: 's1', preview: 'Chat title', title: 'Renamed session', archived: false, created_at: 1, updated_at: 3 },
    ]
    const summaries: TraceSessionSummary[] = [{
      session_id: 's1', name: 'run', latest_start_time: '2026-01-01T00:00:00Z', trace_count: 2, run_count: 1, error_count: 0, status: 'OK', user_id: 'u1',
    }, {
      session_id: 'legacy', name: 'legacy run', latest_start_time: '2026-01-02T00:00:00Z', trace_count: 1, run_count: 1, error_count: 0, status: 'OK', user_id: 'u1',
    }]
    const merged = mergeTraceSessions(chatSessions, summaries)
    expect(merged.map((session) => session.sessionId)).toEqual(['legacy', 's1'])
    expect(merged.find((session) => session.sessionId === 's1')).toMatchObject({ name: 'Renamed session', archived: false })
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
    expect(groupSessions([fallback])[0].runCount).toBe(1)
    expect(groupRuns([fallback], 'legacy')[0]).toMatchObject({ runId: 'fallback-trace', traceId: 'fallback-trace' })
  })

  it('previews span content and selects the first tree node', () => {
    expect(previewSpanValue({ prompt: 'inspect target' })).toBe('JSON · 1 fields')
    expect(previewSpanValue({ format: 'text', text: 'Inspect the target', data: null })).toBe('Inspect the target')
    expect(firstSpanId([{ span: { span_id: 'root', name: 'agent', status_code: 'OK', duration_ms: 1, start_time: '' }, children: [] }])).toBe('root')
  })
})
