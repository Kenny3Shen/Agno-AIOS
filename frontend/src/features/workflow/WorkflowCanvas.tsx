import { useMemo, useCallback, useRef, type DragEvent } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type OnNodeDrag,
  type OnConnect,
  MarkerType,
  ConnectionMode,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { WorkflowNode, WorkflowNodeType } from './types'
import { usePreferences } from '@/app/providers/AppProviders'
import { findNode, layoutCanvas } from './utils'
import { WorkflowFlowNode } from './WorkflowFlowNode'

const nodeTypes = { workflow: WorkflowFlowNode }

const PALETTE_MIME = 'application/x-workflow-node'

type Props = {
  steps: WorkflowNode[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  onPositionsChange: (positions: Record<string, { x: number; y: number }>) => void
  onConnectSequence: (sourceId: string, targetId: string) => void
  onDropNode: (type: WorkflowNodeType, position: { x: number; y: number }) => void
  emptyHint?: string
}

function CanvasInner({
  steps,
  selectedId,
  onSelect,
  onPositionsChange,
  onConnectSequence,
  onDropNode,
  emptyHint,
}: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const { dark } = usePreferences()
  const { screenToFlowPosition, fitView } = useReactFlow()

  const { nodes, edges } = useMemo(() => {
    const layout = layoutCanvas(steps)
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
      return {
        id: item.id,
        type: 'workflow',
        position: { x: item.x, y: item.y },
        data: {
          label: item.label,
          nodeType: item.type,
          subtitle,
          hitl,
        },
        selected: item.id === selectedId,
      }
    })
    const flowEdges: Edge[] = layout.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      type: 'smoothstep',
      animated: edge.label === 'next',
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 18,
        height: 18,
        color: 'var(--wf-edge-stroke)',
      },
      style: { stroke: 'var(--wf-edge-stroke)', strokeWidth: 1.5 },
      labelStyle: { fontSize: 10, fill: 'var(--wf-edge-label)', fontWeight: 500 },
      labelBgStyle: { fill: 'var(--wf-edge-label-bg)', fillOpacity: 0.95 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
    }))
    return { nodes: flowNodes, edges: flowEdges }
  }, [steps, selectedId])

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => onSelect(node.id),
    [onSelect]
  )

  const onPaneClick = useCallback(() => onSelect(null), [onSelect])

  const onNodeDragStop: OnNodeDrag = useCallback(
    (_event, _node, allNodes) => {
      const positions: Record<string, { x: number; y: number }> = {}
      for (const item of allNodes) {
        positions[item.id] = { x: item.position.x, y: item.position.y }
      }
      onPositionsChange(positions)
    },
    [onPositionsChange]
  )

  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (connection.source && connection.target) {
        onConnectSequence(connection.source, connection.target)
      }
    },
    [onConnectSequence]
  )

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault()
      const type = event.dataTransfer.getData(PALETTE_MIME) as WorkflowNodeType
      if (!type) return
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      onDropNode(type, position)
      // slight delay so new node is mounted
      requestAnimationFrame(() => fitView({ padding: 0.2, duration: 200 }))
    },
    [screenToFlowPosition, onDropNode, fitView]
  )

  return (
    <div
      ref={wrapperRef}
      className={`workflow-canvas workflow-canvas--main ${steps.length ? '' : 'is-empty'}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onNodeDragStop={onNodeDragStop}
        onConnect={onConnect}
        nodesDraggable
        nodesConnectable
        elementsSelectable
        panOnScroll
        connectionMode={ConnectionMode.Loose}
        colorMode={dark ? 'dark' : 'light'}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        defaultMarkerColor="var(--wf-edge-stroke)"
        minZoom={0.25}
        maxZoom={1.75}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        proOptions={{ hideAttribution: true }}
        deleteKeyCode={null}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="var(--wf-canvas-dot)" />
        <MiniMap
          pannable
          zoomable
          nodeStrokeWidth={2}
          className="wf-minimap"
        />
        <Controls showInteractive={false} className="wf-controls" />
      </ReactFlow>
      {!steps.length ? (
        <div className="workflow-canvas__empty-overlay">
          <div className="workflow-canvas__empty-card">
            <strong>{emptyHint || 'Drag nodes from the left palette'}</strong>
            <span>Drop onto the canvas to start building your workflow</span>
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

