import { describe, expect, it } from 'vitest'
import { reduceNodeRunStatus } from './runStatus'
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
  reorderRootsByPositions,
  toDefinition,
  defaultTriggers,
  emptySlotsFor,
  branchHandlesFor,
  reparentTargetFromHandle,
  pickConnectionHandles,
  validateWorkflowDraft,
  validateWorkflowName,
  fieldForValidationIssue,
  isKeyboardTargetEditable,
  triggerEnableBlocked,
  workflowWebhookCurl,
  workflowWebhookUrl,
  rotateWebhookSecret,
  resolveNodeCanvasSubtitle,
  executorNamesKey,
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

  it('serializes empty step name without targetId fallback', () => {
    const step = createNode('step')
    step.name = ''
    step.targetId = 'security-operations'
    const definition = toDefinition({ name: 'x', description: '', steps: [step] })
    expect(definition.steps[0]?.name).toBe('')
    expect(definition.steps[0]?.executor).toEqual({ kind: 'agent', ref: 'security-operations' })
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
          skills: ['playbook-skill', 'cve-intel-skill'],
        },
      ],
    }
    const def = toDefinition(withSkills)
    expect(def.steps[0]?.skills).toEqual(['playbook-skill', 'cve-intel-skill'])
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
    expect(restored.steps?.[0]?.skills).toEqual(['playbook-skill', 'cve-intel-skill'])
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

  it('pickConnectionHandles prefers side ports for rightward targets', () => {
    const side = pickConnectionHandles({ x: 0, y: 0 }, { x: 280, y: 20 }, 'out')
    expect(side).toMatchObject({
      sourceHandle: 'out-right',
      targetHandle: 'in-left',
      horizontal: true,
    })
    const branch = pickConnectionHandles({ x: 0, y: 0 }, { x: 300, y: 10 }, 'then')
    expect(branch.sourceHandle).toBe('then-right')
    const vertical = pickConnectionHandles({ x: 0, y: 0 }, { x: 20, y: 200 }, 'out')
    expect(vertical).toMatchObject({
      sourceHandle: 'out',
      targetHandle: 'in',
      horizontal: false,
    })
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
  const t = (key: string, options?: Record<string, unknown>) => {
    if (key === 'subtitleAgent') return 'agent'
    if (key === 'subtitleNested') return 'nested'
    if (key === 'subtitleMaxIter') return `max ${options?.count ?? 3}`
    if (key === 'subtitleBranches') return `branches ${options?.count ?? 0}`
    return key
  }

  it('maps step targetId to executor display name', () => {
    const step = createNode('step')
    step.targetId = 'security-operations'
    const names = new Map([['security-operations', '安全运营助手']])
    expect(resolveNodeCanvasSubtitle(step, t, names)).toBe('安全运营助手')
  })

  it('falls back to targetId when executor catalog misses the ref', () => {
    const step = createNode('step')
    step.targetId = 'custom-agent'
    expect(resolveNodeCanvasSubtitle(step, t, {})).toBe('custom-agent')
  })

  it('uses subtitleAgent when step has no targetId', () => {
    const step = createNode('step')
    step.targetId = ''
    expect(resolveNodeCanvasSubtitle(step, t, {})).toBe('agent')
  })

  it('formats control-flow subtitles', () => {
    const condition = createNode('condition')
    condition.evaluatorCel = 'input.score > 0.8'
    expect(resolveNodeCanvasSubtitle(condition, t, {})).toBe('input.score > 0.8')

    const loop = createNode('loop')
    loop.maxIterations = 5
    expect(resolveNodeCanvasSubtitle(loop, t, {})).toBe('max 5')

    const parallel = createNode('parallel')
    parallel.steps = [createNode('step'), createNode('step')]
    expect(resolveNodeCanvasSubtitle(parallel, t, {})).toBe('branches 2')
  })

  it('executorNamesKey is order-stable', () => {
    expect(executorNamesKey({ b: 'B', a: 'A' })).toBe(executorNamesKey(new Map([['a', 'A'], ['b', 'B']])))
  })
})

describe('isKeyboardTargetEditable', () => {
  it('treats input and ant-select hosts as editable', () => {
    const input = document.createElement('input')
    expect(isKeyboardTargetEditable(input)).toBe(true)
    const host = document.createElement('div')
    host.className = 'ant-select'
    const inner = document.createElement('span')
    host.appendChild(inner)
    document.body.appendChild(host)
    expect(isKeyboardTargetEditable(inner)).toBe(true)
    host.remove()
  })

  it('allows canvas shortcuts on plain elements', () => {
    const div = document.createElement('div')
    expect(isKeyboardTargetEditable(div)).toBe(false)
    expect(isKeyboardTargetEditable(null)).toBe(false)
  })
})

