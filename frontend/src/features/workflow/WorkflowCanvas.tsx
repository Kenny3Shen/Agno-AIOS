import {
  useMemo,
  useCallback,
  useRef,
  useState,
  useEffect,
  type DragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  applyNodeChanges,
  type Node,
  type Edge,
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
  type ReparentTarget,
} from './utils'
import { WorkflowFlowNode } from './WorkflowFlowNode'

const nodeTypes = { workflow: WorkflowFlowNode }

const PALETTE_MIME = 'application/x-workflow-node'

const NODE_SETTLE_MS = 220

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
  onUndo: () => void
  onRedo: () => void
  onCopy: () => void
  onPaste: () => void
  onOrganize: () => void
  onDuplicateSelected: () => void
  nodeRunStatus?: Record<string, 'running' | 'ok' | 'error' | 'paused'>
  validationIssues?: Array<{ nodeId: string | null; code: string; message: string }>
  emptyHint?: string
}

type FlowGraph = { nodes: Node[]; edges: Edge[] }

function buildGraph(
  steps: WorkflowNode[],
  selectedIds: string[],
  prevNodes: Node[],
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
  } | null = null
): FlowGraph {
  const layout = layoutCanvas(steps)
  const prevById = new Map(prevNodes.map((item) => [item.id, item]))
  const prevIds = new Set(prevNodes.map((item) => item.id))
  const selected = new Set(selectedIds)

  const flowNodes: Node[] = layout.nodes.map((item) => {
    const source = findNode(steps, item.id)
    const hitl = Boolean(
      source?.requiresConfirmation ||
        source?.requiresUserInput ||
        source?.requiresOutputReview
    )
    let subtitle: string = item.type
    if (source?.type === 'step') subtitle = source.targetId || 'agent'
    else if (source?.type === 'condition') subtitle = source.evaluatorCel || 'CEL'
    else if (source?.type === 'router') subtitle = source.selectorCel || 'selector'
    else if (source?.type === 'workflow_ref') subtitle = source.workflowId || 'nested'
    else if (source?.type === 'loop') subtitle = `max ${source.maxIterations ?? 3}`
    else if (source?.type === 'parallel') subtitle = `${source.steps?.length ?? 0} branches`

    const prev = prevById.get(item.id)
    const isNew = animateNew && !prevIds.has(item.id)
    const emptySlots = source ? emptySlotsFor(source) : []

    return {
      id: item.id,
      type: 'workflow',
      position: { x: item.x, y: item.y },
      data: {
        label: item.label,
        nodeType: item.type,
        subtitle,
        hitl,
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
    const isBranch =
      edge.label === 'then' ||
      edge.label === 'else' ||
      (edge.sourceHandle != null && edge.sourceHandle.startsWith('choice:'))
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle ?? 'in',
      label: edge.label,
      type: 'smoothstep',
      animated: edge.label === 'next',
      className: isBranch ? 'wf-edge-branch' : edge.label === 'next' ? 'wf-edge-next' : undefined,
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
  onUndo,
  onRedo,
  onCopy,
  onPaste,
  onOrganize,
  onDuplicateSelected,
  nodeRunStatus = {},
  validationIssues = [],
  emptyHint,
}: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const { dark } = usePreferences()
  const { screenToFlowPosition, fitView, getIntersectingNodes } = useReactFlow()

  const [graph, setGraph] = useState<FlowGraph>({ nodes: [], edges: [] })
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)
  const [connectTargetId, setConnectTargetId] = useState<string | null>(null)
  const connectingFromRef = useRef<{ nodeId: string; handleId: string | null } | null>(null)
  const nodeRunStatusRef = useRef(nodeRunStatus)
  nodeRunStatusRef.current = nodeRunStatus
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

  const structureKey = useMemo(
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
          return `${node.id}:${node.type}:${node.name ?? ''}:${pos}:${kids}`
        })
        .join('#'),
    [steps]
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
    const effectiveSelectedIds = selectedIds.length
      ? selectedIds
      : selectedId
        ? [selectedId]
        : []
    setGraph((prev) => {
      const animateNew = bootstrappedRef.current
      const next = buildGraph(
        steps,
        effectiveSelectedIds,
        prev.nodes,
        animateNew,
        dropTargetId,
        (parentId, slotKey) => onEmptySlotRef.current(parentId, slotKey),
        // run status applied in a cheap follow-up effect via data patch
        {},
        invalidById,
        connectTargetId,
        {
          onDelete: () => onDeleteRef.current(),
          onCopy: () => onCopyRef.current(),
          onDuplicate: () => onDupRef.current(),
        }
      )
      // Preserve runStatus from previous nodes when structure rebuilds mid-run.
      const prevStatus = new Map(
        prev.nodes.map((n) => [n.id, (n.data as { runStatus?: string | null })?.runStatus ?? null])
      )
      const liveStatus = nodeRunStatusRef.current
      next.nodes = next.nodes.map((n) => {
        const status = liveStatus[n.id] ?? prevStatus.get(n.id) ?? null
        if (!status) return n
        return {
          ...n,
          data: { ...(n.data as object), runStatus: status },
        }
      })
      bootstrappedRef.current = true
      return next
    })
  }, [
    structureKey,
    selectionKey,
    steps,
    selectedIds,
    selectedId,
    dropTargetId,
    invalidById,
    invalidKey,
    connectTargetId,
  ])

  // PR8d: patch runStatus without full layout/buildGraph rebuild on every SSE tick.
  useEffect(() => {
    setGraph((current) => {
      let changed = false
      const nodes = current.nodes.map((node) => {
        const nextStatus = nodeRunStatus[node.id] ?? null
        const prevStatus = (node.data as { runStatus?: string | null })?.runStatus ?? null
        if (nextStatus === prevStatus) return node
        changed = true
        return {
          ...node,
          data: { ...(node.data as object), runStatus: nextStatus },
        }
      })
      return changed ? { ...current, nodes } : current
    })
  }, [nodeRunStatus])

  // Focus viewport on running / paused nodes during a run.
  useEffect(() => {
    const focusIds = Object.entries(nodeRunStatus)
      .filter(([, status]) => status === 'running' || status === 'paused')
      .map(([id]) => id)
    const key = focusIds.slice().sort().join(',')
    if (!key || key === lastFocusKeyRef.current) return
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

  const onNodesChange: OnNodesChange = useCallback((changes) => {
    setGraph((current) => ({
      ...current,
      nodes: applyNodeChanges(changes, current.nodes),
    }))
  }, [])

  const onNodeClick: NodeMouseHandler = useCallback(
    (event, node) => {
      onSelect(node.id, event.shiftKey || event.metaKey || event.ctrlKey)
    },
    [onSelect]
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
    wrapperRef.current?.classList.add('is-dragging-node')
    if (settleTimerRef.current) {
      clearTimeout(settleTimerRef.current)
      settleTimerRef.current = null
    }
  }, [])

  const onNodeDrag: OnNodeDrag = useCallback(
    (_event, node) => {
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

      const positions: Record<string, { x: number; y: number }> = {}
      for (const item of allNodes) {
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

  const isValidConnection = useCallback(
    (connection: {
      source: string | null
      target: string | null
      sourceHandle?: string | null
      targetHandle?: string | null
    }) => {
      if (!connection.source || !connection.target) return false
      if (connection.source === connection.target) return false
      // Prevent nesting a node under its own descendant via edge.
      if (isDescendantOf(steps, connection.target, connection.source)) return false
      const sourceNode = findNode(steps, connection.source)
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
      requestAnimationFrame(() => fitView({ padding: 0.2, duration: NODE_SETTLE_MS }))
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
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault()
        onDeleteSelected()
      }
    },
    [onUndo, onRedo, onCopy, onPaste, onSelectMany, onOrganize, onDeleteSelected, steps]
  )

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
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
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
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
        selectionOnDrag
        multiSelectionKeyCode="Shift"
        panOnScroll
        connectionMode={ConnectionMode.Loose}
        colorMode={dark ? 'dark' : 'light'}
        fitView
        fitViewOptions={{ padding: 0.2, duration: NODE_SETTLE_MS }}
        defaultMarkerColor="var(--wf-edge-stroke)"
        minZoom={0.25}
        maxZoom={1.75}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        proOptions={{ hideAttribution: true }}
        deleteKeyCode={null}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1.2}
          color="var(--wf-canvas-dot)"
        />
        <MiniMap pannable zoomable nodeStrokeWidth={2} className="wf-minimap" />
        <Controls showInteractive={false} className="wf-controls" />
      </ReactFlow>
      {!steps.length ? (
        <div className="workflow-canvas__empty-overlay">
          <div className="workflow-canvas__empty-card">
            <strong>{emptyHint || 'Drag nodes from the left palette'}</strong>
            <span>Drop onto the canvas — or onto a container to nest</span>
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

