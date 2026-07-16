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
  // Note: normalizeHandleBase is defined below; call-time binding is fine.
  const handle = normalizeHandleBase(sourceHandle)

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

/** Approximate node width used for geometry-based port picking (matches .wf-flow-node). */
export const NODE_LAYOUT_WIDTH = 200

/** Approximate default node height when no type-specific estimate is available. */
export const NODE_LAYOUT_HEIGHT = 96

/**
 * Strip side aliases so semantic branch ids stay stable.
 * "then-right" → "then", "out-right" → "out", "choice:x-right" stays "choice:x".
 */
export const normalizeHandleBase = (handle: string | null | undefined): string => {
  let h = (handle || '').trim()
  if (h.endsWith('-right')) h = h.slice(0, -'-right'.length)
  if (h.endsWith('-left')) h = h.slice(0, -'-left'.length)
  return h
}

export type PortPoint = { x: number; y: number; width?: number; height?: number }

/**
 * Pick source/target handles from node geometry.
 * - Prefer left↔right when the target is clearly to the right.
 * - Otherwise use top/bottom. We only render top+left targets and bottom+right sources.
 * - Branch semantics keep the logical id (`then` / `else` / `choice:…`) and only swap the side alias.
 */
export const pickConnectionHandles = (
  source: PortPoint,
  target: PortPoint,
  logicalSourceHandle?: string | null
): { sourceHandle: string; targetHandle: string; horizontal: boolean } => {
  const sw = source.width ?? NODE_LAYOUT_WIDTH
  const sh = source.height ?? NODE_LAYOUT_HEIGHT
  const tw = target.width ?? NODE_LAYOUT_WIDTH
  const th = target.height ?? NODE_LAYOUT_HEIGHT
  const scx = source.x + sw / 2
  const scy = source.y + sh / 2
  const tcx = target.x + tw / 2
  const tcy = target.y + th / 2
  const dx = tcx - scx
  const dy = tcy - scy

  // Only use side ports when the target is to the right; we have no left source handle.
  const horizontal = dx >= 48 && Math.abs(dx) >= Math.abs(dy) * 0.85

  const base = normalizeHandleBase(logicalSourceHandle)
  const isDefaultOut = !base || base === 'out' || base === 'body' || base === 'steps'
  const sourceHandle = horizontal
    ? isDefaultOut
      ? 'out-right'
      : `${base}-right`
    : isDefaultOut
      ? 'out'
      : base
  const targetHandle = horizontal ? 'in-left' : 'in'
  return { sourceHandle, targetHandle, horizontal }
}

/** Drag smart-guide snap threshold (px, flow space) — draw.io style. */
export const SMART_SNAP_THRESHOLD = 8

export type SmartGuideBox = {
  x: number
  y: number
  width: number
  height: number
}

/** Vertical guide at x=pos, or horizontal guide at y=pos (flow coordinates). */
export type SmartGuideLine = {
  orientation: 'v' | 'h'
  pos: number
  /** Extent along the other axis for drawing. */
  start: number
  end: number
}

export type SmartSnapResult = {
  x: number
  y: number
  guides: SmartGuideLine[]
}

/**
 * Snap a dragged box to nearby peers (left/center/right × top/center/bottom).
 * Returns adjusted top-left and active guide lines for overlay rendering.
 */
type SmartAnchor = { pos: number; kind: 'start' | 'mid' | 'end' }

const smartXAnchors = (box: SmartGuideBox): SmartAnchor[] => [
  { pos: box.x, kind: 'start' },
  { pos: box.x + box.width / 2, kind: 'mid' },
  { pos: box.x + box.width, kind: 'end' },
]

const smartYAnchors = (box: SmartGuideBox): SmartAnchor[] => [
  { pos: box.y, kind: 'start' },
  { pos: box.y + box.height / 2, kind: 'mid' },
  { pos: box.y + box.height, kind: 'end' },
]

export const computeSmartSnap = (
  dragged: SmartGuideBox,
  peers: SmartGuideBox[],
  threshold = SMART_SNAP_THRESHOLD
): SmartSnapResult => {
  if (!peers.length) {
    return { x: dragged.x, y: dragged.y, guides: [] }
  }

  const peerX = peers.flatMap((p) => smartXAnchors(p).map((a) => ({ ...a, box: p })))
  const peerY = peers.flatMap((p) => smartYAnchors(p).map((a) => ({ ...a, box: p })))
  const dragX = smartXAnchors(dragged)
  const dragY = smartYAnchors(dragged)

  let bestDx: number | null = null
  let bestDxAbs = threshold + 1
  let bestXGuide: { pos: number; boxes: SmartGuideBox[] } | null = null

  for (const da of dragX) {
    for (const pa of peerX) {
      const delta = pa.pos - da.pos
      const abs = Math.abs(delta)
      if (abs <= threshold && abs < bestDxAbs) {
        bestDxAbs = abs
        bestDx = delta
        bestXGuide = { pos: pa.pos, boxes: [dragged, pa.box] }
      } else if (abs <= threshold && abs === bestDxAbs && bestDx === delta && bestXGuide) {
        if (!bestXGuide.boxes.includes(pa.box)) bestXGuide.boxes.push(pa.box)
      }
    }
  }

  let bestDy: number | null = null
  let bestDyAbs = threshold + 1
  let bestYGuide: { pos: number; boxes: SmartGuideBox[] } | null = null

  for (const da of dragY) {
    for (const pa of peerY) {
      const delta = pa.pos - da.pos
      const abs = Math.abs(delta)
      if (abs <= threshold && abs < bestDyAbs) {
        bestDyAbs = abs
        bestDy = delta
        bestYGuide = { pos: pa.pos, boxes: [dragged, pa.box] }
      } else if (abs <= threshold && abs === bestDyAbs && bestDy === delta && bestYGuide) {
        if (!bestYGuide.boxes.includes(pa.box)) bestYGuide.boxes.push(pa.box)
      }
    }
  }

  const x = bestDx != null ? dragged.x + bestDx : dragged.x
  const y = bestDy != null ? dragged.y + bestDy : dragged.y
  const snapped: SmartGuideBox = { ...dragged, x, y }
  const guides: SmartGuideLine[] = []

  const extentPad = 40
  if (bestXGuide) {
    const boxes = [...bestXGuide.boxes]
    // include snapped drag box for extent
    boxes[0] = snapped
    const tops = boxes.map((b) => b.y)
    const bottoms = boxes.map((b) => b.y + b.height)
    guides.push({
      orientation: 'v',
      pos: bestXGuide.pos,
      start: Math.min(...tops) - extentPad,
      end: Math.max(...bottoms) + extentPad,
    })
  }
  if (bestYGuide) {
    const boxes = [...bestYGuide.boxes]
    boxes[0] = snapped
    const lefts = boxes.map((b) => b.x)
    const rights = boxes.map((b) => b.x + b.width)
    guides.push({
      orientation: 'h',
      pos: bestYGuide.pos,
      start: Math.min(...lefts) - extentPad,
      end: Math.max(...rights) + extentPad,
    })
  }

  return { x, y, guides }
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

/** Estimated rendered node height (matches ~.wf-flow-node content + HITL). */
const estimateNodeHeight = (node: WorkflowNode): number => {
  let h = 96
  if (node.type === 'condition' || node.type === 'router') h = 112
  if (node.requiresConfirmation || node.requiresUserInput || node.requiresOutputReview) {
    h += 22
  }
  if ((node.instructions || '').length > 80) h += 12
  return h
}

type LayoutBranch = { child: WorkflowNode; label?: string }

const layoutChildrenOf = (node: WorkflowNode): LayoutBranch[] => {
  if (node.type === 'condition') {
    return [
      ...(node.thenSteps ?? []).map((child) => ({ child, label: 'then' as const })),
      ...(node.elseSteps ?? []).map((child) => ({ child, label: 'else' as const })),
    ]
  }
  if (node.type === 'router') {
    return (node.choices ?? []).flatMap((choice) =>
      choice.steps.map((child) => ({ child, label: choice.name }))
    )
  }
  return (node.steps ?? []).map((child) => ({ child }))
}

/**
 * Hierarchical auto-layout (pixel tree packer).
 * - Roots flow left → right (matches out-right / in-left sequence edges).
 * - Nested branches stack top → bottom with real node-height gaps (no overlap).
 * - Condition then/else and router choices get extra vertical separation.
 */
export const applyAutoLayout = (roots: WorkflowNode[]): WorkflowNode[] => {
  const COL_GAP = 280
  const ROOT_GAP = 48
  const SIBLING_GAP = 36
  const BRANCH_EXTRA = 16
  const positions = new Map<string, { x: number; y: number }>()

  /** Place node; returns pixel height of the laid-out subtree. */
  const place = (node: WorkflowNode, x: number, topY: number): number => {
    const selfH = estimateNodeHeight(node)
    const branches = layoutChildrenOf(node)
    if (!branches.length) {
      positions.set(node.id, { x, y: topY })
      return selfH
    }

    // Lay children first into a vertical block starting at topY.
    let childY = topY
    const childTops: number[] = []
    const childHeights: number[] = []
    for (let i = 0; i < branches.length; i += 1) {
      const { child, label } = branches[i]!
      const extra =
        label === 'then' || label === 'else' || Boolean(label) ? BRANCH_EXTRA : 0
      if (i > 0) childY += SIBLING_GAP + extra
      childTops.push(childY)
      const h = place(child, x + COL_GAP, childY)
      childHeights.push(h)
      childY += h
    }
    const kidsBlockH = childY - topY
    // Center parent vertically against children block.
    const parentY = topY + Math.max(0, (kidsBlockH - selfH) / 2)
    positions.set(node.id, { x, y: parentY })
    return Math.max(selfH, kidsBlockH)
  }

  // Roots: horizontal sequence.
  let cursorX = 40
  let maxBottom = 0
  for (const root of roots) {
    const h = place(root, cursorX, 40)
    maxBottom = Math.max(maxBottom, 40 + h)
    cursorX += COL_GAP + ROOT_GAP
  }

  // Safety pass: push any same-column overlaps down (defensive).
  const byCol = new Map<number, Array<{ id: string; y: number; h: number }>>()
  for (const [id, pos] of positions) {
    const node = findNode(roots, id)
    const h = node ? estimateNodeHeight(node) : 96
    const col = Math.round(pos.x / COL_GAP)
    const arr = byCol.get(col) ?? []
    arr.push({ id, y: pos.y, h })
    byCol.set(col, arr)
  }
  for (const arr of byCol.values()) {
    arr.sort((a, b) => a.y - b.y)
    let floor = -Infinity
    for (const item of arr) {
      if (item.y < floor) {
        item.y = floor
        positions.set(item.id, {
          x: positions.get(item.id)!.x,
          y: item.y,
        })
      }
      floor = item.y + item.h + SIBLING_GAP
    }
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
  if (node.skills?.length) {
    step.skills = [...node.skills]
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
    skills: Array.isArray(node.skills) ? node.skills.map(String).filter(Boolean) : [],
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
    edgeSourceHandle?: string,
    rootIndex = 0
  ) => {
    // Roots without saved positions flow left→right; nested use depth/row fallback.
    const autoY = parentId == null ? 40 : row * 90
    const autoX = parentId == null ? rootIndex * 280 : depth * 220
    const x = forceAuto ? (parentId == null ? rootIndex * 280 : depth * 220) : (node.position?.x ?? autoX)
    const y = forceAuto ? (parentId == null ? 40 : row * 90) : (node.position?.y ?? autoY)
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
        // Logical handle only; geometry pass below picks side vs top/bottom.
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
  for (let i = 0; i < roots.length; i += 1) visit(roots[i]!, 0, null, undefined, undefined, i)
  for (let i = 0; i < roots.length - 1; i += 1) {
    edges.push({
      id: `seq-${roots[i]!.id}->${roots[i + 1]!.id}`,
      source: roots[i]!.id,
      target: roots[i + 1]!.id,
      label: 'next',
      sourceHandle: 'out',
      targetHandle: 'in',
    })
  }

  // Geometry-aware ports: L/R when target is to the right, else top/bottom.
  const byId = new Map(nodes.map((n) => [n.id, n]))
  for (const edge of edges) {
    const src = byId.get(edge.source)
    const tgt = byId.get(edge.target)
    if (!src || !tgt) continue
    const picked = pickConnectionHandles(
      { x: src.x, y: src.y },
      { x: tgt.x, y: tgt.y },
      edge.sourceHandle
    )
    edge.sourceHandle = picked.sourceHandle
    edge.targetHandle = picked.targetHandle
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
    `# Compiled from workbench workflow definition`,
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
