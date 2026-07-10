import { describe, expect, it } from 'vitest'
import { filterSessionsByArchive, firstSpanId, groupRuns, groupSessions, previewSpanValue } from './utils'
import type { Trace } from './types'

const traces: Trace[] = [
  { trace_id: 't1', session_id: 's1', run_id: 'r1', name: 'run', status: 'OK', duration_ms: 20, start_time: '2026-01-01T00:00:00Z', end_time: '', total_spans: 3 },
  { trace_id: 't2', session_id: 's1', run_id: 'r1', name: 'model', status: 'ERROR', duration_ms: 8, start_time: '2026-01-01T00:00:01Z', end_time: '', total_spans: 1 },
  { trace_id: 't3', session_id: 's2', run_id: 'r2', name: 'run', status: 'OK', duration_ms: 10, start_time: '2026-01-02T00:00:00Z', end_time: '' },
]

describe('trace hierarchy', () => {
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

  it('groups traces into runs and preserves failure status', () => {
    expect(groupRuns(traces, 's1')[0]).toMatchObject({ runId: 'r1', traceId: 't1', status: 'ERROR', durationMs: 20 })
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
