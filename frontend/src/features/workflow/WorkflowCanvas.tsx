import { useMemo, useCallback, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeMouseHandler,
  MarkerType,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { WorkflowNode, WorkflowNodeType } from './types'
import { layoutCanvas } from './utils'

const typeColor: Record<WorkflowNodeType, string> = {
  step: '#1677ff',
  parallel: '#722ed1',
  condition: '#faad14',
  loop: '#13c2c2',
}

type Props = {
  steps: WorkflowNode[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function WorkflowCanvas({ steps, selectedId, onSelect }: Props) {
  const { nodes, edges } = useMemo(() => {
    const layout = layoutCanvas(steps)
    const flowNodes: Node[] = layout.nodes.map((item) => ({
      id: item.id,
      position: { x: item.x, y: item.y },
      data: { label: `${item.type}: ${item.label}` },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        border: `2px solid ${typeColor[item.type]}`,
        borderRadius: 8,
        padding: 8,
        fontSize: 12,
        background: item.id === selectedId ? 'rgba(22,119,255,0.08)' : '#fff',
        minWidth: 140,
        boxShadow: item.id === selectedId ? '0 0 0 2px rgba(22,119,255,0.25)' : undefined,
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

  // Force fit when structure changes significantly
  useEffect(() => {
    // no-op placeholder for future fitView hooks
  }, [steps.length])

  if (!steps.length) {
    return (
      <div className="workflow-canvas empty">
        <span>Add nodes to visualize the graph</span>
      </div>
    )
  }

  return (
    <div className="workflow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
