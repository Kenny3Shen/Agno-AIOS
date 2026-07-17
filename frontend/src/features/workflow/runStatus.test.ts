import { describe, expect, it } from 'vitest'
import {
  appendRunLog,
  applyNodeRunStatusEvent,
  historyStatusFromEvent,
  historySummaryFromEvent,
  reduceNodeRunStatus,
  runEventLabelKey,
} from './runStatus'
import type { WorkflowNode, WorkflowNodeRunStatus, WorkflowRunLogItem } from './types'

const steps: WorkflowNode[] = [
  {
    id: 'a',
    type: 'step',
    name: 'Triage',
    targetId: 'security-operations',
  },
  {
    id: 'b',
    type: 'step',
    name: 'Contain',
    targetId: 'safe-fallback',
  },
]

const event = (
  type: string,
  stepId?: string,
  stepName?: string
): Pick<WorkflowRunLogItem, 'type' | 'stepId' | 'stepName'> => ({
  type,
  stepId,
  stepName,
})

describe('runStatus performance helpers', () => {
  it('applies events incrementally without needing full log replay', () => {
    let map = applyNodeRunStatusEvent(steps, {}, event('step.started', 'a'))
    expect(map).toEqual({ a: 'running' })
    map = applyNodeRunStatusEvent(steps, map, event('step.completed', 'a'))
    expect(map).toEqual({ a: 'ok' })
    map = applyNodeRunStatusEvent(steps, map, event('step.started', 'b'))
    expect(map).toEqual({ a: 'ok', b: 'running' })
  })

  it('matches full reduceNodeRunStatus for a sequence', () => {
    const log = [
      event('step.started', 'a'),
      event('step.completed', 'a'),
      event('step.started', 'b'),
      event('workflow.paused', 'b'),
    ]
    let incremental: Record<string, WorkflowNodeRunStatus> = {}
    for (const item of log) {
      incremental = applyNodeRunStatusEvent(steps, incremental, item)
    }
    expect(incremental).toEqual(reduceNodeRunStatus(steps, log))
  })

  it('returns same map reference when status is unchanged', () => {
    const base = applyNodeRunStatusEvent(steps, {}, event('step.started', 'a'))
    const again = applyNodeRunStatusEvent(steps, base, event('step.started', 'a'))
    expect(again).toBe(base)
  })


  it('marks running nodes when workflow is cancelled', () => {
    let map = applyNodeRunStatusEvent(steps, {}, event('step.started', 'a'))
    map = applyNodeRunStatusEvent(steps, map, event('step.started', 'b'))
    map = applyNodeRunStatusEvent(steps, map, event('workflow.cancelled'))
    expect(map).toEqual({ a: 'error', b: 'error' })
  })

  it('caps run log length', () => {
    let log: WorkflowRunLogItem[] = []
    for (let i = 0; i < 5; i += 1) {
      log = appendRunLog(
        log,
        {
          id: `e-${i}`,
          type: 'step.started',
          message: String(i),
          at: i,
        },
        3
      )
    }
    expect(log).toHaveLength(3)
    expect(log.map((item) => item.message)).toEqual(['2', '3', '4'])
  })
})


describe('runEventLabelKey', () => {
  it('maps known event types to i18n keys', () => {
    expect(runEventLabelKey('workflow.started')).toBe('runEvent_workflow_started')
    expect(runEventLabelKey('workflow.cancelled')).toBe('runEvent_workflow_cancelled')
    expect(runEventLabelKey('step.completed')).toBe('runEvent_step_completed')
    expect(runEventLabelKey('loop.iteration.started')).toBe('runEvent_loop_iteration_started')
  })

  it('returns null for unknown types', () => {
    expect(runEventLabelKey('custom.event')).toBeNull()
    expect(runEventLabelKey('')).toBeNull()
  })
})

describe('historySummaryFromEvent', () => {
  it('drops raw event-type messages', () => {
    expect(
      historySummaryFromEvent({
        type: 'workflow.started',
        message: 'workflow.started',
      }),
    ).toBeUndefined()
  })

  it('prefers content then step name over type-prefixed message', () => {
    expect(
      historySummaryFromEvent({
        type: 'step.completed',
        message: 'step.completed · Triage',
        stepName: 'Triage',
        content: 'triage complete',
      }),
    ).toBe('triage complete')
    expect(
      historySummaryFromEvent({
        type: 'step.completed',
        message: 'step.completed · Triage',
        stepName: 'Triage',
      }),
    ).toBe('Triage')
    expect(
      historySummaryFromEvent({
        type: 'step.completed',
        message: 'step.completed · Triage',
      }),
    ).toBe('Triage')
  })

  it('maps terminal event types to history status', () => {
    expect(historyStatusFromEvent('workflow.cancelled')).toBe('cancelled')
    expect(historyStatusFromEvent('step.completed')).toBeNull()
  })
})
