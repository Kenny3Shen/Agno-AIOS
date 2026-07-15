import type {
  WorkflowDefinition,
  WorkflowDefinitionNode,
  WorkflowNode,
  WorkflowNodeType,
  WorkflowRecord,
  WorkflowState,
  WorkflowTriggers,
} from './types'

export const defaultTriggers = (): WorkflowTriggers => ({
  webhook: { enabled: false, secret: '' },
  cron: { enabled: false, expression: '' },
})

export const createNode = (type: WorkflowNodeType = 'step'): WorkflowNode => {
  const id = crypto.randomUUID()
  // Control-flow nodes start empty: users drop Agent steps into them.
  // Seeding default agents caused "extra Agent step" spam on the canvas.
  if (type === 'parallel') {
    return {
      id,
      type: 'parallel',
      name: 'Parallel',
      steps: [],
    }
  }
  if (type === 'condition') {
    return {
      id,
      type: 'condition',
      name: 'Condition',
      evaluatorCel: 'input.contains("critical")',
      thenSteps: [],
      elseSteps: [],
    }
  }
  if (type === 'loop') {
    return {
      id,
      type: 'loop',
      name: 'Loop',
      maxIterations: 3,
      endConditionCel: 'current_iteration >= 1',
      steps: [],
    }
  }
  if (type === 'router') {
    return {
      id,
      type: 'router',
      name: 'Router',
      selectorCel: 'input.contains("critical") ? "path_a" : "path_b"',
      choices: [
        { id: crypto.randomUUID(), name: 'path_a', steps: [] },
        { id: crypto.randomUUID(), name: 'path_b', steps: [] },
      ],
    }
  }
  if (type === 'workflow_ref') {
    return {
      id,
      type: 'workflow_ref',
      name: 'Nested workflow',
      workflowId: '',
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

export const createStep = () => createNode('step')

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
    for (const choice of node.choices ?? []) {
      const found = findNode(choice.steps, id)
      if (found) return found
    }
  }
  return null
}

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
      choices: node.choices?.map((choice) => ({
        ...choice,
        steps: updateNodeInTree(choice.steps, id, updater),
      })),
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
        choices: node.choices?.map((choice) => ({
          ...choice,
          steps: removeNodeInTree(choice.steps, id),
        })),
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

/** Reorder top-level nodes by comparing canvas Y positions. */
export const reorderRootsByPositions = (nodes: WorkflowNode[]): WorkflowNode[] => {
  return [...nodes].sort((a, b) => {
    const ay = a.position?.y ?? 0
    const by = b.position?.y ?? 0
    if (ay !== by) return ay - by
    return (a.position?.x ?? 0) - (b.position?.x ?? 0)
  })
}

/** Move node to become sibling after target among root steps (simple restructure). */
export const moveNodeAfter = (
  nodes: WorkflowNode[],
  sourceId: string,
  targetId: string
): WorkflowNode[] => {
  if (sourceId === targetId) return nodes
  const source = nodes.find((n) => n.id === sourceId)
  if (!source) return nodes
  const without = nodes.filter((n) => n.id !== sourceId)
  const targetIndex = without.findIndex((n) => n.id === targetId)
  if (targetIndex < 0) return nodes
  const next = [...without]
  next.splice(targetIndex + 1, 0, source)
  return next
}

const toDefinitionNode = (node: WorkflowNode): WorkflowDefinitionNode => {
  const position = node.position
  const basePos = position ? { position: { x: position.x, y: position.y } } : {}
  if (node.type === 'parallel') {
    return {
      id: node.id,
      type: 'parallel',
      name: node.name || 'Parallel',
      steps: (node.steps ?? []).map(toDefinitionNode),
      ...basePos,
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
      ...basePos,
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
      ...basePos,
    }
  }
  if (node.type === 'router') {
    return {
      id: node.id,
      type: 'router',
      name: node.name || 'Router',
      selector: { cel: node.selectorCel || 'step_choices[0]' },
      choices: (node.choices ?? []).map((choice) => ({
        id: choice.id,
        name: choice.name,
        steps: choice.steps.map(toDefinitionNode),
      })),
      ...basePos,
    }
  }
  if (node.type === 'workflow_ref') {
    return {
      id: node.id,
      type: 'workflow_ref',
      name: node.name || 'Nested workflow',
      workflow_id: node.workflowId || '',
      ...basePos,
    }
  }
  const step: WorkflowDefinitionNode = {
    id: node.id,
    type: 'step',
    name: node.name || node.targetId || 'step',
    executor: { kind: 'agent', ref: node.targetId || 'security-operations' },
    instructions: node.instructions || '',
    ...basePos,
  }
  if (node.requiresConfirmation) {
    step.requires_confirmation = true
    if (node.confirmationMessage) step.confirmation_message = node.confirmationMessage
  }
  if (node.requiresUserInput) {
    step.requires_user_input = true
    if (node.userInputMessage) step.user_input_message = node.userInputMessage
  }
  if (node.requiresOutputReview) {
    step.requires_output_review = true
    if (node.outputReviewMessage) step.output_review_message = node.outputReviewMessage
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
  const position = node.position
  const basePos = position ? { position: { x: position.x, y: position.y } } : {}
  if (node.type === 'parallel') {
    return {
      id: node.id || crypto.randomUUID(),
      type: 'parallel',
      name: node.name || 'Parallel',
      steps: (node.steps ?? []).map(fromDefinitionNode),
      ...basePos,
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
      ...basePos,
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
      ...basePos,
    }
  }
  if (node.type === 'router') {
    return {
      id: node.id || crypto.randomUUID(),
      type: 'router',
      name: node.name || 'Router',
      selectorCel: node.selector?.cel || '',
      choices: (node.choices ?? []).map((choice) => ({
        id: choice.id || crypto.randomUUID(),
        name: choice.name,
        steps: (choice.steps ?? []).map(fromDefinitionNode),
      })),
      ...basePos,
    }
  }
  if (node.type === 'workflow_ref') {
    return {
      id: node.id || crypto.randomUUID(),
      type: 'workflow_ref',
      name: node.name || 'Nested workflow',
      workflowId: node.workflow_id || '',
      ...basePos,
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
    requiresUserInput: Boolean(node.requires_user_input),
    userInputMessage: node.user_input_message || '',
    requiresOutputReview: Boolean(node.requires_output_review),
    outputReviewMessage: node.output_review_message || '',
    ...basePos,
  }
}

export const fromRecord = (record: WorkflowRecord): Partial<WorkflowState> => {
  const steps = (record.definition?.steps ?? []).map(fromDefinitionNode)
  return {
    workflowId: record.id,
    name: record.name || record.definition?.name || '',
    description: record.description || record.definition?.description || '',
    steps,
    triggers: record.triggers ?? defaultTriggers(),
    selectedId: steps[0]?.id ?? null,
    dirty: false,
  }
}

export const nodeLabel = (node: WorkflowNode): string => {
  if (node.name?.trim()) return node.name
  if (node.type === 'step') return node.targetId || 'step'
  if (node.type === 'workflow_ref') return node.workflowId || 'workflow_ref'
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

export const layoutCanvas = (
  roots: WorkflowNode[]
): { nodes: CanvasLayoutNode[]; edges: CanvasLayoutEdge[] } => {
  const nodes: CanvasLayoutNode[] = []
  const edges: CanvasLayoutEdge[] = []
  let row = 0
  const visit = (node: WorkflowNode, depth: number, parentId: string | null, edgeLabel?: string) => {
    const autoY = row * 90
    const autoX = depth * 220
    const x = node.position?.x ?? autoX
    const y = node.position?.y ?? autoY
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
    } else if (node.type === 'router') {
      for (const choice of node.choices ?? []) {
        for (const child of choice.steps) visit(child, depth + 1, node.id, choice.name)
      }
    } else {
      for (const child of node.steps ?? []) visit(child, depth + 1, node.id)
    }
  }
  for (const root of roots) visit(root, 0, null)
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
  if (node.type === 'router') {
    const choices = (node.choices ?? [])
      .map((choice) => {
        const body = choice.steps.map((child) => emitCodeNode(child, indent + '        ')).join(',\n')
        return `${indent}    Steps(name=${JSON.stringify(choice.name)}, steps=[\n${body}\n${indent}    ])`
      })
      .join(',\n')
    return [
      `${indent}Router(`,
      `${indent}    name=${JSON.stringify(node.name)},`,
      `${indent}    selector=${JSON.stringify(node.selector?.cel ?? '')},`,
      `${indent}    choices=[`,
      choices,
      `${indent}    ],`,
      `${indent})`,
    ].join('\n')
  }
  if (node.type === 'workflow_ref') {
    return `${indent}# nested workflow_ref ${JSON.stringify(node.workflow_id)} as Workflow(...)`
  }
  return (
    `${indent}Step(name=${JSON.stringify(node.name)}, ` +
    `step_id=${JSON.stringify(node.id)}, ` +
    `agent=agents[${JSON.stringify(node.executor?.ref ?? 'security-operations')}], ` +
    `requires_confirmation=${node.requires_confirmation ? 'True' : 'False'})`
  )
}

export const buildWorkflowCode = (state: WorkflowState) => {
  const definition = toDefinition(state)
  const steps = definition.steps.map((step) => emitCodeNode(step, '        ')).join(',\n')
  return [
    'from agno.workflow import Workflow, Step, Parallel, Condition, Loop, Router, Steps',
    '',
    `# Compiled from workbench definition (PR4)`,
    `# workflow_id=${JSON.stringify(state.workflowId ?? '')}`,
    `workflow = Workflow(`,
    `    name=${JSON.stringify(definition.name)},`,
    `    description=${JSON.stringify(definition.description)},`,
    `    steps=[`,
    steps || '        # no steps',
    `    ],`,
    `)`,
  ].join('\n')
}
