import type {
  WorkflowDefinition,
  WorkflowDefinitionNode,
  WorkflowNode,
  WorkflowNodeType,
  WorkflowRecord,
  WorkflowState,
} from './types'

export const createNode = (type: WorkflowNodeType = 'step'): WorkflowNode => {
  const id = crypto.randomUUID()
  if (type === 'parallel') {
    return {
      id,
      type: 'parallel',
      name: 'Parallel',
      steps: [createNode('step'), createNode('step')],
    }
  }
  if (type === 'condition') {
    return {
      id,
      type: 'condition',
      name: 'Condition',
      evaluatorCel: 'input.contains("critical")',
      thenSteps: [createNode('step')],
      elseSteps: [createNode('step')],
    }
  }
  if (type === 'loop') {
    return {
      id,
      type: 'loop',
      name: 'Loop',
      maxIterations: 3,
      endConditionCel: 'current_iteration >= 1',
      steps: [createNode('step')],
    }
  }
  return {
    id,
    type: 'step',
    kind: 'agent',
    targetId: 'security-operations',
    name: '',
    instructions: '',
  }
}

/** @deprecated use createNode('step') */
export const createStep = (kind: 'agent' = 'agent'): WorkflowNode => {
  void kind
  return createNode('step')
}

export const moveStep = (steps: WorkflowNode[], id: string, direction: -1 | 1) => {
  const index = steps.findIndex((step) => step.id === id)
  const target = index + direction
  if (index < 0 || target < 0 || target >= steps.length) return steps
  const next = [...steps]
  ;[next[index], next[target]] = [next[target]!, next[index]!]
  return next
}

export const findNode = (nodes: WorkflowNode[], id: string): WorkflowNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node
    for (const child of node.steps ?? []) {
      const found = findNode([child], id)
      if (found) return found
    }
    for (const child of node.thenSteps ?? []) {
      const found = findNode([child], id)
      if (found) return found
    }
    for (const child of node.elseSteps ?? []) {
      const found = findNode([child], id)
      if (found) return found
    }
  }
  return null
}

export const mapTree = (
  nodes: WorkflowNode[],
  mapper: (node: WorkflowNode) => WorkflowNode | null
): WorkflowNode[] =>
  nodes.flatMap((node) => {
    const mapped = mapper(node)
    if (!mapped) return []
    return [
      {
        ...mapped,
        steps: mapped.steps ? mapTree(mapped.steps, mapper) : mapped.steps,
        thenSteps: mapped.thenSteps ? mapTree(mapped.thenSteps, mapper) : mapped.thenSteps,
        elseSteps: mapped.elseSteps ? mapTree(mapped.elseSteps, mapper) : mapped.elseSteps,
      },
    ]
  })

export const updateNodeInTree = (
  nodes: WorkflowNode[],
  id: string,
  updater: (node: WorkflowNode) => WorkflowNode
): WorkflowNode[] =>
  nodes.map((node) => {
    if (node.id === id) return updater(node)
    return {
      ...node,
      steps: node.steps ? updateNodeInTree(node.steps, id, updater) : node.steps,
      thenSteps: node.thenSteps ? updateNodeInTree(node.thenSteps, id, updater) : node.thenSteps,
      elseSteps: node.elseSteps ? updateNodeInTree(node.elseSteps, id, updater) : node.elseSteps,
    }
  })

export const removeNodeInTree = (nodes: WorkflowNode[], id: string): WorkflowNode[] =>
  nodes.flatMap((node) => {
    if (node.id === id) return []
    return [
      {
        ...node,
        steps: node.steps ? removeNodeInTree(node.steps, id) : node.steps,
        thenSteps: node.thenSteps ? removeNodeInTree(node.thenSteps, id) : node.thenSteps,
        elseSteps: node.elseSteps ? removeNodeInTree(node.elseSteps, id) : node.elseSteps,
      },
    ]
  })

export const addChildToNode = (
  nodes: WorkflowNode[],
  parentId: string,
  branch: 'steps' | 'thenSteps' | 'elseSteps',
  child: WorkflowNode
): WorkflowNode[] =>
  updateNodeInTree(nodes, parentId, (parent) => {
    const current = parent[branch] ?? []
    return { ...parent, [branch]: [...current, child] }
  })

const toDefinitionNode = (node: WorkflowNode): WorkflowDefinitionNode => {
  if (node.type === 'parallel') {
    return {
      id: node.id,
      type: 'parallel',
      name: node.name || 'Parallel',
      steps: (node.steps ?? []).map(toDefinitionNode),
    }
  }
  if (node.type === 'condition') {
    return {
      id: node.id,
      type: 'condition',
      name: node.name || 'Condition',
      evaluator: { cel: node.evaluatorCel || 'true' },
      then_steps: (node.thenSteps ?? []).map(toDefinitionNode),
      else_steps: (node.elseSteps ?? []).map(toDefinitionNode),
    }
  }
  if (node.type === 'loop') {
    return {
      id: node.id,
      type: 'loop',
      name: node.name || 'Loop',
      max_iterations: node.maxIterations ?? 3,
      end_condition: node.endConditionCel ? { cel: node.endConditionCel } : null,
      steps: (node.steps ?? []).map(toDefinitionNode),
    }
  }
  const step: WorkflowDefinitionNode = {
    id: node.id,
    type: 'step',
    name: node.name || node.targetId || 'step',
    executor: { kind: 'agent', ref: node.targetId || 'security-operations' },
    instructions: node.instructions || '',
  }
  if (node.requiresConfirmation) {
    step.requires_confirmation = true
    if (node.confirmationMessage) step.confirmation_message = node.confirmationMessage
  }
  return step
}

export const toDefinition = (
  state: Pick<WorkflowState, 'name' | 'description' | 'steps'>
): WorkflowDefinition => ({
  name: state.name || 'Untitled workflow',
  description: state.description || '',
  steps: state.steps.map(toDefinitionNode),
})

const fromDefinitionNode = (node: WorkflowDefinitionNode): WorkflowNode => {
  if (node.type === 'parallel') {
    return {
      id: node.id || crypto.randomUUID(),
      type: 'parallel',
      name: node.name || 'Parallel',
      steps: (node.steps ?? []).map(fromDefinitionNode),
    }
  }
  if (node.type === 'condition') {
    return {
      id: node.id || crypto.randomUUID(),
      type: 'condition',
      name: node.name || 'Condition',
      evaluatorCel: node.evaluator?.cel || (node.evaluator?.value === false ? 'false' : 'true'),
      thenSteps: (node.then_steps ?? []).map(fromDefinitionNode),
      elseSteps: (node.else_steps ?? []).map(fromDefinitionNode),
    }
  }
  if (node.type === 'loop') {
    return {
      id: node.id || crypto.randomUUID(),
      type: 'loop',
      name: node.name || 'Loop',
      maxIterations: node.max_iterations ?? 3,
      endConditionCel: node.end_condition?.cel || '',
      steps: (node.steps ?? []).map(fromDefinitionNode),
    }
  }
  return {
    id: node.id || crypto.randomUUID(),
    type: 'step',
    kind: 'agent',
    targetId: node.executor?.ref || 'security-operations',
    name: node.name || '',
    instructions: node.instructions || '',
    requiresConfirmation: Boolean(node.requires_confirmation),
    confirmationMessage: node.confirmation_message || '',
  }
}

export const fromRecord = (record: WorkflowRecord): Partial<WorkflowState> => {
  const steps = (record.definition?.steps ?? []).map(fromDefinitionNode)
  return {
    workflowId: record.id,
    name: record.name || record.definition?.name || '',
    description: record.description || record.definition?.description || '',
    steps,
    selectedId: steps[0]?.id ?? null,
    dirty: false,
  }
}

const emitCodeNode = (node: WorkflowDefinitionNode, indent: string): string => {
  if (node.type === 'parallel') {
    const children = (node.steps ?? []).map((child) => emitCodeNode(child, indent + '    ')).join(',\n')
    return `${indent}Parallel(\n${children},\n${indent}    name=${JSON.stringify(node.name)},\n${indent})`
  }
  if (node.type === 'condition') {
    const thenSteps = (node.then_steps ?? []).map((child) => emitCodeNode(child, indent + '    ')).join(',\n')
    const elseSteps = (node.else_steps ?? []).map((child) => emitCodeNode(child, indent + '    ')).join(',\n')
    const cel = node.evaluator?.cel ?? 'true'
    return [
      `${indent}Condition(`,
      `${indent}    name=${JSON.stringify(node.name)},`,
      `${indent}    evaluator=${JSON.stringify(cel)},`,
      `${indent}    steps=[`,
      thenSteps,
      `${indent}    ],`,
      elseSteps
        ? `${indent}    else_steps=[\n${elseSteps}\n${indent}    ],`
        : `${indent}    else_steps=None,`,
      `${indent})`,
    ].join('\n')
  }
  if (node.type === 'loop') {
    const children = (node.steps ?? []).map((child) => emitCodeNode(child, indent + '    ')).join(',\n')
    const end = node.end_condition?.cel
    return [
      `${indent}Loop(`,
      `${indent}    name=${JSON.stringify(node.name)},`,
      `${indent}    max_iterations=${node.max_iterations ?? 3},`,
      end ? `${indent}    end_condition=${JSON.stringify(end)},` : `${indent}    end_condition=None,`,
      `${indent}    steps=[`,
      children,
      `${indent}    ],`,
      `${indent})`,
    ].join('\n')
  }
  return (
    `${indent}Step(name=${JSON.stringify(node.name)}, ` +
    `step_id=${JSON.stringify(node.id)}, ` +
    `agent=agents[${JSON.stringify(node.executor?.ref ?? 'security-operations')}])`
  )
}

export const buildWorkflowCode = (state: WorkflowState) => {
  const definition = toDefinition(state)
  const steps = definition.steps.map((step) => emitCodeNode(step, '        ')).join(',\n')
  return [
    'from agno.workflow import Workflow, Step, Parallel, Condition, Loop',
    '',
    `# Compiled from workbench definition (PR2 control flow)`,
    `# workflow_id=${JSON.stringify(state.workflowId ?? '')}`,
    `workflow = Workflow(`,
    `    name=${JSON.stringify(definition.name)},`,
    `    description=${JSON.stringify(definition.description)},`,
    `    steps=[`,
    steps || '        # no steps',
    `    ],`,
    `)`,
    '',
    `workflow.print_response(`,
    `    input=${JSON.stringify(state.input)},`,
    `    session_id=${JSON.stringify(state.sessionId)},`,
    `    stream=True,`,
    `    stream_events=True,`,
    `)`,
  ].join('\n')
}

export const nodeLabel = (node: WorkflowNode): string => {
  if (node.name?.trim()) return node.name
  if (node.type === 'step') return node.targetId || 'step'
  return node.type
}


export type CanvasLayoutNode = {
  id: string
  type: WorkflowNodeType
  label: string
  depth: number
  x: number
  y: number
}

export type CanvasLayoutEdge = {
  id: string
  source: string
  target: string
  label?: string
}

/** Hierarchical layout for nested workflow tree (left → right). */
export const layoutCanvas = (roots: WorkflowNode[]): { nodes: CanvasLayoutNode[]; edges: CanvasLayoutEdge[] } => {
  const nodes: CanvasLayoutNode[] = []
  const edges: CanvasLayoutEdge[] = []
  let row = 0
  const visit = (node: WorkflowNode, depth: number, parentId: string | null, edgeLabel?: string) => {
    const y = row * 90
    const x = depth * 220
    nodes.push({
      id: node.id,
      type: node.type,
      label: nodeLabel(node),
      depth,
      x,
      y,
    })
    if (parentId) {
      edges.push({
        id: `${parentId}->${node.id}`,
        source: parentId,
        target: node.id,
        label: edgeLabel,
      })
    }
    row += 1
    if (node.type === 'condition') {
      for (const child of node.thenSteps ?? []) visit(child, depth + 1, node.id, 'then')
      for (const child of node.elseSteps ?? []) visit(child, depth + 1, node.id, 'else')
    } else {
      for (const child of node.steps ?? []) visit(child, depth + 1, node.id)
    }
  }
  for (const root of roots) visit(root, 0, null)
  // sequential top-level edges
  for (let i = 0; i < roots.length - 1; i += 1) {
    edges.push({
      id: `seq-${roots[i]!.id}->${roots[i + 1]!.id}`,
      source: roots[i]!.id,
      target: roots[i + 1]!.id,
      label: 'next',
    })
  }
  return { nodes, edges }
}
