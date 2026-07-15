import { describe, expect, it } from 'vitest'
import {
  buildWorkflowCode,
  createNode,
  fromRecord,
  layoutCanvas,
  moveNodeAfter,
  moveStep,
  reorderRootsByPositions,
  toDefinition,
  defaultTriggers,
} from './utils'
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
  triggers: defaultTriggers(),
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

  it('builds router definition', () => {
    const router = createNode('router')
    const definition = toDefinition({
      name: 'r',
      description: '',
      steps: [router],
    })
    expect(definition.steps[0]?.type).toBe('router')
    expect(definition.steps[0]?.choices?.length).toBe(2)
  })

  it('reorders roots by position and connect sequence', () => {
    const positioned = [
      { ...state.steps[0]!, position: { x: 0, y: 100 } },
      { ...state.steps[1]!, position: { x: 0, y: 0 } },
    ]
    expect(reorderRootsByPositions(positioned).map((n) => n.id)).toEqual(['b', 'a'])
    expect(moveNodeAfter(state.steps, 'a', 'b').map((n) => n.id)).toEqual(['b', 'a'])
  })

  it('layouts nested nodes for the canvas', () => {
    const layout = layoutCanvas([
      {
        id: 'root',
        type: 'condition',
        name: 'C',
        evaluatorCel: 'true',
        thenSteps: [{ id: 't1', type: 'step', name: 'T', targetId: 'security-operations' }],
        elseSteps: [{ id: 'e1', type: 'step', name: 'E', targetId: 'safe-fallback' }],
      },
    ])
    expect(layout.nodes.map((n) => n.id)).toEqual(['root', 't1', 'e1'])
    expect(layout.edges.some((e) => e.label === 'then')).toBe(true)
  })

  it('round-trips nested definition via fromRecord', () => {
    const parallel = createNode('parallel')
    parallel.id = 'fanout'
    parallel.steps = [
      { id: 'c1', type: 'step', targetId: 'security-operations', name: 'A' },
      { id: 'c2', type: 'step', targetId: 'safe-fallback', name: 'B' },
    ]
    const definition = toDefinition({
      name: 'n',
      description: '',
      steps: [parallel],
    })
    const restored = fromRecord({
      id: 'wf',
      name: 'n',
      description: '',
      owner_user_id: 'u',
      definition,
      enabled: true,
      version: 1,
      created_at: 1,
      updated_at: 1,
    })
    expect(restored.steps?.[0]?.type).toBe('parallel')
    expect(restored.steps?.[0]?.steps).toHaveLength(2)
  })

  it('preserves execution settings in exported code', () => {
    const code = buildWorkflowCode(state)
    expect(code).toContain('Step(name=')
    expect(code).toContain('Router')
  })
})
