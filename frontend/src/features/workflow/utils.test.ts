import { describe, expect, it } from 'vitest'
import {
  createNode,
  defaultTriggers,
  fromRecord,
  reparentNode,
  toDefinition,
  triggerEnableBlocked,
  validateWorkflowDraft,
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

describe('workflow utils (critical)', () => {
  it('builds a linear definition for save/run', () => {
    expect(toDefinition(state)).toMatchObject({
      name: 'IR',
      steps: [
        { id: 'a', executor: { kind: 'agent', ref: 'security-operations' } },
        { id: 'b', executor: { kind: 'agent', ref: 'safe-fallback' } },
      ],
    })
  })

  it('validates empty parallel and missing executor', () => {
    const parallel = createNode('parallel')
    parallel.id = 'p1'
    const step = createNode('step')
    step.id = 's1'
    step.targetId = ''
    const issues = validateWorkflowDraft([parallel, step])
    expect(issues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining(['empty_parallel', 'missing_executor']),
    )
  })

  it('blocks reparenting HITL into parallel', () => {
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

  it('blocks trigger enable when unpublished or dirty', () => {
    expect(triggerEnableBlocked({ hasPublished: false, dirty: false })).toBe('unpublished')
    expect(triggerEnableBlocked({ hasPublished: true, dirty: true })).toBe('dirty')
    expect(triggerEnableBlocked({ hasPublished: true, dirty: false })).toBeNull()
  })

  it('serializes an empty step name with its selected executor', () => {
    const step = createNode('step')
    step.name = ''
    step.targetId = 'security-operations'
    const definition = toDefinition({ name: 'x', description: '', steps: [step] })
    expect(definition.steps[0]?.name).toBe('')
    expect(definition.steps[0]?.executor).toEqual({ kind: 'agent', ref: 'security-operations' })
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
    expect(restored.steps?.[0]?.steps?.map((node) => node.id)).toEqual(['c1', 'c2'])
    expect(restored.steps?.[1]?.thenSteps?.[0]?.id).toBe('then')
    expect(restored.steps?.[1]?.elseSteps?.[0]?.id).toBe('else')
    expect(restored.version).toBe(3)
    expect(restored.publishedVersion).toBe(2)
    expect(restored.hasPublished).toBe(true)
  })
})
