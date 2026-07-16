import {
  useMemo,
  useCallback,
  useRef,
  useState,
  useEffect,
  type DragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  applyNodeChanges,
  type Edge,
  type IsValidConnection,
  type NodeMouseHandler,
  type OnNodeDrag,
  type OnNodesChange,
  type OnConnect,
  type OnConnectStart,
  type OnConnectEnd,
  type OnSelectionChangeFunc,
  MarkerType,
  ConnectionMode,
  BackgroundVariant,
  ViewportPortal,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { WorkflowNode, WorkflowNodeType } from './types'
import { usePreferences } from '@/app/providers/AppProviders'
import {
  branchHandlesFor,
  defaultDropTarget,
  emptySlotsFor,
  findNode,
  isContainerType,
  isDescendantOf,
  layoutCanvas,
  reparentTargetFromHandle,
  computeSmartSnap,
  resolveNodeCanvasSubtitle,
  executorNamesKey,
  NODE_LAYOUT_WIDTH,
  NODE_LAYOUT_HEIGHT,
  type ReparentTarget,
  type SmartGuideLine,
  isKeyboardTargetEditable,
} from './utils'
import {
  WorkflowFlowNode,
  type WorkflowCanvasNode,
} from './WorkflowFlowNode'

/** Module-scope map (skill gate: stable nodeTypes). */
const nodeTypes = { workflow: WorkflowFlowNode } as const

const PALETTE_MIME = 'application/x-workflow-node'

const NODE_SETTLE_MS = 220

const FIT_VIEW_OPTIONS = { padding: 0.2, duration: NODE_SETTLE_MS, maxZoom: 1.5 } as const

const DEFAULT_EDGE_OPTIONS = {
  type: 'smoothstep' as const,
  style: { strokeWidth: 1.5 },
}

const PRO_OPTIONS = { hideAttribution: true } as const

const MINIMAP_NODE_COLOR = (node: WorkflowCanvasNode) => {
  const status = node.data?.runStatus
  if (status === 'running') return '#1677ff'
  if (status === 'ok') return '#52c41a'
  if (status === 'error') return '#ff4d4f'
  if (status === 'paused') return '#faad14'
  return 'var(--tais-muted, #c0c0c0)'
}

type Props = {
  steps: WorkflowNode[]
  selectedId: string | null
  selectedIds: string[]
  onSelect: (id: string | null, multi?: boolean) => void
  onSelectMany: (ids: string[]) => void
  onPositionsChange: (positions: Record<string, { x: number; y: number }>) => void
  onConnectSequence: (sourceId: string, targetId: string) => void
  onConnectBranch: (sourceId: string, targetId: string, sourceHandle?: string | null) => void
  onDropNode: (
    type: WorkflowNodeType,
    position: { x: number; y: number },
    target?: ReparentTarget | null
  ) => void
  onReparent: (nodeId: string, target: ReparentTarget) => void
  onEmptySlot: (parentId: string, slotKey: string) => void
  onDeleteSelected: () => void
  /** Double-click a node to open/focus the inspector name field. */
  onFocusInspector?: (nodeId: string) => void
  onUndo: () => void
  onRedo: () => void
  onCopy: () => void
  onPaste: () => void
  onOrganize: () => void
  onDuplicateSelected: () => void
  nodeRunStatus?: Record<string, 'running' | 'ok' | 'error' | 'paused'>
  validationIssues?: Array<{ nodeId: string | null; code: string; message: string }>
  validationEpoch?: number
  /** Bumped after load/template so viewport fits all nodes. */
  focusEpoch?: number
  emptyHint?: string
  emptyActionLabel?: string
  onEmptyAction?: () => void
  /** ref → display name for agent step subtitles on the canvas. */
  executorNames?: ReadonlyMap<string, string> | Record<string, string>
}

type FlowGraph = { nodes: WorkflowCanvasNode[]; edges: Edge[] }

type TranslateFn = (key: string, options?: Record<string, unknown>) => string

function buildGraph(
  steps: WorkflowNode[],
  selectedIds: string[],
  prevNodes: WorkflowCanvasNode[],
  animateNew: boolean,
  dropTargetId: string | null,
  onEmptySlot: (parentId: string, slotKey: string) => void,
  nodeRunStatus: Record<string, 'running' | 'ok' | 'error' | 'paused'> = {},
  invalidById: Record<string, string> = {},
  connectTargetId: string | null = null,
  toolbar: {
    onDelete: (id: string) => void
    onCopy: () => void
    onDuplicate: () => void
  } | null = null,
  t: TranslateFn = (key) => key,
  executorNames: ReadonlyMap<string, string> | Record<string, string> = {},
): FlowGraph {
  const layout = layoutCanvas(steps)
  const prevById = new Map(prevNodes.map((item) => [item.id, item]))
  const prevIds = new Set(prevNodes.map((item) => item.id))
  const selected = new Set(selectedIds)

  const flowNodes: WorkflowCanvasNode[] = layout.nodes.map((item) => {
    const source = findNode(steps, item.id)
    const hitl = Boolean(
      source?.requiresConfirmation ||
        source?.requiresUserInput ||
        source?.requiresOutputReview
    )
    const skillCount =
      source?.type === 'step' ? (source.skills ?? []).filter(Boolean).length : 0
    const subtitle = source
      ? resolveNodeCanvasSubtitle(source, t, executorNames)
      : item.type
    const displayLabel =
      source?.name?.trim() ||
      t(`defaultName_${item.type}`) ||
      item.label

    const prev = prevById.get(item.id)
    const isNew = animateNew && !prevIds.has(item.id)
    const emptySlots = source ? emptySlotsFor(source) : []

    return {
      id: item.id,
      type: 'workflow',
      position: { x: item.x, y: item.y },
      data: {
        label: displayLabel,
        nodeType: item.type,
        subtitle,
        hitl,
        skillCount,
        runStatus: nodeRunStatus[item.id] ?? null,
        invalid: Boolean(invalidById[item.id]),
        invalidMessage: invalidById[item.id] ?? null,
        branchHandles: source ? branchHandlesFor(source) : [],
        emptySlots,
        dropHighlight: dropTargetId === item.id,
        connectHighlight: connectTargetId === item.id,
        onEmptySlot: (slotKey: string) => onEmptySlot(item.id, slotKey),
        onToolbarDelete: () => toolbar?.onDelete(item.id),
        onToolbarCopy: () => toolbar?.onCopy(),
        onToolbarDuplicate: () => toolbar?.onDuplicate(),
      },
      selected: selected.has(item.id),
      ...(prev?.measured ? { measured: prev.measured } : {}),
      ...(prev?.width != null ? { width: prev.width } : {}),
      ...(prev?.height != null ? { height: prev.height } : {}),
      className: isNew ? 'wf-node-enter' : undefined,
    }
  })

  const flowEdges: Edge[] = layout.edges.map((edge) => {
    const rawLabel = edge.label || ''
    const isBranch =
      rawLabel === 'then' ||
      rawLabel === 'else' ||
      (edge.sourceHandle != null && edge.sourceHandle.startsWith('choice:'))
    const displayLabel =
      rawLabel === 'next'
        ? t('edgeNext')
        : rawLabel === 'then'
          ? t('edgeThen')
          : rawLabel === 'else'
            ? t('edgeElse')
            : rawLabel || undefined
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle ?? 'in',
      label: displayLabel,
      type: 'smoothstep',
      animated: rawLabel === 'next',
      className: isBranch ? 'wf-edge-branch' : rawLabel === 'next' ? 'wf-edge-next' : undefined,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 18,
        height: 18,
        color: isBranch ? 'var(--wf-edge-branch)' : 'var(--wf-edge-stroke)',
      },
      style: {
        stroke: isBranch ? 'var(--wf-edge-branch)' : 'var(--wf-edge-stroke)',
        strokeWidth: isBranch ? 1.75 : 1.5,
      },
      labelStyle: { fontSize: 10, fill: 'var(--wf-edge-label)', fontWeight: 500 },
      labelBgStyle: { fill: 'var(--wf-edge-label-bg)', fillOpacity: 0.95 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
    }
  })

  return { nodes: flowNodes, edges: flowEdges }
}

function CanvasInner({
  steps,
  selectedId,
  selectedIds,
  onSelect,
  onSelectMany,
  onPositionsChange,
  onConnectSequence,
  onConnectBranch,
  onDropNode,
  onReparent,
  onEmptySlot,
  onDeleteSelected,
  onFocusInspector,
  onUndo,
  onRedo,
  onCopy,
  onPaste,
  onOrganize,
  onDuplicateSelected,
  nodeRunStatus = {},
  validationIssues = [],
  validationEpoch = 0,
  focusEpoch = 0,
  emptyHint,
  emptyActionLabel,
  onEmptyAction,
  executorNames = {},
}: Props) {
  const { t } = useTranslation('workflow')
  const executorCatalogKey = useMemo(() => executorNamesKey(executorNames), [executorNames])
  const executorNamesRef = useRef(executorNames)
  executorNamesRef.current = executorNames
  const wrapperRef = useRef<HTMLDivElement>(null)
  const { dark } = usePreferences()
  const { screenToFlowPosition, fitView, getIntersectingNodes, updateNodeData } = useReactFlow()

  const [graph, setGraph] = useState<FlowGraph>({ nodes: [], edges: [] })
  const graphNodesRef = useRef<WorkflowCanvasNode[]>([])
  graphNodesRef.current = graph.nodes
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)
  const [connectTargetId, setConnectTargetId] = useState<string | null>(null)
  const [smartGuides, setSmartGuides] = useState<SmartGuideLine[]>([])
  const connectingFromRef = useRef<{ nodeId: string; handleId: string | null } | null>(null)
  const nodeRunStatusRef = useRef(nodeRunStatus)
  nodeRunStatusRef.current = nodeRunStatus
  const stepsRef = useRef(steps)
  stepsRef.current = steps
  const selectionRef = useRef({ selectedIds, selectedId })
  selectionRef.current = { selectedIds, selectedId }
  const highlightRef = useRef({ dropTargetId, connectTargetId })
  highlightRef.current = { dropTargetId, connectTargetId }
  const draggingRef = useRef(false)
  const bootstrappedRef = useRef(false)
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const enterTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastFocusKeyRef = useRef('')
  const onEmptySlotRef = useRef(onEmptySlot)
  onEmptySlotRef.current = onEmptySlot
  const onDeleteRef = useRef(onDeleteSelected)
  onDeleteRef.current = onDeleteSelected
  const onCopyRef = useRef(onCopy)
  onCopyRef.current = onCopy
  const onDupRef = useRef(onDuplicateSelected)
  onDupRef.current = onDuplicateSelected

  // Topology: ids/types/nesting/positions — full layout rebuild.
  const topologyKey = useMemo(
    () =>
      steps
        .map((node) => {
          const kids =
            node.type === 'condition'
              ? `${(node.thenSteps ?? []).map((c) => c.id).join(',')}|${(node.elseSteps ?? []).map((c) => c.id).join(',')}`
              : node.type === 'router'
                ? (node.choices ?? [])
                    .map((c) => `${c.id}:${c.steps.map((s) => s.id).join(',')}`)
                    .join(';')
                : (node.steps ?? []).map((c) => c.id).join(',')
          const pos = node.position
            ? `${Math.round(node.position.x)},${Math.round(node.position.y)}`
            : '-'
          return `${node.id}:${node.type}:${pos}:${kids}`
        })
        .join('#'),
    [steps]
  )

  // Presentation: labels / subtitles / HITL flags — data patch only.
  const contentKey = useMemo(
    () =>
      steps
        .map((node) => {
          const hitl = Boolean(
            node.requiresConfirmation || node.requiresUserInput || node.requiresOutputReview
          )
          const skillCount =
            node.type === 'step' ? (node.skills ?? []).filter(Boolean).length : 0
          const subtitle = resolveNodeCanvasSubtitle(node, t, executorNames)
          const branches =
            node.type === 'router'
              ? (node.choices ?? []).map((c) => `${c.id}:${c.name}`).join(',')
              : ''
          return `${node.id}:${node.name ?? ''}:${subtitle}:${hitl ? 1 : 0}:${skillCount}:${branches}`
        })
        .join('#') + `@${executorCatalogKey}`,
    [steps, t, executorNames, executorCatalogKey]
  )

  const selectionKey = selectedIds.length
    ? selectedIds.join(',')
    : selectedId ?? ''

  const invalidById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const issue of validationIssues) {
      if (issue.nodeId && !map[issue.nodeId]) map[issue.nodeId] = issue.message
    }
    return map
  }, [validationIssues])

  const invalidKey = useMemo(() => Object.keys(invalidById).sort().join(','), [invalidById])

  useEffect(() => {
    if (draggingRef.current) return
    const liveSteps = stepsRef.current
    const { selectedIds: selIds, selectedId: selId } = selectionRef.current
    const effectiveSelectedIds = selIds.length ? selIds : selId ? [selId] : []
    const { dropTargetId: dropId, connectTargetId: connectId } = highlightRef.current
    setGraph((prev) => {
      const animateNew = bootstrappedRef.current
      const next = buildGraph(
        liveSteps,
        // selection applied via post-pass / selection effect (avoids layout on click).
        effectiveSelectedIds,
        prev.nodes,
        animateNew,
        null,
        (parentId, slotKey) => onEmptySlotRef.current(parentId, slotKey),
        {},
        invalidById,
        null,
        {
          onDelete: () => onDeleteRef.current(),
          onCopy: () => onCopyRef.current(),
          onDuplicate: () => onDupRef.current(),
        },
        t,
        executorNamesRef.current,
      )
      // Preserve runStatus + apply current selection/highlights (refs, not deps).
      const prevStatus = new Map(
        prev.nodes.map((n) => [n.id, n.data.runStatus ?? null])
      )
      const liveStatus = nodeRunStatusRef.current
      const selectedSet = new Set(effectiveSelectedIds)
      next.nodes = next.nodes.map((n) => {
        const status = liveStatus[n.id] ?? prevStatus.get(n.id) ?? null
        return {
          ...n,
          selected: selectedSet.has(n.id),
          data: {
            ...n.data,
            runStatus: status,
            dropHighlight: dropId === n.id,
            connectHighlight: connectId === n.id,
          },
        }
      })
      bootstrappedRef.current = true
      return next
    })
  }, [topologyKey, invalidById, invalidKey, t])

  // Selection only: patch `selected` without layoutCanvas / edge rebuild.
  useEffect(() => {
    const selectedSet = new Set(
      selectedIds.length ? selectedIds : selectedId ? [selectedId] : []
    )
    setGraph((current) => {
      if (!current.nodes.length) return current
      let changed = false
      const nodes = current.nodes.map((node) => {
        const nextSelected = selectedSet.has(node.id)
        if (node.selected === nextSelected) return node
        changed = true
        return { ...node, selected: nextSelected }
      })
      return changed ? { ...current, nodes } : current
    })
  }, [selectionKey, selectedIds, selectedId])

  // Drop / connect highlight: patch node data flags only.
  useEffect(() => {
    setGraph((current) => {
      if (!current.nodes.length) return current
      let changed = false
      const nodes = current.nodes.map((node) => {
        const dropHighlight = dropTargetId === node.id
        const connectHighlight = connectTargetId === node.id
        if (
          Boolean(node.data.dropHighlight) === dropHighlight &&
          Boolean(node.data.connectHighlight) === connectHighlight
        ) {
          return node
        }
        changed = true
        return {
          ...node,
          data: { ...node.data, dropHighlight, connectHighlight },
        }
      })
      return changed ? { ...current, nodes } : current
    })
  }, [dropTargetId, connectTargetId])

  // Presentation-only edits (rename / CEL / executor): patch node data, keep positions.
  useEffect(() => {
    if (draggingRef.current) return
    if (!bootstrappedRef.current) return
    const liveSteps = stepsRef.current
    setGraph((current) => {
      if (!current.nodes.length) return current
      let changed = false
      const nodes = current.nodes.map((node) => {
        const source = findNode(liveSteps, node.id)
        if (!source) return node
        const hitl = Boolean(
          source.requiresConfirmation ||
            source.requiresUserInput ||
            source.requiresOutputReview
        )
        const skillCount =
          source.type === 'step' ? (source.skills ?? []).filter(Boolean).length : 0
        const subtitle = resolveNodeCanvasSubtitle(source, t, executorNames)
        const label =
          source.name?.trim() ||
          t(`defaultName_${source.type}`) ||
          subtitle
        const branchHandles = branchHandlesFor(source)
        const data = node.data
        if (
          data.label === label &&
          data.subtitle === subtitle &&
          data.hitl === hitl &&
          (data.skillCount ?? 0) === skillCount
        ) {
          return node
        }
        changed = true
        const nextData = {
          ...data,
          label,
          subtitle,
          hitl,
          skillCount,
          branchHandles,
        }
        return { ...node, data: nextData }
      })
      return changed ? { ...current, nodes } : current
    })
  }, [contentKey, t, executorNames])

  // Run status: only patch nodes whose status actually changed (no layout).
  const prevRunStatusRef = useRef(nodeRunStatus)
  useEffect(() => {
    const live = nodeRunStatus
    const prevLive = prevRunStatusRef.current
    prevRunStatusRef.current = live

    const changedIds = new Set<string>()
    for (const id of new Set([...Object.keys(prevLive), ...Object.keys(live)])) {
      if ((prevLive[id] ?? null) !== (live[id] ?? null)) changedIds.add(id)
    }
    if (!changedIds.size) return

    for (const id of changedIds) {
      updateNodeData(id, { runStatus: live[id] ?? null })
    }

    setGraph((current) => {
      if (!current.nodes.length) return current
      let changed = false
      const nodes = current.nodes.map((node) => {
        if (!changedIds.has(node.id)) return node
        const nextStatus = live[node.id] ?? null
        const prevStatus = node.data.runStatus ?? null
        if (nextStatus === prevStatus) return node
        changed = true
        return {
          ...node,
          data: { ...node.data, runStatus: nextStatus },
        }
      })
      return changed ? { ...current, nodes } : current
    })
  }, [nodeRunStatus, updateNodeData])

  // Focus viewport on running / paused nodes during a run.
  useEffect(() => {
    const focusIds = Object.entries(nodeRunStatus)
      .filter(([, status]) => status === 'running' || status === 'paused')
      .map(([id]) => id)
    const key = `run:${focusIds.slice().sort().join(',')}`
    if (key === 'run:' || key === lastFocusKeyRef.current) return
    lastFocusKeyRef.current = key
    requestAnimationFrame(() => {
      void fitView({
        nodes: focusIds.map((id) => ({ id })),
        padding: 0.35,
        duration: 320,
        maxZoom: 1.25,
      })
    })
  }, [nodeRunStatus, fitView])

  // Focus invalid nodes when save validation fails (or when user re-triggers).
  useEffect(() => {
    const focusIds = Object.keys(invalidById)
    const key = `invalid:${validationEpoch}:${focusIds.slice().sort().join(',')}`
    if (key === 'invalid:' || key === lastFocusKeyRef.current) return
    lastFocusKeyRef.current = key
    requestAnimationFrame(() => {
      void fitView({
        nodes: focusIds.map((id) => ({ id })),
        padding: 0.4,
        duration: 280,
        maxZoom: 1.35,
      })
    })
  }, [invalidKey, invalidById, validationEpoch, fitView])

  // When selecting a single invalid node from the validation list, center it.
  useEffect(() => {
    if (!selectedId || !invalidById[selectedId]) return
    if (selectedIds.length > 1) return
    const key = `select-invalid:${validationEpoch}:${selectedId}`
    if (key === lastFocusKeyRef.current) return
    lastFocusKeyRef.current = key
    requestAnimationFrame(() => {
      void fitView({
        nodes: [{ id: selectedId }],
        padding: 0.45,
        duration: 240,
        maxZoom: 1.4,
      })
    })
  }, [selectedId, selectedIds, invalidById, validationEpoch, fitView])

  // Fit whole graph after load / template apply.
  useEffect(() => {
    if (!focusEpoch || !steps.length) return
    const key = `focus:${focusEpoch}`
    if (key === lastFocusKeyRef.current) return
    lastFocusKeyRef.current = key
    requestAnimationFrame(() => {
      void fitView({ padding: 0.22, duration: 280, maxZoom: 1.15 })
    })
  }, [focusEpoch, steps.length, fitView])

  useEffect(() => {
    if (!graph.nodes.some((node) => node.className?.includes('wf-node-enter'))) return
    if (enterTimerRef.current) clearTimeout(enterTimerRef.current)
    enterTimerRef.current = setTimeout(() => {
      setGraph((current) => ({
        ...current,
        nodes: current.nodes.map((node) =>
          node.className?.includes('wf-node-enter')
            ? { ...node, className: undefined }
            : node
        ),
      }))
      enterTimerRef.current = null
    }, 320)
    return () => {
      if (enterTimerRef.current) clearTimeout(enterTimerRef.current)
    }
  }, [graph.nodes])

  useEffect(
    () => () => {
      if (settleTimerRef.current) clearTimeout(settleTimerRef.current)
      if (enterTimerRef.current) clearTimeout(enterTimerRef.current)
    },
    []
  )

  const onNodesChange: OnNodesChange<WorkflowCanvasNode> = useCallback((changes) => {
    setGraph((current) => {
      let nextChanges = changes
      if (draggingRef.current) {
        const active = changes.find(
          (change) =>
            change.type === 'position' &&
            change.dragging === true &&
            change.position != null
        )
        if (active && active.type === 'position' && active.position) {
          const node = current.nodes.find((item) => item.id === active.id)
          if (node) {
            const width = node.measured?.width ?? node.width ?? NODE_LAYOUT_WIDTH
            const height = node.measured?.height ?? node.height ?? NODE_LAYOUT_HEIGHT
            const peers = current.nodes
              .filter((item) => item.id !== active.id)
              .map((item) => ({
                x: item.position.x,
                y: item.position.y,
                width: item.measured?.width ?? item.width ?? NODE_LAYOUT_WIDTH,
                height: item.measured?.height ?? item.height ?? NODE_LAYOUT_HEIGHT,
              }))
            const snapped = computeSmartSnap(
              {
                x: active.position.x,
                y: active.position.y,
                width,
                height,
              },
              peers
            )
            // Defer guide paint; avoid setState during setState.
            queueMicrotask(() => {
              setSmartGuides((prev) => {
                const next = snapped.guides
                if (
                  prev.length === next.length &&
                  prev.every(
                    (g, i) =>
                      g.orientation === next[i]?.orientation &&
                      g.pos === next[i]?.pos &&
                      g.start === next[i]?.start &&
                      g.end === next[i]?.end
                  )
                ) {
                  return prev
                }
                return next
              })
            })
            nextChanges = changes.map((change) => {
              if (
                change.type === 'position' &&
                change.id === active.id &&
                change.position
              ) {
                return {
                  ...change,
                  position: { x: snapped.x, y: snapped.y },
                }
              }
              return change
            })
          }
        }
      }
      return {
        ...current,
        nodes: applyNodeChanges(nextChanges, current.nodes),
      }
    })
  }, [])

  const onNodeClick: NodeMouseHandler = useCallback(
    (event, node) => {
      onSelect(node.id, event.shiftKey || event.metaKey || event.ctrlKey)
    },
    [onSelect]
  )

  const onNodeDoubleClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onSelect(node.id, false)
      onFocusInspector?.(node.id)
    },
    [onSelect, onFocusInspector]
  )

  const onPaneClick = useCallback(() => onSelect(null), [onSelect])

  const onSelectionChange: OnSelectionChangeFunc = useCallback(
    ({ nodes: selectedNodes }) => {
      if (draggingRef.current) return
      // RF box-select / multi-select
      if (selectedNodes.length > 1) {
        onSelectMany(selectedNodes.map((n) => n.id))
      }
    },
    [onSelectMany]
  )

  const resolveContainerTarget = useCallback(
    (nodeId: string, candidateId: string): ReparentTarget | null => {
      if (candidateId === nodeId) return null
      if (isDescendantOf(steps, nodeId, candidateId)) return null
      const container = findNode(steps, candidateId)
      if (!container || !isContainerType(container.type)) return null
      return defaultDropTarget(container)
    },
    [steps]
  )

  const onNodeDragStart: OnNodeDrag = useCallback(() => {
    draggingRef.current = true
    setSmartGuides([])
    wrapperRef.current?.classList.add('is-dragging-node')
    if (settleTimerRef.current) {
      clearTimeout(settleTimerRef.current)
      settleTimerRef.current = null
    }
  }, [])

  const onNodeDrag: OnNodeDrag = useCallback(
    (_event, node) => {
      // Container reparent highlight; smart snap lives in onNodesChange.
      const hits = getIntersectingNodes(node).filter((item) => item.id !== node.id)
      let nextTarget: string | null = null
      for (const hit of hits) {
        const target = resolveContainerTarget(node.id, hit.id)
        if (target) {
          nextTarget = hit.id
          break
        }
      }
      setDropTargetId((current) => (current === nextTarget ? current : nextTarget))
    },
    [getIntersectingNodes, resolveContainerTarget]
  )

  const onNodeDragStop: OnNodeDrag = useCallback(
    (_event, node, allNodes) => {
      draggingRef.current = false
      const targetId = dropTargetId
      setDropTargetId(null)
      setSmartGuides([])

      if (targetId) {
        const target = resolveContainerTarget(node.id, targetId)
        if (target) {
          onReparent(node.id, target)
          settleTimerRef.current = setTimeout(() => {
            wrapperRef.current?.classList.remove('is-dragging-node')
            settleTimerRef.current = null
          }, NODE_SETTLE_MS + 40)
          return
        }
      }

      // Prefer graph nodes (include smart-snap) and fall back to RF callback nodes.
      const positions: Record<string, { x: number; y: number }> = {}
      for (const item of allNodes) {
        positions[item.id] = { x: item.position.x, y: item.position.y }
      }
      for (const item of graphNodesRef.current) {
        positions[item.id] = { x: item.position.x, y: item.position.y }
      }
      onPositionsChange(positions)
      settleTimerRef.current = setTimeout(() => {
        wrapperRef.current?.classList.remove('is-dragging-node')
        settleTimerRef.current = null
      }, NODE_SETTLE_MS + 40)
    },
    [dropTargetId, onPositionsChange, onReparent, resolveContainerTarget]
  )

  const onConnectStart: OnConnectStart = useCallback((_event, params) => {
    connectingFromRef.current = {
      nodeId: params.nodeId ?? '',
      handleId: params.handleId ?? null,
    }
  }, [])

  const onConnectEnd: OnConnectEnd = useCallback(() => {
    connectingFromRef.current = null
    setConnectTargetId(null)
  }, [])

  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (!connection.source || !connection.target || connection.source === connection.target) {
        return
      }
      const sourceNode = findNode(steps, connection.source)
      if (sourceNode && isContainerType(sourceNode.type)) {
        const branchTarget = reparentTargetFromHandle(sourceNode, connection.sourceHandle)
        if (branchTarget) {
          onConnectBranch(connection.source, connection.target, connection.sourceHandle)
          connectingFromRef.current = null
          setConnectTargetId(null)
          return
        }
      }
      onConnectSequence(connection.source, connection.target)
      connectingFromRef.current = null
      setConnectTargetId(null)
    },
    [onConnectBranch, onConnectSequence, steps]
  )

  const onNodeMouseEnter: NodeMouseHandler = useCallback(
    (_event, node) => {
      if (!connectingFromRef.current?.nodeId) return
      if (node.id === connectingFromRef.current.nodeId) return
      setConnectTargetId(node.id)
    },
    []
  )

  const onNodeMouseLeave: NodeMouseHandler = useCallback(() => {
    if (!connectingFromRef.current?.nodeId) return
    setConnectTargetId(null)
  }, [])

  const isValidConnection = useCallback<IsValidConnection<Edge>>(
    (connection) => {
      const source = connection.source
      const target = connection.target
      if (!source || !target) return false
      if (source === target) return false
      // Prevent nesting a node under its own descendant via edge.
      if (isDescendantOf(steps, target, source)) return false
      // Only accept known target handles when specified.
      const th = connection.targetHandle
      if (th && th !== 'in' && th !== 'in-left') return false
      const sourceNode = findNode(steps, source)
      if (sourceNode && isContainerType(sourceNode.type)) {
        // Container sources must use a branch handle (not a bare out for condition/router).
        if (sourceNode.type === 'condition' || sourceNode.type === 'router') {
          const handle = connection.sourceHandle || ''
          if (!handle || handle === 'out' || handle === 'out-right') return false
          return reparentTargetFromHandle(sourceNode, handle) != null
        }
      }
      return true
    },
    [steps]
  )

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const findContainerAtPoint = useCallback(
    (flowPos: { x: number; y: number }): { id: string; target: ReparentTarget } | null => {
      // Hit-test nodes by position/size (last drawn = top-most preference reversed: prefer deepest)
      const candidates: Array<{ id: string; target: ReparentTarget; area: number }> = []
      for (const node of graph.nodes) {
        const width = node.measured?.width ?? node.width ?? 200
        const height = node.measured?.height ?? node.height ?? 88
        const x = node.position.x
        const y = node.position.y
        if (
          flowPos.x >= x &&
          flowPos.x <= x + width &&
          flowPos.y >= y &&
          flowPos.y <= y + height
        ) {
          const source = findNode(steps, node.id)
          if (!source || !isContainerType(source.type)) continue
          const target = defaultDropTarget(source)
          if (!target) continue
          candidates.push({ id: node.id, target, area: width * height })
        }
      }
      if (!candidates.length) return null
      // Prefer smaller (deeper) containers
      candidates.sort((a, b) => a.area - b.area)
      return candidates[0] ?? null
    },
    [graph.nodes, steps]
  )

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault()
      const type = event.dataTransfer.getData(PALETTE_MIME) as WorkflowNodeType
      if (!type) return
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      const hit = findContainerAtPoint(position)
      onDropNode(type, position, hit?.target ?? null)
      // Only nudge viewport when dropping into empty canvas (first node).
      if (!stepsRef.current.length) {
        requestAnimationFrame(() => void fitView({ ...FIT_VIEW_OPTIONS }))
      }
    },
    [screenToFlowPosition, onDropNode, fitView, findContainerAtPoint]
  )

  const onKeyDown = useCallback(
    (event: KeyboardEvent | ReactKeyboardEvent<HTMLDivElement>) => {
      const mod = event.metaKey || event.ctrlKey
      if (mod && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault()
        onUndo()
        return
      }
      if (mod && (event.key.toLowerCase() === 'y' || (event.key.toLowerCase() === 'z' && event.shiftKey))) {
        event.preventDefault()
        onRedo()
        return
      }
      if (mod && event.key.toLowerCase() === 'c') {
        event.preventDefault()
        onCopy()
        return
      }
      if (mod && event.key.toLowerCase() === 'v') {
        event.preventDefault()
        onPaste()
        return
      }
      if (mod && event.key.toLowerCase() === 'a') {
        event.preventDefault()
        onSelectMany(steps.map((n) => n.id))
        return
      }
      if (mod && event.key.toLowerCase() === 'l') {
        event.preventDefault()
        onOrganize()
        return
      }
      if (event.key === 'Escape') {
        if (selectedIds.length || selectedId) {
          event.preventDefault()
          onSelectMany([])
        }
        return
      }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        if (!(selectedIds.length || selectedId)) return
        event.preventDefault()
        onDeleteSelected()
      }
    },
    [onUndo, onRedo, onCopy, onPaste, onSelectMany, onOrganize, onDeleteSelected, steps, selectedIds, selectedId]
  )

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (isKeyboardTargetEditable(event.target)) {
        return
      }
      const root = wrapperRef.current
      if (!root) return
      const active = document.activeElement
      if (
        active &&
        active !== document.body &&
        active !== root &&
        !root.contains(active)
      ) {
        return
      }
      onKeyDown(event as unknown as ReactKeyboardEvent<HTMLDivElement>)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onKeyDown])

  return (
    <div
      ref={wrapperRef}
      className={`workflow-canvas workflow-canvas--main ${steps.length ? '' : 'is-empty'}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
    >
      <ReactFlow<WorkflowCanvasNode, Edge>
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onPaneClick={onPaneClick}
        onSelectionChange={onSelectionChange}
        onNodeDragStart={onNodeDragStart}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        onConnect={onConnect}
        onConnectStart={onConnectStart}
        onConnectEnd={onConnectEnd}
        isValidConnection={isValidConnection}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        nodesDraggable
        nodesConnectable
        elementsSelectable
        selectNodesOnDrag={false}
        selectionOnDrag
        multiSelectionKeyCode="Shift"
        panOnScroll
        zoomOnDoubleClick={false}
        elevateNodesOnSelect
        onlyRenderVisibleElements
        connectionMode={ConnectionMode.Loose}
        colorMode={dark ? 'dark' : 'light'}
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        defaultMarkerColor="var(--wf-edge-stroke)"
        minZoom={0.2}
        maxZoom={1.75}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        proOptions={PRO_OPTIONS}
        deleteKeyCode={null}
      >
        {smartGuides.length ? (
          <ViewportPortal>
            <div className="wf-smart-guides" aria-hidden>
              {smartGuides.map((guide, index) =>
                guide.orientation === 'v' ? (
                  <div
                    key={`v-${guide.pos}-${index}`}
                    className="wf-smart-guide wf-smart-guide--v"
                    style={{
                      left: guide.pos,
                      top: guide.start,
                      height: Math.max(1, guide.end - guide.start),
                    }}
                  />
                ) : (
                  <div
                    key={`h-${guide.pos}-${index}`}
                    className="wf-smart-guide wf-smart-guide--h"
                    style={{
                      top: guide.pos,
                      left: guide.start,
                      width: Math.max(1, guide.end - guide.start),
                    }}
                  />
                )
              )}
            </div>
          </ViewportPortal>
        ) : null}
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1.2}
          color="var(--wf-canvas-dot)"
        />
        <MiniMap
          pannable
          zoomable
          nodeStrokeWidth={2}
          className="wf-minimap"
          nodeColor={MINIMAP_NODE_COLOR}
        />
        <Controls
          showInteractive={false}
          showFitView
          showZoom
          className="wf-controls"
        />
      </ReactFlow>
      {!steps.length ? (
        <div className="workflow-canvas__empty-overlay">
          <div className="workflow-canvas__empty-card">
            <strong>{emptyHint || t('canvasEmptyHint')}</strong>
            <span>{t('canvasEmptyDrop')}</span>
            {emptyActionLabel && onEmptyAction ? (
              <button
                type="button"
                className="workflow-canvas__empty-action"
                onClick={(event) => {
                  event.stopPropagation()
                  onEmptyAction()
                }}
              >
                {emptyActionLabel}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function WorkflowCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  )
}

export function paletteDragStart(event: DragEvent, type: WorkflowNodeType) {
  event.dataTransfer.setData(PALETTE_MIME, type)
  event.dataTransfer.effectAllowed = 'copy'
}

