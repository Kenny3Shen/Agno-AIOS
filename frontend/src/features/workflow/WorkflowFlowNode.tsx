import { memo, type CSSProperties, type MouseEvent } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { WorkflowNodeRunStatus, WorkflowNodeType } from './types'
import type { EmptySlot } from './utils'

export type WorkflowFlowNodeData = {
  label: string
  nodeType: WorkflowNodeType
  subtitle?: string
  hitl?: boolean
  runStatus?: WorkflowNodeRunStatus | null
  emptySlots?: EmptySlot[]
  dropHighlight?: boolean
  onEmptySlot?: (slotKey: string) => void
}

const TYPE_META: Record<
  WorkflowNodeType,
  { color: string; bg: string; icon: string }
> = {
  step: { color: '#1677ff', bg: 'rgba(22,119,255,0.08)', icon: 'A' },
  parallel: { color: '#722ed1', bg: 'rgba(114,46,209,0.08)', icon: 'P' },
  condition: { color: '#d48806', bg: 'rgba(250,173,20,0.12)', icon: 'C' },
  loop: { color: '#08979c', bg: 'rgba(19,194,194,0.12)', icon: 'L' },
  router: { color: '#c41d7f', bg: 'rgba(235,47,150,0.1)', icon: 'R' },
  workflow_ref: { color: '#389e0d', bg: 'rgba(82,196,26,0.1)', icon: 'W' },
}

const RUN_LABEL: Record<WorkflowNodeRunStatus, string> = {
  running: 'RUNNING',
  ok: 'OK',
  error: 'ERROR',
  paused: 'PAUSED',
}

function WorkflowFlowNodeComponent({ data, selected }: NodeProps) {
  const payload = data as unknown as WorkflowFlowNodeData
  const meta = TYPE_META[payload.nodeType] ?? TYPE_META.step
  const style = {
    '--wf-node-color': meta.color,
    '--wf-node-bg': meta.bg,
  } as CSSProperties
  const runClass = payload.runStatus ? `is-run-${payload.runStatus}` : ''

  const onSlotClick = (event: MouseEvent, key: string) => {
    event.stopPropagation()
    event.preventDefault()
    payload.onEmptySlot?.(key)
  }

  return (
    <div
      className={`wf-flow-node ${selected ? 'is-selected' : ''} ${payload.dropHighlight ? 'is-drop-target' : ''} ${runClass}`}
      style={style}
    >
      <Handle type="target" position={Position.Top} className="wf-handle" />
      <div className="wf-flow-node__badge" aria-hidden>
        {meta.icon}
        {payload.runStatus ? (
          <span className={`wf-flow-node__run-pill is-${payload.runStatus}`}>
            {RUN_LABEL[payload.runStatus]}
          </span>
        ) : null}
      </div>
      <div className="wf-flow-node__body">
        <div className="wf-flow-node__type">{payload.nodeType}</div>
        <div className="wf-flow-node__title">{payload.label}</div>
        {payload.subtitle ? <div className="wf-flow-node__sub">{payload.subtitle}</div> : null}
        {payload.hitl ? <div className="wf-flow-node__hitl">HITL</div> : null}
        {payload.emptySlots?.length ? (
          <div className="wf-flow-node__slots">
            {payload.emptySlots.map((slot) => (
              <button
                key={slot.key}
                type="button"
                className="wf-flow-node__cta nodrag nopan"
                onClick={(event) => onSlotClick(event, slot.key)}
              >
                + {slot.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <Handle type="source" position={Position.Bottom} className="wf-handle" />
    </div>
  )
}

export const WorkflowFlowNode = memo(WorkflowFlowNodeComponent)
