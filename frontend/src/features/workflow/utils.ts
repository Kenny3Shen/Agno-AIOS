import type {
  WorkflowDefinition,
  WorkflowDefinitionNode,
  UserInputSchemaField,
  WorkflowNode,
  WorkflowNodeType,
  WorkflowRecord,
  WorkflowState,
  WorkflowTriggers,
} from './types'

export const defaultTriggers = (): WorkflowTriggers => ({
  webhook: { enabled: false, secret: '' },
  cron: { enabled: false, expression: '', last_run_at: 0 },
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

export type BranchKey = 'steps' | 'thenSteps' | 'elseSteps'

export type ReparentTarget =
  | { kind: 'root'; index?: number }
  | { kind: 'branch'; parentId: string; branch: BranchKey }
  | { kind: 'choice'; parentId: string; choiceId: string }

export type EmptySlot = {
  key: string
  label: string
  branch?: BranchKey
  choiceId?: string
}

export const isContainerType = (type: WorkflowNodeType): boolean =>
  type === 'parallel' || type === 'condition' || type === 'loop' || type === 'router'

export const collectNodeIds = (nodes: WorkflowNode[]): string[] => {
  const ids: string[] = []
  const walk = (list: WorkflowNode[]) => {
    for (const node of list) {
      ids.push(node.id)
      if (node.steps) walk(node.steps)
      if (node.thenSteps) walk(node.thenSteps)
      if (node.elseSteps) walk(node.elseSteps)
      for (const choice of node.choices ?? []) walk(choice.steps)
    }
  }
  walk(nodes)
  return ids
}

export const isDescendantOf = (
  nodes: WorkflowNode[],
  ancestorId: string,
  maybeDescendantId: string
): boolean => {
  const ancestor = findNode(nodes, ancestorId)
  if (!ancestor) return false
  return collectNodeIds([ancestor]).includes(maybeDescendantId)
}

/** Deep-clone a node tree with fresh ids (for copy/paste). */
export const cloneNodeDeep = (node: WorkflowNode): WorkflowNode => {
  const id = crypto.randomUUID()
  const base = { ...node, id, position: node.position ? { ...node.position } : undefined }
  if (node.type === 'condition') {
    return {
      ...base,
      type: 'condition',
      thenSteps: (node.thenSteps ?? []).map(cloneNodeDeep),
      elseSteps: (node.elseSteps ?? []).map(cloneNodeDeep),
    }
  }
  if (node.type === 'router') {
    return {
      ...base,
      type: 'router',
      choices: (node.choices ?? []).map((choice) => ({
        id: crypto.randomUUID(),
        name: choice.name,
        steps: choice.steps.map(cloneNodeDeep),
      })),
    }
  }
  if (node.steps) {
    return { ...base, steps: node.steps.map(cloneNodeDeep) }
  }
  return base
}

export const removeNodesInTree = (nodes: WorkflowNode[], ids: string[]): WorkflowNode[] => {
  const doomed = new Set(ids)
  const filterList = (list: WorkflowNode[]): WorkflowNode[] =>
    list.flatMap((node) => {
      if (doomed.has(node.id)) return []
      return [
        {
          ...node,
          steps: node.steps ? filterList(node.steps) : node.steps,
          thenSteps: node.thenSteps ? filterList(node.thenSteps) : node.thenSteps,
          elseSteps: node.elseSteps ? filterList(node.elseSteps) : node.elseSteps,
          choices: node.choices?.map((choice) => ({
            ...choice,
            steps: filterList(choice.steps),
          })),
        },
      ]
    })
  return filterList(nodes)
}

/** Extract a node from the tree; returns the node and remaining roots. */
export const extractNode = (
  nodes: WorkflowNode[],
  id: string
): { node: WorkflowNode | null; remaining: WorkflowNode[] } => {
  const node = findNode(nodes, id)
  if (!node) return { node: null, remaining: nodes }
  return { node, remaining: removeNodeInTree(nodes, id) }
}

export const insertChild = (
  nodes: WorkflowNode[],
  target: ReparentTarget,
  child: WorkflowNode
): WorkflowNode[] => {
  if (target.kind === 'root') {
    const next = [...nodes]
    const index = target.index ?? next.length
    next.splice(Math.max(0, Math.min(index, next.length)), 0, child)
    return next
  }
  if (target.kind === 'choice') {
    return updateNodeInTree(nodes, target.parentId, (parent) => {
      if (parent.type !== 'router') return parent
      return {
        ...parent,
        choices: (parent.choices ?? []).map((choice) =>
          choice.id === target.choiceId
            ? { ...choice, steps: [...choice.steps, child] }
            : choice
        ),
      }
    })
  }
  return addChildToNode(nodes, target.parentId, target.branch, child)
}

/**
 * Move `nodeId` under a container (or to root). Blocks cycles and HITL-in-Parallel.
 */
export const reparentNode = (
  nodes: WorkflowNode[],
  nodeId: string,
  target: ReparentTarget
): WorkflowNode[] => {
  if (target.kind !== 'root' && target.parentId === nodeId) return nodes
  if (target.kind !== 'root' && isDescendantOf(nodes, nodeId, target.parentId)) return nodes

  const { node, remaining } = extractNode(nodes, nodeId)
  if (!node) return nodes

  if (target.kind !== 'root') {
    const parent = findNode(remaining, target.parentId) ?? findNode(nodes, target.parentId)
    if (!parent || !isContainerType(parent.type)) return nodes
    // Agno: no HITL inside Parallel
    if (parent.type === 'parallel') {
      const hitl = Boolean(
        node.requiresConfirmation || node.requiresUserInput || node.requiresOutputReview
      )
      if (hitl || collectNodeIds([node]).some((id) => {
        const n = findNode([node], id)
        return Boolean(n?.requiresConfirmation || n?.requiresUserInput || n?.requiresOutputReview)
      })) {
        return nodes
      }
    }
  }

  return insertChild(remaining, target, node)
}

/** Default drop target when releasing a node over a container. */
export const defaultDropTarget = (container: WorkflowNode): ReparentTarget | null => {
  if (container.type === 'parallel' || container.type === 'loop') {
    return { kind: 'branch', parentId: container.id, branch: 'steps' }
  }
  if (container.type === 'condition') {
    const thenEmpty = !(container.thenSteps ?? []).length
    const elseEmpty = !(container.elseSteps ?? []).length
    if (thenEmpty) return { kind: 'branch', parentId: container.id, branch: 'thenSteps' }
    if (elseEmpty) return { kind: 'branch', parentId: container.id, branch: 'elseSteps' }
    return { kind: 'branch', parentId: container.id, branch: 'thenSteps' }
  }
  if (container.type === 'router') {
    const choices = container.choices ?? []
    const empty = choices.find((c) => c.steps.length === 0) ?? choices[0]
    if (!empty) return null
    return { kind: 'choice', parentId: container.id, choiceId: empty.id }
  }
  return null
}


/** Branch source handles rendered on a control-flow node. */
export const branchHandlesFor = (
  node: WorkflowNode
): Array<{ id: string; label: string }> => {
  if (node.type === 'condition') {
    return [
      { id: 'then', label: 'then' },
      { id: 'else', label: 'else' },
    ]
  }
  if (node.type === 'router') {
    return (node.choices ?? []).map((choice) => ({
      id: `choice:${choice.id}`,
      label: choice.name || 'path',
    }))
  }
  if (node.type === 'parallel') {
    return [{ id: 'out', label: 'branch' }]
  }
  if (node.type === 'loop') {
    return [{ id: 'out', label: 'body' }]
  }
  return []
}

/** Map a connection sourceHandle to a reparent target under the source node. */
export const reparentTargetFromHandle = (
  source: WorkflowNode,
  sourceHandle: string | null | undefined
): ReparentTarget | null => {
  // Normalize side aliases: "then-right" → "then", "out-right" → "out"
  let handle = (sourceHandle || '').trim()
  if (handle.endsWith('-right')) handle = handle.slice(0, -'-right'.length)
  if (handle.endsWith('-left')) handle = handle.slice(0, -'-left'.length)

  if (source.type === 'condition') {
    if (handle === 'then' || handle === 'thenSteps') {
      return { kind: 'branch', parentId: source.id, branch: 'thenSteps' }
    }
    if (handle === 'else' || handle === 'elseSteps') {
      return { kind: 'branch', parentId: source.id, branch: 'elseSteps' }
    }
  }
  if (source.type === 'router' && handle.startsWith('choice:')) {
    return { kind: 'choice', parentId: source.id, choiceId: handle.slice('choice:'.length) }
  }
  if (
    (source.type === 'parallel' || source.type === 'loop') &&
    (handle === 'out' || handle === 'body' || handle === 'steps' || !handle)
  ) {
    return { kind: 'branch', parentId: source.id, branch: 'steps' }
  }
  return null
}

/** True if handle is a node entrance (top or left). */
export const isEntranceHandle = (handle: string | null | undefined): boolean => {
  const h = (handle || '').trim()
  return !h || h === 'in' || h === 'in-left'
}

/** True if handle is a default (non-branch) exit. */
export const isDefaultExitHandle = (handle: string | null | undefined): boolean => {
  const h = (handle || '').trim()
  return !h || h === 'out' || h === 'out-right'
}

export const emptySlotsFor = (node: WorkflowNode): EmptySlot[] => {
  if (node.type === 'parallel') {
    if ((node.steps ?? []).length) return []
    return [{ key: 'steps', label: 'Add branch', branch: 'steps' }]
  }
  if (node.type === 'loop') {
    if ((node.steps ?? []).length) return []
    return [{ key: 'steps', label: 'Add body step', branch: 'steps' }]
  }
  if (node.type === 'condition') {
    const slots: EmptySlot[] = []
    if (!(node.thenSteps ?? []).length) {
      slots.push({ key: 'thenSteps', label: 'Add then', branch: 'thenSteps' })
    }
    if (!(node.elseSteps ?? []).length) {
      slots.push({ key: 'elseSteps', label: 'Add else', branch: 'elseSteps' })
    }
    return slots
  }
  if (node.type === 'router') {
    return (node.choices ?? [])
      .filter((c) => c.steps.length === 0)
      .map((c) => ({
        key: `choice:${c.id}`,
        label: `Add ${c.name || 'path'}`,
        choiceId: c.id,
      }))
  }
  return []
}

export const parseEmptySlot = (
  parent: WorkflowNode,
  slotKey: string
): ReparentTarget | null => {
  if (slotKey === 'steps' || slotKey === 'thenSteps' || slotKey === 'elseSteps') {
    return { kind: 'branch', parentId: parent.id, branch: slotKey }
  }
  if (slotKey.startsWith('choice:')) {
    return { kind: 'choice', parentId: parent.id, choiceId: slotKey.slice('choice:'.length) }
  }
  return null
}


export type WorkflowValidationIssue = {
  nodeId: string | null
  code: string
  message: string
}

/** Client-side save checks (mirrors compiler empty-branch rules). */
export const validateWorkflowDraft = (roots: WorkflowNode[]): WorkflowValidationIssue[] => {
  const issues: WorkflowValidationIssue[] = []
  if (!roots.length) {
    issues.push({
      nodeId: null,
      code: 'empty_workflow',
      message: 'Add at least one node before saving',
    })
    return issues
  }

  const walk = (nodes: WorkflowNode[], path: string) => {
    for (const node of nodes) {
      const label = node.name?.trim() || node.type
      const here = `${path}/${label}`
      if (node.type === 'parallel') {
        if (!(node.steps ?? []).length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_parallel',
            message: `${here}: Parallel needs at least one branch`,
          })
        }
      }
      if (node.type === 'loop') {
        if (!(node.steps ?? []).length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_loop',
            message: `${here}: Loop body is empty`,
          })
        }
      }
      if (node.type === 'condition') {
        if (!(node.thenSteps ?? []).length && !(node.elseSteps ?? []).length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_condition',
            message: `${here}: Condition needs then and/or else steps`,
          })
        }
      }
      if (node.type === 'router') {
        const choices = node.choices ?? []
        if (!choices.length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_router',
            message: `${here}: Router has no choices`,
          })
        }
        for (const choice of choices) {
          if (!choice.steps.length) {
            issues.push({
              nodeId: node.id,
              code: 'empty_router_choice',
              message: `${here}: choice "${choice.name || choice.id}" is empty`,
            })
          }
        }
      }
      if (node.type === 'workflow_ref' && !(node.workflowId || '').trim()) {
        issues.push({
          nodeId: node.id,
          code: 'missing_workflow_ref',
          message: `${here}: Nested workflow id is required`,
        })
      }
      if (node.type === 'step' && !(node.targetId || '').trim()) {
        issues.push({
          nodeId: node.id,
          code: 'missing_executor',
          message: `${here}: Agent executor is required`,
        })
      }
      for (const list of [node.steps, node.thenSteps, node.elseSteps]) {
        if (list?.length) walk(list, here)
      }
      for (const choice of node.choices ?? []) {
        if (choice.steps.length) walk(choice.steps, `${here}/${choice.name || 'choice'}`)
      }
    }
  }
  walk(roots, 'workflow')
  return issues
}

const subtreeHeight = (node: WorkflowNode): number => {
  const children =
    node.type === 'condition'
      ? [...(node.thenSteps ?? []), ...(node.elseSteps ?? [])]
      : node.type === 'router'
        ? (node.choices ?? []).flatMap((c) => c.steps)
        : (node.steps ?? [])
  if (!children.length) return 1
  return children.reduce((sum, child) => sum + subtreeHeight(child), 0)
}

/** Hierarchical auto-layout (tree packer; Dify-like vertical flow). Overwrites positions. */
export const applyAutoLayout = (roots: WorkflowNode[]): WorkflowNode[] => {
  const H_GAP = 240
  const V_GAP = 110
  const positions = new Map<string, { x: number; y: number }>()
  let cursorY = 0

  const place = (node: WorkflowNode, depth: number, startY: number): number => {
    const height = subtreeHeight(node)
    const y = startY + ((height - 1) * V_GAP) / 2
    positions.set(node.id, { x: depth * H_GAP, y })
    let childY = startY
    const children: Array<{ child: WorkflowNode }> =
      node.type === 'condition'
        ? [
            ...(node.thenSteps ?? []).map((child) => ({ child })),
            ...(node.elseSteps ?? []).map((child) => ({ child })),
          ]
        : node.type === 'router'
          ? (node.choices ?? []).flatMap((c) => c.steps.map((child) => ({ child })))
          : (node.steps ?? []).map((child) => ({ child }))
    for (const { child } of children) {
      const h = subtreeHeight(child)
      place(child, depth + 1, childY)
      childY += h * V_GAP
    }
    return height
  }

  for (const root of roots) {
    const h = place(root, 0, cursorY)
    cursorY += h * V_GAP + 24
  }

  const stamp = (list: WorkflowNode[]): WorkflowNode[] =>
    list.map((node) => ({
      ...node,
      position: positions.get(node.id) ?? node.position,
      steps: node.steps ? stamp(node.steps) : node.steps,
      thenSteps: node.thenSteps ? stamp(node.thenSteps) : node.thenSteps,
      elseSteps: node.elseSteps ? stamp(node.elseSteps) : node.elseSteps,
      choices: node.choices?.map((choice) => ({
        ...choice,
        steps: stamp(choice.steps),
      })),
    }))

  return stamp(roots)
}


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
    if (node.userInputSchema?.length) step.user_input_schema = node.userInputSchema
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
    userInputSchema: Array.isArray(node.user_input_schema)
      ? (node.user_input_schema as UserInputSchemaField[])
      : undefined,
    requiresOutputReview: Boolean(node.requires_output_review),
    outputReviewMessage: node.output_review_message || '',
    ...basePos,
  }
}

export const fromDefinition = (
  definition: WorkflowDefinition,
  options?: { name?: string; description?: string }
): Partial<WorkflowState> => {
  const steps = (definition.steps ?? []).map(fromDefinitionNode)
  return {
    workflowId: null,
    name: options?.name ?? definition.name ?? '',
    description: options?.description ?? definition.description ?? '',
    version: 0,
    publishedVersion: null,
    publishedAt: null,
    hasPublished: false,
    nextCronAt: null,
    steps,
    triggers: defaultTriggers(),
    selectedId: steps[0]?.id ?? null,
    dirty: true,
  }
}

export const fromRecord = (record: WorkflowRecord): Partial<WorkflowState> => {
  const steps = (record.definition?.steps ?? []).map(fromDefinitionNode)
  const publishedVersion =
    record.published_version != null ? Number(record.published_version) : null
  return {
    workflowId: record.id,
    name: record.name || record.definition?.name || '',
    description: record.description || record.definition?.description || '',
    version: Number(record.version ?? 1),
    publishedVersion,
    publishedAt: record.published_at != null ? Number(record.published_at) : null,
    hasPublished: Boolean(record.has_published) || publishedVersion != null,
    nextCronAt: record.next_cron_at != null ? Number(record.next_cron_at) : null,
    steps,
    triggers: record.triggers ?? defaultTriggers(),
    selectedId: steps[0]?.id ?? null,
    dirty: false,
  }
}

/** Absolute webhook URL for the current browser origin. */
export const workflowWebhookUrl = (workflowId: string, origin = window.location.origin) =>
  `${origin.replace(/\/$/, '')}/api/workflows/${encodeURIComponent(workflowId)}/hooks/webhook`

export const workflowWebhookCurl = (workflowId: string, secret: string, origin = window.location.origin) => {
  const url = workflowWebhookUrl(workflowId, origin)
  const sec = secret || '<secret>'
  return `curl -N -X POST '${url}?secret=${sec}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{"input":"webhook trigger"}'`
}

export const rotateWebhookSecret = () => {
  const bytes = new Uint8Array(18)
  crypto.getRandomValues(bytes)
  let bin = ''
  bytes.forEach((b) => {
    bin += String.fromCharCode(b)
  })
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Whether enabling a live trigger should be blocked/confirmed (unpublished or dirty draft). */
export const triggerEnableBlocked = (state: {
  hasPublished: boolean
  dirty: boolean
}): 'unpublished' | 'dirty' | null => {
  if (!state.hasPublished) return 'unpublished'
  if (state.dirty) return 'dirty'
  return null
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
  sourceHandle?: string
  targetHandle?: string
}

export const layoutCanvas = (
  roots: WorkflowNode[],
  options?: { forceAuto?: boolean }
): { nodes: CanvasLayoutNode[]; edges: CanvasLayoutEdge[] } => {
  const nodes: CanvasLayoutNode[] = []
  const edges: CanvasLayoutEdge[] = []
  let row = 0
  const forceAuto = Boolean(options?.forceAuto)
  const visit = (
    node: WorkflowNode,
    depth: number,
    parentId: string | null,
    edgeLabel?: string,
    edgeSourceHandle?: string
  ) => {
    const autoY = row * 90
    const autoX = depth * 220
    const x = forceAuto ? autoX : (node.position?.x ?? autoX)
    const y = forceAuto ? autoY : (node.position?.y ?? autoY)
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
        sourceHandle: edgeSourceHandle,
        targetHandle: 'in',
      })
    }
    row += 1
    if (node.type === 'condition') {
      for (const child of node.thenSteps ?? []) visit(child, depth + 1, node.id, 'then', 'then')
      for (const child of node.elseSteps ?? []) visit(child, depth + 1, node.id, 'else', 'else')
    } else if (node.type === 'router') {
      for (const choice of node.choices ?? []) {
        for (const child of choice.steps) {
          visit(child, depth + 1, node.id, choice.name, `choice:${choice.id}`)
        }
      }
    } else if (node.type === 'parallel' || node.type === 'loop') {
      for (const child of node.steps ?? []) visit(child, depth + 1, node.id, undefined, 'out')
    } else {
      for (const child of node.steps ?? []) visit(child, depth + 1, node.id, undefined, 'out')
    }
  }
  for (const root of roots) visit(root, 0, null)
  for (let i = 0; i < roots.length - 1; i += 1) {
    edges.push({
      id: `seq-${roots[i]!.id}->${roots[i + 1]!.id}`,
      source: roots[i]!.id,
      target: roots[i + 1]!.id,
      label: 'next',
      // Root sequence prefers left→right ports for Dify-like flow.
      sourceHandle: 'out-right',
      targetHandle: 'in-left',
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
