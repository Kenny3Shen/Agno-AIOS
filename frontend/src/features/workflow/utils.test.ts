import { describe, expect, it } from 'vitest'
import { reduceNodeRunStatus } from './runStatus'
import {
  applyAutoLayout,
  buildWorkflowCode,
  createNode,
  fromRecord,
  layoutCanvas,
  moveNodeAfter,
  moveStep,
  reparentNode,
  reorderRootsByPositions,
  toDefinition,
  defaultTriggers,
  emptySlotsFor,
  branchHandlesFor,
  reparentTargetFromHandle,
  validateWorkflowDraft,
  triggerEnableBlocked,
} from './utils'
import type { WorkflowState } from './types'

const state: WorkflowState = {
  workflowId: 'wf-1',
  name: 'IR',
  description: 'response',
  input: 'alert',
  sessionId: 's1',
  modelId: 'model-1',
  version: 1,
  publishedVersion: null,
  publishedAt: null,
  hasPublished: false,
  selectedId: null,
  selectedIds: [],
  dirty: false,
  saving: false,
  running: false,
  runLog: [],
  nodeRunStatus: {},
  runHistory: [],
  error: null,
  validationIssues: [],
  lastApprovalId: null,
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

  it('builds router definition without seeding agent steps', () => {
    const router = createNode('router')
    expect(router.choices?.every((c) => c.steps.length === 0)).toBe(true)
    const definition = toDefinition({
      name: 'r',
      description: '',
      steps: [router],
    })
    expect(definition.steps[0]?.type).toBe('router')
    expect(definition.steps[0]?.choices?.length).toBe(2)
  })

  it('creates control-flow nodes without nested agent steps', () => {
    expect(createNode('parallel').steps).toEqual([])
    expect(createNode('condition').thenSteps).toEqual([])
    expect(createNode('condition').elseSteps).toEqual([])
    expect(createNode('loop').steps).toEqual([])
    expect(createNode('step').type).toBe('step')
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
      version: 3,
      published_version: 2,
      published_at: 1_700_000_000,
      has_published: true,
      created_at: 1,
      updated_at: 1,
    })
    expect(restored.steps?.[0]?.type).toBe('parallel')
    expect(restored.steps?.[0]?.steps).toHaveLength(2)
    expect(restored.version).toBe(3)
    expect(restored.publishedVersion).toBe(2)
    expect(restored.publishedAt).toBe(1_700_000_000)
    expect(restored.hasPublished).toBe(true)
  })

  it('blocks trigger enable when unpublished or dirty', () => {
    expect(triggerEnableBlocked({ hasPublished: false, dirty: false })).toBe('unpublished')
    expect(triggerEnableBlocked({ hasPublished: true, dirty: true })).toBe('dirty')
    expect(triggerEnableBlocked({ hasPublished: true, dirty: false })).toBeNull()
  })

  it('preserves execution settings in exported code', () => {
    const code = buildWorkflowCode(state)
    expect(code).toContain('Step(name=')
    expect(code).toContain('Router')
  })
})

describe('reparent and auto-layout', () => {
  it('reparents a step into parallel', () => {
    const parallel = createNode('parallel')
    parallel.id = 'p1'
    const step = createNode('step')
    step.id = 's1'
    const next = reparentNode([parallel, step], 's1', {
      kind: 'branch',
      parentId: 'p1',
      branch: 'steps',
    })
    expect(next).toHaveLength(1)
    expect(next[0]?.type).toBe('parallel')
    expect(next[0]?.steps?.map((n) => n.id)).toEqual(['s1'])
  })

  it('blocks reparent into own descendant', () => {
    const parallel = createNode('parallel')
    parallel.id = 'p1'
    const step = createNode('step')
    step.id = 's1'
    parallel.steps = [step]
    const next = reparentNode([parallel], 'p1', {
      kind: 'branch',
      parentId: 's1',
      branch: 'steps',
    })
    expect(next[0]?.id).toBe('p1')
    expect(next[0]?.steps?.[0]?.id).toBe('s1')
  })

  it('exposes empty slots for empty containers', () => {
    expect(emptySlotsFor(createNode('parallel')).map((s) => s.key)).toEqual(['steps'])
    expect(emptySlotsFor(createNode('condition')).map((s) => s.key)).toEqual(['thenSteps', 'elseSteps'])
  })

  it('auto-layout assigns positions', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const laid = applyAutoLayout([a, b])
    expect(laid[0]?.position).toBeTruthy()
    expect(laid[1]?.position).toBeTruthy()
    expect(laid[0]?.position?.y).not.toEqual(laid[1]?.position?.y)
  })
})

describe('run status reduce', () => {
  it('marks started/completed/paused nodes', () => {
    const steps = [
      { id: 'a', type: 'step' as const, name: 'Triage', targetId: 'security-operations' },
      { id: 'b', type: 'step' as const, name: 'Report', targetId: 'safe-fallback' },
    ]
    const map = reduceNodeRunStatus(steps, [
      { id: '1', type: 'step.started', message: '', stepId: 'a', at: 1 },
      { id: '2', type: 'step.completed', message: '', stepId: 'a', at: 2 },
      { id: '3', type: 'step.started', message: '', stepId: 'b', at: 3 },
      { id: '4', type: 'workflow.paused', message: '', stepId: 'b', approvalId: 'ap1', at: 4 },
    ])
    expect(map.a).toBe('ok')
    expect(map.b).toBe('paused')
  })
})

describe('multi-handle branches', () => {
  it('exposes then/else handles for condition', () => {
    const handles = branchHandlesFor(createNode('condition'))
    expect(handles.map((h) => h.id)).toEqual(['then', 'else'])
  })

  it('exposes choice handles for router', () => {
    const router = createNode('router')
    const handles = branchHandlesFor(router)
    expect(handles).toHaveLength(2)
    expect(handles.every((h) => h.id.startsWith('choice:'))).toBe(true)
  })

  it('maps handle to reparent target', () => {
    const condition = createNode('condition')
    condition.id = 'c1'
    expect(reparentTargetFromHandle(condition, 'then')).toEqual({
      kind: 'branch',
      parentId: 'c1',
      branch: 'thenSteps',
    })
    const router = createNode('router')
    router.id = 'r1'
    const choiceId = router.choices![0]!.id
    expect(reparentTargetFromHandle(router, `choice:${choiceId}`)).toEqual({
      kind: 'choice',
      parentId: 'r1',
      choiceId,
    })
  })

  it('layouts edges with sourceHandle for branches', () => {
    const condition = createNode('condition')
    condition.id = 'c1'
    condition.thenSteps = [{ id: 't1', type: 'step', name: 'T', targetId: 'security-operations' }]
    condition.elseSteps = [{ id: 'e1', type: 'step', name: 'E', targetId: 'safe-fallback' }]
    const layout = layoutCanvas([condition])
    const thenEdge = layout.edges.find((e) => e.target === 't1')
    const elseEdge = layout.edges.find((e) => e.target === 'e1')
    expect(thenEdge?.sourceHandle).toBe('then')
    expect(elseEdge?.sourceHandle).toBe('else')
    expect(thenEdge?.targetHandle).toBe('in')
  })

  it('uses left-right ports for root sequence edges', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const layout = layoutCanvas([a, b])
    const next = layout.edges.find((e) => e.label === 'next')
    expect(next?.sourceHandle).toBe('out-right')
    expect(next?.targetHandle).toBe('in-left')
  })

  it('normalizes side handle aliases for reparent', () => {
    const condition = createNode('condition')
    condition.id = 'c1'
    expect(reparentTargetFromHandle(condition, 'then-right')).toEqual({
      kind: 'branch',
      parentId: 'c1',
      branch: 'thenSteps',
    })
  })
})

describe('draft validation', () => {
  it('flags empty parallel and missing executor', () => {
    const parallel = createNode('parallel')
    parallel.id = 'p1'
    const step = createNode('step')
    step.id = 's1'
    step.targetId = ''
    const issues = validateWorkflowDraft([parallel, step])
    expect(issues.some((i) => i.code === 'empty_parallel')).toBe(true)
    expect(issues.some((i) => i.code === 'missing_executor')).toBe(true)
  })

  it('accepts a minimal valid linear workflow', () => {
    const step = createNode('step')
    step.targetId = 'security-operations'
    expect(validateWorkflowDraft([step])).toEqual([])
  })
})
