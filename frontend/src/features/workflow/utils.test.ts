import { describe, expect, it } from 'vitest'
import {
  applyAutoLayout,
  buildWorkflowCode,
  createNode,
  fromRecord,
  layoutCanvas,
  computeSmartSnap,
  moveNodeAfter,
  moveStep,
  reparentNode,
  toDefinition,
  defaultTriggers,
  emptySlotsFor,
  branchHandlesFor,
  reparentTargetFromHandle,
  validateWorkflowDraft,
  validateWorkflowName,
  fieldForValidationIssue,
  updateNodeInTree,
  findNode,
  summarizeSelectedAgentSteps,
  cloneNodeDeep,
  pasteNodesIntoSelection,
  preserveSelectionAfterReload,
  locateNode,
  triggerEnableBlocked,
  workflowWebhookCurl,
  workflowWebhookUrl,
  rotateWebhookSecret,
  resolveNodeCanvasSubtitle,
  executorNamesKey,
} from './utils'

const translateWorkflowSubtitle = (key: string, options?: Record<string, unknown>) => {
  if (key === 'subtitleAgent') return 'agent'
  if (key === 'subtitleNested') return 'nested'
  if (key === 'subtitleMaxIter') return `max ${options?.count ?? 3}`
  if (key === 'subtitleBranches') return `branches ${options?.count ?? 0}`
  return key
}
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
  nextCronAt: null,
  selectedId: null,
  selectedIds: [],
  dirty: false,
  loading: false,
  saving: false,
  running: false,
  runLog: [],
  nodeRunStatus: {},
  runHistory: [],
  error: null,
  validationIssues: [],
  validationEpoch: 0,
  focusEpoch: 0,
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

  it('serializes an empty step name with its selected executor', () => {
    const step = createNode('step')
    step.name = ''
    step.targetId = 'security-operations'
    const definition = toDefinition({ name: 'x', description: '', steps: [step] })
    expect(definition.steps[0]?.name).toBe('')
    expect(definition.steps[0]?.executor).toEqual({ kind: 'agent', ref: 'security-operations' })
  })

  it('keeps a missing executor empty instead of silently selecting an agent', () => {
    const step = createNode('step')
    step.id = 'missing-executor'
    step.targetId = ''
    const definition = toDefinition({ name: 'x', description: '', steps: [step] })
    expect(definition.steps[0]?.executor).toEqual({ kind: 'agent', ref: '' })

    const restored = fromRecord({
      id: 'wf-missing-executor',
      name: 'x',
      description: '',
      owner_user_id: 'u',
      definition: {
        name: 'x',
        description: '',
        steps: [{ id: 'missing-executor', type: 'step', name: 'Missing executor' }],
      },
      enabled: true,
      version: 1,
      created_at: 1,
      updated_at: 1,
    })
    const restoredStep = restored.steps?.[0]
    expect(restoredStep?.targetId).toBe('')
    expect(validateWorkflowDraft(restored.steps ?? []).map((issue) => issue.code)).toContain('missing_executor')
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

  it('moves a root after its connection target', () => {
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
    const condition = createNode('condition')
    condition.id = 'branch'
    condition.thenSteps = [{ id: 'then', type: 'step', targetId: 'security-operations', name: 'Then' }]
    condition.elseSteps = [{ id: 'else', type: 'step', targetId: 'safe-fallback', name: 'Else' }]
    const definition = toDefinition({
      name: 'n',
      description: '',
      steps: [parallel, condition],
    })
    expect(definition.steps[1]?.type).toBe('condition')
    expect(definition.steps[1]?.steps).toEqual([
      {
        id: 'then',
        type: 'step',
        name: 'Then',
        executor: { kind: 'agent', ref: 'security-operations' },
        instructions: '',
      },
    ])
    expect(definition.steps[1]?.else).toEqual([
      {
        id: 'else',
        type: 'step',
        name: 'Else',
        executor: { kind: 'agent', ref: 'safe-fallback' },
        instructions: '',
      },
    ])
    expect(definition.steps[1]).not.toHaveProperty('then_steps')
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
    expect(restored.steps?.[0]?.id).toBe('fanout')
    expect(restored.steps?.[0]?.steps?.map((node) => node.id)).toEqual(['c1', 'c2'])
    expect(restored.steps?.[0]?.steps).toHaveLength(2)
    expect(restored.steps?.[1]?.id).toBe('branch')
    expect(restored.steps?.[1]?.thenSteps?.[0]?.id).toBe('then')
    expect(restored.steps?.[1]?.elseSteps?.[0]?.id).toBe('else')
    expect(restored.steps?.[1]?.thenSteps).toHaveLength(1)
    expect(restored.steps?.[1]?.elseSteps).toHaveLength(1)
    expect(restored.version).toBe(3)
    expect(restored.publishedVersion).toBe(2)
    expect(restored.publishedAt).toBe(1_700_000_000)
    expect(restored.hasPublished).toBe(true)
  })

  it('preserves canonical router branch IDs when loading a record', () => {
    const restored = fromRecord({
      id: 'wf-router',
      name: 'Router',
      description: '',
      owner_user_id: 'u',
      definition: {
        name: 'Router',
        description: '',
        steps: [
          {
            id: 'severity-router',
            type: 'router',
            name: 'Route severity',
            selector: { cel: 'input' },
            choices: [
              { id: 'critical', name: 'critical', steps: [] },
              { id: 'other', name: 'other', steps: [] },
            ],
          },
        ],
      },
      enabled: true,
      version: 1,
      created_at: 1,
      updated_at: 1,
    })

    expect(restored.steps?.[0]).toMatchObject({
      id: 'severity-router',
      choices: [{ id: 'critical' }, { id: 'other' }],
    })
  })

  it('blocks trigger enable when unpublished or dirty', () => {
    expect(triggerEnableBlocked({ hasPublished: false, dirty: false })).toBe('unpublished')
    expect(triggerEnableBlocked({ hasPublished: true, dirty: true })).toBe('dirty')
    expect(triggerEnableBlocked({ hasPublished: true, dirty: false })).toBeNull()
  })

  it('round-trips step skills on definition', () => {
    const withSkills: WorkflowState = {
      ...state,
      steps: [
        {
          id: 's1',
          type: 'step',
          name: 'T',
          targetId: 'security-operations',
          instructions: 'x',
          skills: ['cve-intel-skill', 'hitl-containment-skill'],
        },
      ],
    }
    const def = toDefinition(withSkills)
    expect(def.steps[0]?.skills).toEqual(['cve-intel-skill', 'hitl-containment-skill'])
    const restored = fromRecord({
      id: 'wf',
      name: 'n',
      description: '',
      owner_user_id: 'u',
      definition: def,
      enabled: true,
      version: 1,
      created_at: 1,
      updated_at: 1,
    })
    expect(restored.steps?.[0]?.skills).toEqual(['cve-intel-skill', 'hitl-containment-skill'])
  })

  it('builds webhook URL and curl sample', () => {
    expect(workflowWebhookUrl('wf-1', 'https://app.example')).toBe(
      'https://app.example/api/workflows/wf-1/hooks/webhook'
    )
    const curl = workflowWebhookCurl('wf-1', 's3cret', 'https://app.example')
    expect(curl).toContain("secret=s3cret")
    expect(curl).toContain('-N')
    expect(curl).toContain('hooks/webhook')
    expect(rotateWebhookSecret().length).toBeGreaterThan(8)
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
    expect(next.blocked).toBeUndefined()
    expect(next.steps).toHaveLength(1)
    expect(next.steps[0]?.type).toBe('parallel')
    expect(next.steps[0]?.steps?.map((n) => n.id)).toEqual(['s1'])
  })

  it('blocks HITL reparent into parallel', () => {
    const parallel = createNode('parallel')
    parallel.id = 'p1'
    const step = createNode('step')
    step.id = 's1'
    step.requiresConfirmation = true
    const next = reparentNode([parallel, step], 's1', {
      kind: 'branch',
      parentId: 'p1',
      branch: 'steps',
    })
    expect(next.blocked).toBe('hitl_in_parallel')
    expect(next.steps).toHaveLength(2)
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
    expect(next.blocked).toBe('cycle')
    expect(next.steps[0]?.id).toBe('p1')
    expect(next.steps[0]?.steps?.[0]?.id).toBe('s1')
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
    // Roots flow horizontally (left → right).
    expect(laid[1]!.position!.x).toBeGreaterThan(laid[0]!.position!.x)
  })

  it('auto-layout separates condition then/else without vertical overlap', () => {
    const condition = createNode('condition')
    condition.id = 'c1'
    condition.thenSteps = [
      {
        id: 'contain',
        type: 'step',
        name: 'Contain',
        targetId: 'security-operations',
        requiresConfirmation: true,
      },
    ]
    condition.elseSteps = [
      { id: 'report', type: 'step', name: 'Report', targetId: 'safe-fallback' },
    ]
    const triage = createNode('step')
    triage.id = 'triage'
    triage.name = 'Triage'
    const laid = applyAutoLayout([triage, condition])
    const contain = laid[1]?.thenSteps?.[0]
    const report = laid[1]?.elseSteps?.[0]
    expect(contain?.position && report?.position).toBeTruthy()
    // then above else
    expect(contain!.position!.y).toBeLessThan(report!.position!.y)
    // No box overlap: contain bottom + gap <= report top (est height ~118 with HITL)
    const containBottom = contain!.position!.y + 118
    expect(report!.position!.y).toBeGreaterThanOrEqual(containBottom)
    // Children to the right of condition
    expect(contain!.position!.x).toBeGreaterThan(laid[1]!.position!.x)
  })

  it('auto-layout accounts for empty branch CTAs without sibling overlap', () => {
    const empty = createNode('condition')
    empty.id = 'empty-cond'
    empty.thenSteps = []
    empty.elseSteps = []
    const withKids = createNode('condition')
    withKids.id = 'full-cond'
    withKids.thenSteps = [{ id: 't1', type: 'step', name: 'Then', targetId: 'security-operations' }]
    withKids.elseSteps = [{ id: 'e1', type: 'step', name: 'Else', targetId: 'safe-fallback' }]
    // Two root conditions stacked via layout columns; safety pass uses estimated height.
    const laid = applyAutoLayout([empty, withKids])
    expect(laid[0]?.position && laid[1]?.position).toBeTruthy()
    // Roots are horizontal; children of full-cond must not overlap each other.
    const t1 = laid[1]?.thenSteps?.[0]
    const e1 = laid[1]?.elseSteps?.[0]
    expect(t1?.position && e1?.position).toBeTruthy()
    const t1Bottom = t1!.position!.y + 96
    expect(e1!.position!.y).toBeGreaterThanOrEqual(t1Bottom)
  })

  it('auto-layout separates parallel children without vertical overlap', () => {
    const parallel = createNode('parallel')
    parallel.id = 'p1'
    parallel.steps = [
      { id: 'a', type: 'step', name: 'A', targetId: 'security-operations' },
      { id: 'b', type: 'step', name: 'B', targetId: 'safe-fallback' },
      { id: 'c', type: 'step', name: 'C', targetId: 'safe-fallback' },
    ]
    const laid = applyAutoLayout([parallel])
    const kids = laid[0]?.steps ?? []
    expect(kids).toHaveLength(3)
    expect(kids.every((k) => k.position)).toBe(true)
    // stacked top → bottom
    expect(kids[0]!.position!.y).toBeLessThan(kids[1]!.position!.y)
    expect(kids[1]!.position!.y).toBeLessThan(kids[2]!.position!.y)
    const aBottom = kids[0]!.position!.y + 96
    expect(kids[1]!.position!.y).toBeGreaterThanOrEqual(aBottom)
    // children to the right of parallel parent
    expect(kids[0]!.position!.x).toBeGreaterThan(laid[0]!.position!.x)
  })


  it('auto-layout separates router choice children without vertical overlap', () => {
    const router = createNode('router')
    router.id = 'r1'
    router.choices = [
      {
        id: 'c1',
        name: 'Path A',
        steps: [{ id: 'a', type: 'step', name: 'A', targetId: 'security-operations' }],
      },
      {
        id: 'c2',
        name: 'Path B',
        steps: [{ id: 'b', type: 'step', name: 'B', targetId: 'safe-fallback' }],
      },
    ]
    const laid = applyAutoLayout([router])
    const a = laid[0]?.choices?.[0]?.steps[0]
    const b = laid[0]?.choices?.[1]?.steps[0]
    expect(a?.position && b?.position).toBeTruthy()
    expect(a!.position!.y).toBeLessThan(b!.position!.y)
    expect(b!.position!.y).toBeGreaterThanOrEqual(a!.position!.y + 96)
    expect(a!.position!.x).toBeGreaterThan(laid[0]!.position!.x)
  })


  it('auto-layout separates loop body children without vertical overlap', () => {
    const loop = createNode('loop')
    loop.id = 'loop-1'
    loop.steps = [
      { id: 'a', type: 'step', name: 'A', targetId: 'security-operations' },
      { id: 'b', type: 'step', name: 'B', targetId: 'safe-fallback' },
    ]
    const laid = applyAutoLayout([loop])
    const kids = laid[0]?.steps ?? []
    expect(kids).toHaveLength(2)
    expect(kids[0]!.position!.y).toBeLessThan(kids[1]!.position!.y)
    expect(kids[1]!.position!.y).toBeGreaterThanOrEqual(kids[0]!.position!.y + 96)
    expect(kids[0]!.position!.x).toBeGreaterThan(laid[0]!.position!.x)
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

  it('uses defaultPathName for unnamed router choices', () => {
    const router = createNode('router')
    router.choices = router.choices?.map((c, i) => ({ ...c, name: i === 0 ? '' : c.name }))
    const handles = branchHandlesFor(router)
    expect(handles[0]?.label).toBe('defaultPathName')
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
    // Child placed to the right of parent → side ports + branch -right alias.
    condition.position = { x: 0, y: 40 }
    condition.thenSteps = [
      {
        id: 't1',
        type: 'step',
        name: 'T',
        targetId: 'security-operations',
        position: { x: 280, y: 0 },
      },
    ]
    condition.elseSteps = [
      {
        id: 'e1',
        type: 'step',
        name: 'E',
        targetId: 'safe-fallback',
        position: { x: 280, y: 120 },
      },
    ]
    const layout = layoutCanvas([condition])
    const thenEdge = layout.edges.find((e) => e.target === 't1')
    const elseEdge = layout.edges.find((e) => e.target === 'e1')
    expect(thenEdge?.sourceHandle).toBe('then-right')
    expect(elseEdge?.sourceHandle).toBe('else-right')
    expect(thenEdge?.targetHandle).toBe('in-left')
    expect(elseEdge?.targetHandle).toBe('in-left')
  })

  it('uses left-right ports for horizontally placed root sequence', () => {
    const a = createNode('step')
    a.id = 'a'
    a.position = { x: 0, y: 0 }
    const b = createNode('step')
    b.id = 'b'
    b.position = { x: 280, y: 0 }
    const layout = layoutCanvas([a, b])
    const next = layout.edges.find((e) => e.label === 'next')
    expect(next?.sourceHandle).toBe('out-right')
    expect(next?.targetHandle).toBe('in-left')
  })

  it('defaults root sequence without positions to left-right ports', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const layout = layoutCanvas([a, b])
    const next = layout.edges.find((e) => e.label === 'next')
    expect(next?.sourceHandle).toBe('out-right')
    expect(next?.targetHandle).toBe('in-left')
  })

  it('uses side ports for nested child placed to the right of parent', () => {
    const parent = createNode('parallel')
    parent.id = 'p1'
    parent.position = { x: 0, y: 0 }
    parent.steps = [
      {
        id: 'c1',
        type: 'step',
        name: 'Child',
        targetId: 'security-operations',
        position: { x: 280, y: 20 },
      },
    ]
    const layout = layoutCanvas([parent])
    const edge = layout.edges.find((e) => e.target === 'c1')
    expect(edge?.sourceHandle).toBe('out-right')
    expect(edge?.targetHandle).toBe('in-left')
  })

  it('uses top-bottom ports when sequence is stacked vertically', () => {
    const a = createNode('step')
    a.id = 'a'
    a.position = { x: 0, y: 0 }
    const b = createNode('step')
    b.id = 'b'
    b.position = { x: 0, y: 160 }
    const layout = layoutCanvas([a, b])
    const next = layout.edges.find((e) => e.label === 'next')
    expect(next?.sourceHandle).toBe('out')
    expect(next?.targetHandle).toBe('in')
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

describe('smart snap guides', () => {
  it('snaps dragged left edge to peer left edge', () => {
    const result = computeSmartSnap(
      { x: 102, y: 40, width: 200, height: 96 },
      [{ x: 100, y: 200, width: 200, height: 96 }]
    )
    expect(result.x).toBe(100)
    expect(result.guides.some((g) => g.orientation === 'v' && g.pos === 100)).toBe(true)
  })

  it('snaps vertical centers when only mids align', () => {
    // peer center y=80; drag center ~82 (y=32, h=100) — tops far apart
    const result = computeSmartSnap(
      { x: 0, y: 32, width: 200, height: 100 },
      [{ x: 300, y: 40, width: 160, height: 80 }]
    )
    // peer mid = 80; drag mid = 82 → snap y so mid=80 → y=30
    expect(result.y).toBe(30)
    expect(result.guides.some((g) => g.orientation === 'h' && g.pos === 80)).toBe(true)
  })

  it('returns unchanged when far from peers', () => {
    const result = computeSmartSnap(
      { x: 0, y: 0, width: 200, height: 96 },
      [{ x: 400, y: 400, width: 200, height: 96 }]
    )
    expect(result.x).toBe(0)
    expect(result.y).toBe(0)
    expect(result.guides).toEqual([])
  })
})

describe('fieldForValidationIssue', () => {
  it('maps issue codes to inspector fields', () => {
    expect(fieldForValidationIssue({ code: 'missing_executor' })).toBe('executor')
    expect(fieldForValidationIssue({ code: 'missing_workflow_ref' })).toBe('workflow_ref')
    expect(fieldForValidationIssue({ code: 'empty_parallel' })).toBe('children')
    expect(fieldForValidationIssue({ code: 'empty_workflow' })).toBe('name')
  })
})


  it('keeps empty control-flow names on save (UI uses defaultName i18n)', () => {
    const parallel = createNode('parallel')
    const definition = toDefinition({ name: '', description: '', steps: [parallel] })
    expect(definition.name).toBe('')
    expect(definition.steps[0]?.name).toBe('')
    const restored = fromRecord({
      id: 'wf',
      name: '',
      description: '',
      owner_user_id: 'u',
      definition,
      enabled: true,
      version: 1,
      created_at: 1,
      updated_at: 1,
    })
    expect(restored.steps?.[0]?.name).toBe('')
  })


  it('flags user_input without named fields', () => {
    const issues = validateWorkflowDraft([
      {
        id: 's1',
        type: 'step',
        name: 'Ask',
        targetId: 'security-operations',
        requiresUserInput: true,
        userInputSchema: [{ name: '', field_type: 'str' }],
      },
    ])
    expect(issues.some((i) => i.code === 'user_input_schema_empty' || i.code === 'user_input_schema_field')).toBe(
      true,
    )
  })


  it('requires a workflow name', () => {
    expect(validateWorkflowName('')?.code).toBe('empty_name')
    expect(validateWorkflowName('  IR  ')).toBeNull()
  })

  it('flags HITL steps nested under Parallel', () => {
    const hitl = createNode('step')
    hitl.id = 'h'
    hitl.requiresConfirmation = true
    hitl.targetId = 'security-operations'
    const parallel = createNode('parallel')
    parallel.id = 'p'
    parallel.steps = [hitl]
    const issues = validateWorkflowDraft([parallel])
    expect(issues.some((issue) => issue.code === 'hitl_in_parallel')).toBe(true)
    expect(fieldForValidationIssue({ code: 'hitl_in_parallel' })).toBe('hitl')
  })


  it('flags empty condition/router CEL', () => {
    const condition = createNode('condition')
    condition.evaluatorCel = '   '
    condition.thenSteps = [{ id: 't', type: 'step', name: 'T', targetId: 'security-operations' }]
    const router = createNode('router')
    router.selectorCel = ''
    const issues = validateWorkflowDraft([condition, router])
    expect(issues.some((i) => i.code === 'empty_condition_cel')).toBe(true)
    expect(issues.some((i) => i.code === 'empty_router_cel')).toBe(true)
    expect(fieldForValidationIssue({ code: 'empty_condition_cel' })).toBe('evaluator')
    expect(fieldForValidationIssue({ code: 'empty_router_cel' })).toBe('selector')
  })


  it('flags self-referencing nested workflow', () => {
    const nested = createNode('workflow_ref')
    nested.workflowId = 'wf-1'
    const issues = validateWorkflowDraft([nested], (key) => key, 'wf-1')
    expect(issues.some((i) => i.code === 'self_workflow_ref')).toBe(true)
    expect(fieldForValidationIssue({ code: 'self_workflow_ref' })).toBe('workflow_ref')
  })

describe('resolveNodeCanvasSubtitle', () => {
  it('maps step targetId to executor display name', () => {
    const step = createNode('step')
    step.targetId = 'security-operations'
    const names = new Map([['security-operations', '安全运营助手']])
    expect(resolveNodeCanvasSubtitle(step, translateWorkflowSubtitle, names)).toBe('安全运营助手')
  })

  it('falls back to targetId when executor catalog misses the ref', () => {
    const step = createNode('step')
    step.targetId = 'custom-agent'
    expect(resolveNodeCanvasSubtitle(step, translateWorkflowSubtitle, {})).toBe('custom-agent')
  })

  it('uses subtitleAgent when step has no targetId', () => {
    const step = createNode('step')
    step.targetId = ''
    expect(resolveNodeCanvasSubtitle(step, translateWorkflowSubtitle, {})).toBe('agent')
  })

  it('formats control-flow subtitles', () => {
    const condition = createNode('condition')
    condition.evaluatorCel = 'input.score > 0.8'
    expect(resolveNodeCanvasSubtitle(condition, translateWorkflowSubtitle, {})).toBe('input.score > 0.8')

    const loop = createNode('loop')
    loop.maxIterations = 5
    expect(resolveNodeCanvasSubtitle(loop, translateWorkflowSubtitle, {})).toBe('max 5')

    const parallel = createNode('parallel')
    parallel.steps = [createNode('step'), createNode('step')]
    expect(resolveNodeCanvasSubtitle(parallel, translateWorkflowSubtitle, {})).toBe('branches 2')
  })

  it('executorNamesKey is order-stable', () => {
    expect(executorNamesKey({ b: 'B', a: 'A' })).toBe(executorNamesKey(new Map([['a', 'A'], ['b', 'B']])))
  })
})


describe('updateNodeInTree bulk agent patch', () => {
  it('bulk-patches only agent steps', () => {
    const a = createNode('step')
    a.id = 'a'
    a.targetId = 'security-operations'
    a.requiresConfirmation = false
    const b = createNode('step')
    b.id = 'b'
    b.targetId = 'security-operations'
    b.requiresConfirmation = false
    const c = createNode('parallel')
    c.id = 'c'
    let steps = [a, b, c]
    for (const id of ['a', 'b', 'c']) {
      const node = findNode(steps, id)
      if (!node || node.type !== 'step') continue
      steps = updateNodeInTree(steps, id, (item) => ({
        ...item,
        targetId: 'safe-fallback',
        requiresConfirmation: true,
      }))
    }
    expect(findNode(steps, 'a')).toMatchObject({
      targetId: 'safe-fallback',
      requiresConfirmation: true,
    })
    expect(findNode(steps, 'b')).toMatchObject({
      targetId: 'safe-fallback',
      requiresConfirmation: true,
    })
    expect(findNode(steps, 'c')?.type).toBe('parallel')
  })
})

describe('updateNodeInTree bulk skills patch', () => {
  it('bulk-patches skills on agent steps', () => {
    const a = createNode('step')
    a.id = 'a'
    a.skills = ['cve-intel-skill']
    const b = createNode('step')
    b.id = 'b'
    b.skills = ['intranet-ip-skill']
    let steps = [a, b]
    for (const id of ['a', 'b']) {
      steps = updateNodeInTree(steps, id, (item) => ({
        ...item,
        skills: ['cve-intel-skill', 'hitl-containment-skill'],
      }))
    }
    expect(findNode(steps, 'a')?.skills).toEqual(['cve-intel-skill', 'hitl-containment-skill'])
    expect(findNode(steps, 'b')?.skills).toEqual(['cve-intel-skill', 'hitl-containment-skill'])
  })
})

describe('updateNodeInTree bulk instructions patch', () => {
  it('bulk-patches instructions on agent steps', () => {
    const a = createNode('step')
    a.id = 'a'
    a.instructions = 'one'
    const b = createNode('step')
    b.id = 'b'
    b.instructions = 'two'
    let steps = [a, b]
    for (const id of ['a', 'b']) {
      steps = updateNodeInTree(steps, id, (item) => ({
        ...item,
        instructions: 'shared ops brief',
      }))
    }
    expect(findNode(steps, 'a')?.instructions).toBe('shared ops brief')
    expect(findNode(steps, 'b')?.instructions).toBe('shared ops brief')
  })
})

describe('updateNodeInTree bulk HITL flags', () => {
  it('bulk-patches HITL flags on agent steps', () => {
    const a = createNode('step')
    a.id = 'a'
    a.requiresUserInput = false
    a.requiresOutputReview = false
    const b = createNode('step')
    b.id = 'b'
    b.requiresUserInput = true
    b.requiresOutputReview = false
    let steps = [a, b]
    for (const id of ['a', 'b']) {
      steps = updateNodeInTree(steps, id, (item) => ({
        ...item,
        requiresUserInput: true,
        requiresOutputReview: true,
      }))
    }
    expect(findNode(steps, 'a')).toMatchObject({
      requiresUserInput: true,
      requiresOutputReview: true,
    })
    expect(findNode(steps, 'b')).toMatchObject({
      requiresUserInput: true,
      requiresOutputReview: true,
    })
  })
})

describe('summarizeSelectedAgentSteps', () => {
  it('detects mixed skills, instructions, and HITL flags', () => {
    const a = createNode('step')
    a.id = 'a'
    a.targetId = 'security-operations'
    a.skills = ['cve-intel-skill']
    a.instructions = 'one'
    a.requiresConfirmation = true
    a.requiresUserInput = false
    a.requiresOutputReview = false
    const b = createNode('step')
    b.id = 'b'
    b.targetId = 'safe-fallback'
    b.skills = ['intranet-ip-skill']
    b.instructions = 'two'
    b.requiresConfirmation = false
    b.requiresUserInput = true
    b.requiresOutputReview = true
    const summary = summarizeSelectedAgentSteps([a, b])
    expect(summary.agentCount).toBe(2)
    expect(summary.sharedTargetId).toBeUndefined()
    expect(summary.skillsMixed).toBe(true)
    expect(summary.sharedSkills).toEqual([])
    expect(summary.instructionsMixed).toBe(true)
    expect(summary.sharedInstructions).toBe('')
    expect(summary.allConfirm).toBe(false)
    expect(summary.noneConfirm).toBe(false)
    expect(summary.allUserInput).toBe(false)
    expect(summary.noneUserInput).toBe(false)
    expect(summary.allOutputReview).toBe(false)
    expect(summary.noneOutputReview).toBe(false)
  })

  it('shares values when agents match', () => {
    const a = createNode('step')
    a.targetId = 'security-operations'
    a.skills = ['hitl-containment-skill']
    a.instructions = 'shared'
    a.requiresConfirmation = true
    a.requiresUserInput = true
    a.requiresOutputReview = false
    const b = { ...a, id: 'b' }
    const summary = summarizeSelectedAgentSteps([a, b])
    expect(summary.sharedTargetId).toBe('security-operations')
    expect(summary.skillsMixed).toBe(false)
    expect(summary.sharedSkills).toEqual(['hitl-containment-skill'])
    expect(summary.instructionsMixed).toBe(false)
    expect(summary.sharedInstructions).toBe('shared')
    expect(summary.allConfirm).toBe(true)
    expect(summary.noneConfirm).toBe(false)
    expect(summary.allUserInput).toBe(true)
    expect(summary.noneOutputReview).toBe(true)
  })
})

describe('cloneNodeDeep', () => {
  it('cloneNodeDeep isolates skills arrays', () => {
    const a = createNode('step')
    a.skills = ['hitl-containment-skill']
    const clone = cloneNodeDeep(a)
    clone.skills?.push('cve-intel-skill')
    expect(a.skills).toEqual(['hitl-containment-skill'])
    expect(clone.skills).toEqual(['hitl-containment-skill', 'cve-intel-skill'])
    expect(clone.id).not.toBe(a.id)
  })
})

describe('pasteNodesIntoSelection', () => {
  it('pastes into an empty condition then-branch when selected', () => {
    const condition = createNode('condition')
    condition.id = 'cond'
    condition.thenSteps = []
    condition.elseSteps = []
    const agent = createNode('step')
    agent.id = 'agent'
    const pasted = pasteNodesIntoSelection([condition], [cloneNodeDeep(agent)], ['cond'], 'cond')
    const host = findNode(pasted.steps, 'cond')
    expect(host?.thenSteps?.length).toBe(1)
    expect(pasted.steps).toHaveLength(1)
  })

  it('appends to roots when no container selected', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const pasted = pasteNodesIntoSelection([a], [cloneNodeDeep(b)], [], null)
    expect(pasted.steps.map((n) => n.id)).toEqual(['a', expect.any(String)])
    expect(pasted.steps).toHaveLength(2)
  })

  it('pastes into parallel body when selected', () => {
    const parallel = createNode('parallel')
    parallel.id = 'par'
    parallel.steps = []
    const agent = createNode('step')
    agent.id = 'agent'
    const pasted = pasteNodesIntoSelection([parallel], [cloneNodeDeep(agent)], ['par'], 'par')
    const host = findNode(pasted.steps, 'par')
    expect(host?.steps?.length).toBe(1)
    expect(pasted.steps).toHaveLength(1)
  })

  it('appends to roots when multi-select is active', () => {
    const a = createNode('step')
    a.id = 'a'
    const cond = createNode('condition')
    cond.id = 'cond'
    cond.thenSteps = []
    cond.elseSteps = []
    const b = createNode('step')
    b.id = 'b'
    const pasted = pasteNodesIntoSelection([a, cond], [cloneNodeDeep(b)], ['a', 'cond'], 'cond')
    expect(pasted.steps).toHaveLength(3)
    expect(findNode(pasted.steps, 'cond')?.thenSteps?.length ?? 0).toBe(0)
    expect(pasted.multiSelectRootPaste).toBe(true)
    expect(pasted.divertedHitlCount).toBe(0)
  })

  it('marks single-select paste as non multi-select root', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const pasted = pasteNodesIntoSelection([a], [cloneNodeDeep(b)], ['a'], 'a')
    expect(pasted.multiSelectRootPaste).toBe(false)
  })

  it('pastes as sibling after a selected agent step', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const c = createNode('step')
    c.id = 'c'
    const pasted = pasteNodesIntoSelection([a, b], [cloneNodeDeep(c)], ['a'], 'a')
    expect(pasted.steps).toHaveLength(3)
    expect(pasted.steps[0]?.id).toBe('a')
    expect(pasted.steps[2]?.id).toBe('b')
    expect(pasted.steps[1]?.id).not.toBe('a')
    expect(pasted.steps[1]?.id).not.toBe('b')
  })

  it('pastes multiple clones after sibling preserving order', () => {
    const a = createNode('step')
    a.id = 'a'
    const x = createNode('step')
    x.id = 'x'
    x.name = 'X'
    const y = createNode('step')
    y.id = 'y'
    y.name = 'Y'
    const pasted = pasteNodesIntoSelection(
      [a],
      [cloneNodeDeep(x), cloneNodeDeep(y)],
      ['a'],
      'a',
    )
    expect(pasted.steps).toHaveLength(3)
    expect(pasted.steps[0]?.id).toBe('a')
    expect(pasted.steps[1]?.name).toBe('X')
    expect(pasted.steps[2]?.name).toBe('Y')
  })

  it('routes HITL paste out of parallel to root', () => {
    const parallel = createNode('parallel')
    parallel.id = 'par'
    parallel.steps = []
    const hitl = createNode('step')
    hitl.id = 'hitl'
    hitl.requiresConfirmation = true
    const pasted = pasteNodesIntoSelection([parallel], [cloneNodeDeep(hitl)], ['par'], 'par')
    expect(findNode(pasted.steps, 'par')?.steps?.length ?? 0).toBe(0)
    expect(pasted.steps).toHaveLength(2)
    expect(pasted.divertedHitlCount).toBe(1)
    expect(pasted.multiSelectRootPaste).toBe(false)
    expect(pasted.steps.some((n) => n.requiresConfirmation)).toBe(true)
  })

  it('locateNode finds nested then-branch index', () => {
    const agent = createNode('step')
    agent.id = 't1'
    const cond = createNode('condition')
    cond.id = 'cond'
    cond.thenSteps = [agent]
    cond.elseSteps = []
    expect(locateNode([cond], 't1')).toEqual({
      kind: 'branch',
      parentId: 'cond',
      branch: 'thenSteps',
      index: 0,
    })
  })
})

describe('preserveSelectionAfterReload', () => {
  it('keeps multi-selection when nodes still exist after save reload', () => {
    const a = createNode('step')
    a.id = 'a'
    const b = createNode('step')
    b.id = 'b'
    const c = createNode('step')
    c.id = 'c'
    const result = preserveSelectionAfterReload([a, b, c], 'b', ['a', 'b'], 'a')
    expect(result).toEqual({ selectedId: 'b', selectedIds: ['a', 'b'] })
  })

  it('falls back when selection was removed', () => {
    const a = createNode('step')
    a.id = 'a'
    const result = preserveSelectionAfterReload([a], 'gone', ['gone'], 'a')
    expect(result).toEqual({ selectedId: 'a', selectedIds: ['a'] })
  })
})
