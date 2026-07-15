import { describe, expect, it } from 'vitest'
import {
  appendRunLog,
  applyNodeRunStatusEvent,
  reduceNodeRunStatus,
} from './runStatus'
import type { WorkflowNode, WorkflowRunLogItem } from './types'

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
    let incremental: Record<string, string> = {}
    for (const item of log) {
      incremental = applyNodeRunStatusEvent(steps, incremental as never, item)
    }
    expect(incremental).toEqual(reduceNodeRunStatus(steps, log))
  })

  it('returns same map reference when status is unchanged', () => {
    const base = applyNodeRunStatusEvent(steps, {}, event('step.started', 'a'))
    const again = applyNodeRunStatusEvent(steps, base, event('step.started', 'a'))
    expect(again).toBe(base)
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
