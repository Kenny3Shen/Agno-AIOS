import { useMemo, useCallback } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type OnNodeDrag,
  type OnConnect,
  MarkerType,
  Position,
  ConnectionMode,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { WorkflowNode, WorkflowNodeType } from './types'
import { layoutCanvas } from './utils'

const typeColor: Record<WorkflowNodeType, string> = {
  step: '#1677ff',
  parallel: '#722ed1',
  condition: '#faad14',
  loop: '#13c2c2',
  router: '#eb2f96',
  workflow_ref: '#52c41a',
}

type Props = {
  steps: WorkflowNode[]
  selectedId: string | null
  onSelect: (id: string) => void
  onPositionsChange: (positions: Record<string, { x: number; y: number }>) => void
  onConnectSequence: (sourceId: string, targetId: string) => void
}

export function WorkflowCanvas({
  steps,
  selectedId,
  onSelect,
  onPositionsChange,
  onConnectSequence,
}: Props) {
  const { nodes, edges } = useMemo(() => {
    const layout = layoutCanvas(steps)
    const flowNodes: Node[] = layout.nodes.map((item) => ({
      id: item.id,
      position: { x: item.x, y: item.y },
      data: { label: `${item.type}: ${item.label}` },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      style: {
        border: `2px solid ${typeColor[item.type]}`,
        borderRadius: 8,
        padding: 8,
        fontSize: 12,
        background: item.id === selectedId ? 'rgba(22,119,255,0.08)' : '#fff',
        minWidth: 140,
        boxShadow: item.id === selectedId ? '0 0 0 2px rgba(22,119,255,0.25)' : undefined,
        cursor: 'grab',
      },
    }))
    const flowEdges: Edge[] = layout.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
      style: { stroke: '#94a3b8' },
      labelStyle: { fontSize: 10, fill: '#64748b' },
    }))
    return { nodes: flowNodes, edges: flowEdges }
  }, [steps, selectedId])

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onSelect(node.id)
    },
    [onSelect]
  )

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

  if (!steps.length) {
    return (
      <div className="workflow-canvas empty">
        <span>Add nodes to visualize and edit the graph</span>
      </div>
    )
  }

  return (
    <div className="workflow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        onConnect={onConnect}
        nodesDraggable
        nodesConnectable
        elementsSelectable
        connectionMode={ConnectionMode.Loose}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  )
}
