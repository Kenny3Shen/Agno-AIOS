import { describe, expect, it } from 'vitest'
import { buildWorkflowCode, moveStep, toDefinition } from './utils'
import type { WorkflowState } from './types'

const state: WorkflowState = {
  workflowId: 'wf-1',
  name: 'IR',
  description: 'response',
  input: 'alert',
  sessionId: 's1',
  modelId: 'model-1',
  selectedId: null,
  dirty: false,
  saving: false,
  running: false,
  runLog: [],
  error: null,
  lastRunId: null,
  lastSessionId: null,
  steps: [
    { id: 'a', type: 'step', kind: 'agent', targetId: 'security-operations', name: 'Triage', instructions: 'inspect' },
    { id: 'b', type: 'step', kind: 'agent', targetId: 'safe-fallback', name: 'Report', instructions: 'summarize' },
  ],
}

describe('workflow behavior', () => {
  it('reorders steps without mutating the source', () => {
    const moved = moveStep(state.steps, 'a', 1)
    expect(moved.map((item) => item.id)).toEqual(['b', 'a'])
    expect(state.steps.map((item) => item.id)).toEqual(['a', 'b'])
  })

  it('builds a linear definition for save/run', () => {
    expect(toDefinition(state)).toMatchObject({
      name: 'IR',
      steps: [
        { id: 'a', executor: { kind: 'agent', ref: 'security-operations' } },
        { id: 'b', executor: { kind: 'agent', ref: 'safe-fallback' } },
      ],
    })
  })

  it('preserves execution settings in exported code', () => {
    const code = buildWorkflowCode(state)
    expect(code).toContain('Step(name=')
    expect(code).toContain('session_id="s1"')
    expect(code).toContain('stream_events=True')
  })
})
