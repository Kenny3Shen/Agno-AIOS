/**
 * Custom React Flow node for Workflow Studio.
 *
 * Presentation only: handles, NodeToolbar, run-status pills, empty-slot CTAs.
 * Mutation callbacks are injected via `data` from `WorkflowCanvas` graph build.
 * Keep styling here; graph topology and drag rules live in the canvas/utils layer.
 */
import { memo, type CSSProperties, type MouseEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Handle,
  NodeToolbar,
  Position,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import type { WorkflowNodeRunStatus, WorkflowNodeType } from './types'
import type { EmptySlot } from './utils'

type BranchHandle = {
  id: string
  label: string
}

type WorkflowFlowNodeData = {
  label: string
  nodeType: WorkflowNodeType
  subtitle?: string
  hitl?: boolean
  /** Bound skill count for agent steps (0 hides badge). */
  skillCount?: number
  runStatus?: WorkflowNodeRunStatus | null
  invalid?: boolean
  invalidMessage?: string | null
  /** Outgoing branch handles (condition/router/parallel). */
  branchHandles?: BranchHandle[]
  emptySlots?: EmptySlot[]
  dropHighlight?: boolean
  connectHighlight?: boolean
  onEmptySlot?: (slotKey: string) => void
  onToolbarDelete?: () => void
  onToolbarCopy?: () => void
  onToolbarDuplicate?: () => void
  /** When true, hide mutation toolbar + empty-slot CTAs (Studio run active). */
  structureLocked?: boolean
}

/** Typed React Flow node for Studio (skill: Node<data, type>). */
export type WorkflowCanvasNode = Node<WorkflowFlowNodeData, 'workflow'>

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

function handleLeftPercent(index: number, total: number): string {
  if (total <= 1) return '50%'
  return `${((index + 1) / (total + 1)) * 100}%`
}

function handleTopPercent(index: number, total: number): string {
  if (total <= 1) return '62%'
  const start = 38
  const end = 88
  return `${start + ((end - start) * index) / (total - 1)}%`
}

const BRANCH_I18N_KEYS = new Set(['branchThen', 'branchElse', 'branchBody', 'branchOut', 'branchNext', 'defaultPathName'])

function WorkflowFlowNodeComponent({
  data,
  selected,
  isConnectable,
}: NodeProps<WorkflowCanvasNode>) {
  const { t } = useTranslation('workflow')
  const payload = data
  const meta = TYPE_META[payload.nodeType] ?? TYPE_META.step
  const style = {
    '--wf-node-color': meta.color,
    '--wf-node-bg': meta.bg,
  } as CSSProperties
  const runClass = payload.runStatus ? `is-run-${payload.runStatus}` : ''
  const runLabelKey =
    payload.runStatus === 'running'
      ? 'runStatusRunning'
      : payload.runStatus === 'ok'
        ? 'runStatusOk'
        : payload.runStatus === 'error'
          ? 'runStatusError'
          : payload.runStatus === 'paused'
            ? 'runStatusPaused'
            : null
  const runLabel = runLabelKey ? t(runLabelKey) : null
  const typeLabel = t(`nodeType_${payload.nodeType}`)
  const branches = payload.branchHandles ?? []
  const multiOut = branches.length > 0
  const branchLabel = (label: string) => (BRANCH_I18N_KEYS.has(label) ? t(label) : label)
  const slotLabel = (slot: EmptySlot) =>
    slot.labelParams ? t(slot.labelKey, slot.labelParams) : t(slot.labelKey)

  const onSlotClick = (event: MouseEvent, key: string) => {
    event.stopPropagation()
    event.preventDefault()
    if (payload.structureLocked) return
    payload.onEmptySlot?.(key)
  }

  return (
    <div
      className={`wf-flow-node ${selected ? 'is-selected' : ''} ${payload.dropHighlight ? 'is-drop-target' : ''} ${payload.connectHighlight ? 'is-connect-target' : ''} ${payload.invalid ? 'is-invalid' : ''} ${runClass} ${multiOut ? 'has-branch-handles' : ''}`}
      style={style}
      title={payload.invalidMessage || undefined}
    >
      <NodeToolbar
        isVisible={selected && !payload.structureLocked}
        position={Position.Top}
        offset={10}
        className="wf-node-toolbar nodrag nopan"
      >
        <button
          type="button"
          className="wf-node-toolbar__btn nodrag nopan"
          onClick={(e) => {
            e.stopPropagation()
            payload.onToolbarCopy?.()
          }}
          title={t('toolbarCopy')}
        >
          {t('toolbarCopy')}
        </button>
        <button
          type="button"
          className="wf-node-toolbar__btn nodrag nopan"
          onClick={(e) => {
            e.stopPropagation()
            payload.onToolbarDuplicate?.()
          }}
          title={t('toolbarDuplicate')}
        >
          {t('toolbarDup')}
        </button>
        <button
          type="button"
          className="wf-node-toolbar__btn wf-node-toolbar__btn--danger nodrag nopan"
          onClick={(e) => {
            e.stopPropagation()
            payload.onToolbarDelete?.()
          }}
          title={t('toolbarDelete')}
        >
          {t('toolbarDel')}
        </button>
      </NodeToolbar>

      <Handle
        type="target"
        position={Position.Top}
        id="in"
        isConnectable={isConnectable}
        className="wf-handle wf-handle--in wf-handle--top"
        title={t('handleInTop')}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="in-left"
        isConnectable={isConnectable}
        className="wf-handle wf-handle--in wf-handle--left"
        title={t('handleInLeft')}
      />

      <div className="wf-flow-node__badge" aria-hidden>
        {meta.icon}
        {payload.invalid ? <span className="wf-flow-node__invalid-pill">!</span> : null}
        {payload.runStatus && runLabel ? (
          <span className={`wf-flow-node__run-pill is-${payload.runStatus}`}>
            {runLabel}
          </span>
        ) : null}
      </div>
      <div className="wf-flow-node__body">
        <div className="wf-flow-node__type">{typeLabel}</div>
        <div className="wf-flow-node__title">{payload.label}</div>
        {payload.subtitle ? <div className="wf-flow-node__sub">{payload.subtitle}</div> : null}
        {payload.hitl ? <div className="wf-flow-node__hitl">{t('hitlBadge')}</div> : null}
        {payload.skillCount && payload.skillCount > 0 ? (
          <div className="wf-flow-node__skills">{t('skillsBadge', { count: payload.skillCount })}</div>
        ) : null}
        {payload.invalid && payload.invalidMessage ? (
          <div className="wf-flow-node__error">{payload.invalidMessage}</div>
        ) : null}
        {payload.emptySlots?.length && !payload.structureLocked ? (
          <div className="wf-flow-node__slots">
            {payload.emptySlots.map((slot) => (
              <button
                key={slot.key}
                type="button"
                className="wf-flow-node__cta nodrag nopan"
                onClick={(event) => onSlotClick(event, slot.key)}
              >
                + {slotLabel(slot)}
              </button>
            ))}
          </div>
        ) : null}
        {multiOut ? (
          <div className="wf-flow-node__branch-labels" aria-hidden>
            {branches.map((branch) => (
              <span key={branch.id} className="wf-flow-node__branch-label">
                {branchLabel(branch.label)}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {multiOut ? (
        <>
          {branches.map((branch, index) => (
            <Handle
              key={`b-${branch.id}`}
              type="source"
              position={Position.Bottom}
              id={branch.id}
              isConnectable={isConnectable}
              className="wf-handle wf-handle--branch wf-handle--bottom"
              style={{ left: handleLeftPercent(index, branches.length) }}
              title={t('handleBranchBottom', { label: branchLabel(branch.label) })}
            />
          ))}
          {branches.map((branch, index) => (
            <Handle
              key={`r-${branch.id}`}
              type="source"
              position={Position.Right}
              id={`${branch.id}-right`}
              isConnectable={isConnectable}
              className="wf-handle wf-handle--branch wf-handle--right"
              style={{ top: handleTopPercent(index, branches.length) }}
              title={t('handleBranchRight', { label: branchLabel(branch.label) })}
            />
          ))}
        </>
      ) : (
        <>
          <Handle
            type="source"
            position={Position.Bottom}
            id="out"
            isConnectable={isConnectable}
            className="wf-handle wf-handle--out wf-handle--bottom"
            title={t('handleOutBottom')}
          />
          <Handle
            type="source"
            position={Position.Right}
            id="out-right"
            isConnectable={isConnectable}
            className="wf-handle wf-handle--out wf-handle--right"
            title={t('handleOutRight')}
          />
        </>
      )}
    </div>
  )
}

export const WorkflowFlowNode = memo(WorkflowFlowNodeComponent)
