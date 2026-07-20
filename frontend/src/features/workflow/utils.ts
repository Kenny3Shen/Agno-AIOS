/**
 * Pure helpers for Workflow Studio.
 *
 * Includes: DSL create/normalize, canvas layout, smart-snap guides,
 * reparent rules, and client-side validation.
 * No React hooks and no network — safe to unit test in isolation.
 */
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
      name: '',
      steps: [],
    }
  }
  if (type === 'condition') {
    return {
      id,
      type: 'condition',
      name: '',
      evaluatorCel: 'input.contains("critical")',
      thenSteps: [],
      elseSteps: [],
    }
  }
  if (type === 'loop') {
    return {
      id,
      type: 'loop',
      name: '',
      maxIterations: 3,
      endConditionCel: 'current_iteration >= 1',
      steps: [],
    }
  }
  if (type === 'router') {
    return {
      id,
      type: 'router',
      name: '',
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
      name: '',
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

/** Materialize a business/custom step preset into a canvas node. */
export const createNodeFromPreset = (
  preset: {
    name: string
    definition: {
      name?: string
      executor?: { ref?: string }
      instructions?: string
      skills?: string[]
      requires_confirmation?: boolean
      confirmation_message?: string
      requires_user_input?: boolean
      user_input_message?: string
      user_input_schema?: WorkflowNode['userInputSchema']
      requires_output_review?: boolean
      output_review_message?: string
    }
  },
): WorkflowNode => {
  const def = preset.definition
  const node = createNode('step')
  return {
    ...node,
    name: (def.name || preset.name || '').trim(),
    kind: 'agent',
    targetId: def.executor?.ref || 'security-operations',
    instructions: def.instructions || '',
    skills: Array.isArray(def.skills) ? def.skills.map(String).filter(Boolean) : [],
    requiresConfirmation: Boolean(def.requires_confirmation),
    confirmationMessage: def.confirmation_message || '',
    requiresUserInput: Boolean(def.requires_user_input),
    userInputMessage: def.user_input_message || '',
    userInputSchema: def.user_input_schema,
    requiresOutputReview: Boolean(def.requires_output_review),
    outputReviewMessage: def.output_review_message || '',
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

type BranchKey = 'steps' | 'thenSteps' | 'elseSteps'

export type ReparentTarget =
  | { kind: 'root'; index?: number }
  | { kind: 'branch'; parentId: string; branch: BranchKey }
  | { kind: 'choice'; parentId: string; choiceId: string }

export type EmptySlot = {
  key: string
  /** i18n key under workflow namespace (or literal for router path name via params). */
  labelKey: string
  labelParams?: Record<string, string>
  branch?: BranchKey
  choiceId?: string
}

export const isContainerType = (type: WorkflowNodeType): boolean =>
  type === 'parallel' || type === 'condition' || type === 'loop' || type === 'router'

const collectNodeIds = (nodes: WorkflowNode[]): string[] => {
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

/** True if this node or any nested step requests HITL. */
export const nodeTreeHasHitl = (node: WorkflowNode): boolean => {
  if (node.requiresConfirmation || node.requiresUserInput || node.requiresOutputReview) {
    return true
  }
  return collectNodeIds([node]).some((id) => {
    if (id === node.id) return false
    const nested = findNode([node], id)
    return Boolean(
      nested?.requiresConfirmation || nested?.requiresUserInput || nested?.requiresOutputReview,
    )
  })
}

/**
 * Locate a node among roots or nested branches.
 * Returns parent context for sibling insertion (root / branch / choice).
 */
export type NodeLocation =
  | { kind: 'root'; index: number }
  | { kind: 'branch'; parentId: string; branch: BranchKey; index: number }
  | { kind: 'choice'; parentId: string; choiceId: string; index: number }

export const locateNode = (nodes: WorkflowNode[], id: string): NodeLocation | null => {
  const rootIndex = nodes.findIndex((node) => node.id === id)
  if (rootIndex >= 0) return { kind: 'root', index: rootIndex }

  const walk = (list: WorkflowNode[]): NodeLocation | null => {
    for (const node of list) {
      if (node.steps) {
        const idx = node.steps.findIndex((child) => child.id === id)
        if (idx >= 0) {
          return { kind: 'branch', parentId: node.id, branch: 'steps', index: idx }
        }
        const nested = walk(node.steps)
        if (nested) return nested
      }
      if (node.thenSteps) {
        const idx = node.thenSteps.findIndex((child) => child.id === id)
        if (idx >= 0) {
          return { kind: 'branch', parentId: node.id, branch: 'thenSteps', index: idx }
        }
        const nested = walk(node.thenSteps)
        if (nested) return nested
      }
      if (node.elseSteps) {
        const idx = node.elseSteps.findIndex((child) => child.id === id)
        if (idx >= 0) {
          return { kind: 'branch', parentId: node.id, branch: 'elseSteps', index: idx }
        }
        const nested = walk(node.elseSteps)
        if (nested) return nested
      }
      for (const choice of node.choices ?? []) {
        const idx = choice.steps.findIndex((child) => child.id === id)
        if (idx >= 0) {
          return { kind: 'choice', parentId: node.id, choiceId: choice.id, index: idx }
        }
        const nested = walk(choice.steps)
        if (nested) return nested
      }
    }
    return null
  }
  return walk(nodes)
}

/** True when `nodeId` is nested under any Parallel (including itself). */
export const isInsideParallel = (nodes: WorkflowNode[], nodeId: string): boolean => {
  const self = findNode(nodes, nodeId)
  if (self?.type === 'parallel') return true
  let current: string | null = nodeId
  const seen = new Set<string>()
  while (current && !seen.has(current)) {
    seen.add(current)
    const location = locateNode(nodes, current)
    if (!location || location.kind === 'root') return false
    const parent = findNode(nodes, location.parentId)
    if (!parent) return false
    if (parent.type === 'parallel') return true
    current = parent.id
  }
  return false
}

/** Insert a child after the given location index (or append when index is last). */
const insertAfterLocation = (
  nodes: WorkflowNode[],
  location: NodeLocation,
  child: WorkflowNode,
): WorkflowNode[] => {
  if (location.kind === 'root') {
    const next = [...nodes]
    next.splice(location.index + 1, 0, child)
    return next
  }
  if (location.kind === 'choice') {
    return updateNodeInTree(nodes, location.parentId, (parent) => {
      if (parent.type !== 'router') return parent
      return {
        ...parent,
        choices: (parent.choices ?? []).map((choice) => {
          if (choice.id !== location.choiceId) return choice
          const steps = [...choice.steps]
          steps.splice(location.index + 1, 0, child)
          return { ...choice, steps }
        }),
      }
    })
  }
  return updateNodeInTree(nodes, location.parentId, (parent) => {
    const current = [...(parent[location.branch] ?? [])]
    current.splice(location.index + 1, 0, child)
    return { ...parent, [location.branch]: current }
  })
}

/** Deep-clone a node tree with fresh ids (for copy/paste). */
export const cloneNodeDeep = (node: WorkflowNode): WorkflowNode => {
  const id = crypto.randomUUID()
  const base: WorkflowNode = {
    ...node,
    id,
    position: node.position ? { ...node.position } : undefined,
    skills: node.skills ? [...node.skills] : node.skills,
    userInputSchema: node.userInputSchema
      ? node.userInputSchema.map((field) => ({ ...field }))
      : node.userInputSchema,
  }
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
const extractNode = (
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

export type ReparentBlockedReason = 'cycle' | 'hitl_in_parallel' | 'invalid'

type ReparentOutcome = {
  steps: WorkflowNode[]
  blocked?: ReparentBlockedReason
}

/**
 * Move `nodeId` under a container (or to root). Blocks cycles and HITL-in-Parallel.
 */
export const reparentNode = (
  nodes: WorkflowNode[],
  nodeId: string,
  target: ReparentTarget
): ReparentOutcome => {
  if (target.kind !== 'root' && target.parentId === nodeId) {
    return { steps: nodes, blocked: 'cycle' }
  }
  if (target.kind !== 'root' && isDescendantOf(nodes, nodeId, target.parentId)) {
    return { steps: nodes, blocked: 'cycle' }
  }

  const { node, remaining } = extractNode(nodes, nodeId)
  if (!node) return { steps: nodes, blocked: 'invalid' }

  if (target.kind !== 'root') {
    const parent = findNode(remaining, target.parentId) ?? findNode(nodes, target.parentId)
    if (!parent || !isContainerType(parent.type)) {
      return { steps: nodes, blocked: 'invalid' }
    }
    // Agno: no HITL inside Parallel
    if (parent.type === 'parallel' && nodeTreeHasHitl(node)) {
      return { steps: nodes, blocked: 'hitl_in_parallel' }
    }
  }

  return { steps: insertChild(remaining, target, node) }
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
      { id: 'then', label: 'branchThen' },
      { id: 'else', label: 'branchElse' },
    ]
  }
  if (node.type === 'router') {
    return (node.choices ?? []).map((choice) => ({
      id: `choice:${choice.id}`,
      label: choice.name || 'defaultPathName',
    }))
  }
  if (node.type === 'parallel') {
    return [{ id: 'out', label: 'branchOut' }]
  }
  if (node.type === 'loop') {
    return [{ id: 'out', label: 'branchBody' }]
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
const normalizeHandleBase = (handle: string | null | undefined): string => {
  let h = (handle || '').trim()
  if (h.endsWith('-right')) h = h.slice(0, -'-right'.length)
  if (h.endsWith('-left')) h = h.slice(0, -'-left'.length)
  return h
}

type PortPoint = { x: number; y: number; width?: number; height?: number }

/**
 * Pick source/target handles from node geometry.
 * - Prefer left↔right when the target is clearly to the right.
 * - Otherwise use top/bottom. We only render top+left targets and bottom+right sources.
 * - Branch semantics keep the logical id (`then` / `else` / `choice:…`) and only swap the side alias.
 */
const pickConnectionHandles = (
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
const SMART_SNAP_THRESHOLD = 8

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

type SmartSnapResult = {
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
    return [{ key: 'steps', labelKey: 'slotAddBranch', branch: 'steps' }]
  }
  if (node.type === 'loop') {
    if ((node.steps ?? []).length) return []
    return [{ key: 'steps', labelKey: 'slotAddBodyStep', branch: 'steps' }]
  }
  if (node.type === 'condition') {
    const slots: EmptySlot[] = []
    if (!(node.thenSteps ?? []).length) {
      slots.push({ key: 'thenSteps', labelKey: 'slotAddThen', branch: 'thenSteps' })
    }
    if (!(node.elseSteps ?? []).length) {
      slots.push({ key: 'elseSteps', labelKey: 'slotAddElse', branch: 'elseSteps' })
    }
    return slots
  }
  if (node.type === 'router') {
    return (node.choices ?? [])
      .filter((c) => c.steps.length === 0)
      .map((c) => {
        const name = (c.name || '').trim()
        return {
          key: `choice:${c.id}`,
          labelKey: name ? 'slotAddPath' : 'slotAddPathDefault',
          labelParams: name ? { name } : undefined,
          choiceId: c.id,
        }
      })
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

/** Map a validation issue to an inspector field key for scroll/focus. */
export const fieldForValidationIssue = (issue: Pick<WorkflowValidationIssue, 'code'>): string => {
  switch (issue.code) {
    case 'missing_executor':
      return 'executor'
    case 'user_input_schema_empty':
    case 'user_input_schema_field':
      return 'userInput'
    case 'empty_name':
      return 'workflowName'
    case 'empty_condition_cel':
      return 'evaluator'
    case 'empty_router_cel':
      return 'selector'
    case 'missing_workflow_ref':
    case 'self_workflow_ref':
      return 'workflow_ref'
    case 'empty_parallel':
    case 'empty_loop':
    case 'empty_condition':
    case 'empty_router':
    case 'empty_router_choice':
      return 'children'
    case 'hitl_in_parallel':
      return 'hitl'
    default:
      return 'name'
  }
}

/** Internal layout/debug label (canvas display uses i18n + executor names). */
const nodeLabel = (node: WorkflowNode): string => {
  if (node.name?.trim()) return node.name.trim()
  switch (node.type) {
    case 'step':
      return 'Agent step'
    case 'workflow_ref':
      return 'Nested workflow'
    case 'parallel':
      return 'Parallel'
    case 'condition':
      return 'Condition'
    case 'loop':
      return 'Loop'
    case 'router':
      return 'Router'
    default:
      return node.type
  }
}

/** Client-side save checks (mirrors compiler empty-branch rules). */
export type WorkflowValidationTranslate = (
  key: string,
  options?: Record<string, string | number>,
) => string

/** Optional translator; falls back to English keys when omitted (tests). */
export const validateWorkflowDraft = (
  roots: WorkflowNode[],
  t: WorkflowValidationTranslate = (key, options) => {
    const path = String(options?.path ?? '')
    const choice = String(options?.choice ?? '')
    switch (key) {
      case 'validationEmptyWorkflow':
        return 'Add at least one node before saving'
      case 'validationEmptyParallel':
        return `${path}: Parallel needs at least one branch`
      case 'validationEmptyLoop':
        return `${path}: Loop body is empty`
      case 'validationEmptyCondition':
        return `${path}: Condition needs then and/or else steps`
      case 'validationEmptyRouter':
        return `${path}: Router has no choices`
      case 'validationEmptyRouterChoice':
        return `${path}: choice "${choice}" is empty`
      case 'validationMissingWorkflowRef':
        return `${path}: Nested workflow id is required`
      case 'validationMissingExecutor':
        return `${path}: Agent executor is required`
      case 'validationUserInputSchemaEmpty':
        return `${path}: user input needs at least one named field`
      case 'validationUserInputSchemaField':
        return `${path}: field #${options?.index ?? ''} needs a name`
      case 'validationEmptyName':
        return 'Workflow name is required'
      case 'validationEmptyConditionCel':
        return `${path}: condition expression is required`
      case 'validationEmptyRouterCel':
        return `${path}: router expression is required`
      case 'validationSelfWorkflowRef':
        return `${path}: nested workflow cannot reference itself`
      case 'validationHitlInParallel':
        return `${path}: step HITL is not allowed inside Parallel`
      default:
        return key
    }
  },
  currentWorkflowId: string | null = null,
): WorkflowValidationIssue[] => {
  const issues: WorkflowValidationIssue[] = []
  if (!roots.length) {
    issues.push({
      nodeId: null,
      code: 'empty_workflow',
      message: t('validationEmptyWorkflow'),
    })
    return issues
  }

  const walk = (nodes: WorkflowNode[], path: string, insideParallel = false) => {
    for (const node of nodes) {
      const label = node.name?.trim() || nodeLabel(node)
      const here = `${path}/${label}`
      const nestedParallel = insideParallel || node.type === 'parallel'
      if (
        node.type === 'step' &&
        insideParallel &&
        (node.requiresConfirmation || node.requiresUserInput || node.requiresOutputReview)
      ) {
        issues.push({
          nodeId: node.id,
          code: 'hitl_in_parallel',
          message: t('validationHitlInParallel', { path: here }),
        })
      }
      if (node.type === 'parallel') {
        if (!(node.steps ?? []).length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_parallel',
            message: t('validationEmptyParallel', { path: here }),
          })
        }
      }
      if (node.type === 'loop') {
        if (!(node.steps ?? []).length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_loop',
            message: t('validationEmptyLoop', { path: here }),
          })
        }
      }
      if (node.type === 'condition') {
        if (!(node.thenSteps ?? []).length && !(node.elseSteps ?? []).length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_condition',
            message: t('validationEmptyCondition', { path: here }),
          })
        }
        if (!(node.evaluatorCel || '').trim()) {
          issues.push({
            nodeId: node.id,
            code: 'empty_condition_cel',
            message: t('validationEmptyConditionCel', { path: here }),
          })
        }
      }
      if (node.type === 'router') {
        if (!(node.selectorCel || '').trim()) {
          issues.push({
            nodeId: node.id,
            code: 'empty_router_cel',
            message: t('validationEmptyRouterCel', { path: here }),
          })
        }
        const choices = node.choices ?? []
        if (!choices.length) {
          issues.push({
            nodeId: node.id,
            code: 'empty_router',
            message: t('validationEmptyRouter', { path: here }),
          })
        }
        for (const choice of choices) {
          if (!choice.steps.length) {
            issues.push({
              nodeId: node.id,
              code: 'empty_router_choice',
              message: t('validationEmptyRouterChoice', {
                path: here,
                choice: choice.name || choice.id,
              }),
            })
          }
        }
      }
      if (node.type === 'workflow_ref') {
        const nestedId = (node.workflowId || '').trim()
        if (!nestedId) {
          issues.push({
            nodeId: node.id,
            code: 'missing_workflow_ref',
            message: t('validationMissingWorkflowRef', { path: here }),
          })
        } else if (currentWorkflowId && nestedId === currentWorkflowId) {
          issues.push({
            nodeId: node.id,
            code: 'self_workflow_ref',
            message: t('validationSelfWorkflowRef', { path: here }),
          })
        }
      }
      if (node.type === 'step' && !(node.targetId || '').trim()) {
        issues.push({
          nodeId: node.id,
          code: 'missing_executor',
          message: t('validationMissingExecutor', { path: here }),
        })
      }
      if (node.type === 'step' && node.requiresUserInput) {
        const schema = node.userInputSchema ?? []
        const named = schema.filter((field) => (field.name || '').trim())
        if (!named.length) {
          issues.push({
            nodeId: node.id,
            code: 'user_input_schema_empty',
            message: t('validationUserInputSchemaEmpty', { path: here }),
          })
        } else {
          schema.forEach((field, index) => {
            if (!(field.name || '').trim()) {
              issues.push({
                nodeId: node.id,
                code: 'user_input_schema_field',
                message: t('validationUserInputSchemaField', {
                  path: here,
                  index: index + 1,
                }),
              })
            }
          })
        }
      }
      for (const list of [node.steps, node.thenSteps, node.elseSteps]) {
        if (list?.length) walk(list, here, nestedParallel)
      }
      for (const choice of node.choices ?? []) {
        if (choice.steps.length) {
          walk(choice.steps, `${here}/${choice.name || 'choice'}`, nestedParallel)
        }
      }
    }
  }
  walk(roots, 'workflow')
  return issues
}

export const validateWorkflowName = (
  name: string,
  t: WorkflowValidationTranslate = (key) =>
    key === 'validationEmptyName' ? 'Workflow name is required' : key,
): WorkflowValidationIssue | null => {
  if (name.trim()) return null
  return {
    nodeId: null,
    code: 'empty_name',
    message: t('validationEmptyName'),
  }
}

/** Estimated rendered node height (matches ~.wf-flow-node content + badges). */
const estimateNodeHeight = (node: WorkflowNode): number => {
  let h = 96
  if (node.type === 'condition' || node.type === 'router') h = 112
  if (node.requiresConfirmation || node.requiresUserInput || node.requiresOutputReview) {
    h += 22
  }
  // Skill chips and empty-slot CTAs grow the card beyond the base estimate.
  const skillCount = Array.isArray(node.skills) ? node.skills.length : 0
  if (skillCount > 0) h += 18
  if ((node.instructions || '').length > 80) h += 12
  if ((node.name || '').length > 28) h += 10
  // Container types show empty-slot CTAs when a branch has no children.
  if (node.type === 'condition') {
    if (!(node.thenSteps?.length)) h += 28
    if (!(node.elseSteps?.length)) h += 28
  } else if (node.type === 'router') {
    const emptyChoices = (node.choices ?? []).filter((c) => !(c.steps?.length)).length
    h += emptyChoices * 24
  } else if (node.type === 'parallel' || node.type === 'loop') {
    if (!(node.steps?.length)) h += 28
  }
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
      name: node.name || '',
      steps: (node.steps ?? []).map(toDefinitionNode),
      ...basePos,
    }
  }
  if (node.type === 'condition') {
    return {
      id: node.id,
      type: 'condition',
      name: node.name || '',
      evaluator: { cel: node.evaluatorCel || 'true' },
      steps: (node.thenSteps ?? []).map(toDefinitionNode),
      else: (node.elseSteps ?? []).map(toDefinitionNode),
      ...basePos,
    }
  }
  if (node.type === 'loop') {
    return {
      id: node.id,
      type: 'loop',
      name: node.name || '',
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
      name: node.name || '',
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
      name: node.name || '',
      workflow_id: node.workflowId || '',
      ...basePos,
    }
  }
  const step: WorkflowDefinitionNode = {
    id: node.id,
    type: 'step',
    name: (node.name || '').trim(),
    executor: { kind: 'agent', ref: node.targetId || '' },
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
  name: state.name || '',
  description: state.description || '',
  steps: state.steps.map(toDefinitionNode),
})

const fromDefinitionNode = (node: WorkflowDefinitionNode): WorkflowNode => {
  const position = node.position
  const basePos = position ? { position: { x: position.x, y: position.y } } : {}
  if (node.type === 'parallel') {
    return {
      id: node.id,
      type: 'parallel',
      name: node.name || '',
      steps: (node.steps ?? []).map(fromDefinitionNode),
      ...basePos,
    }
  }
  if (node.type === 'condition') {
    return {
      id: node.id,
      type: 'condition',
      name: node.name || '',
      evaluatorCel: node.evaluator?.cel || (node.evaluator?.value === false ? 'false' : 'true'),
      thenSteps: (node.steps ?? []).map(fromDefinitionNode),
      elseSteps: (node.else ?? []).map(fromDefinitionNode),
      ...basePos,
    }
  }
  if (node.type === 'loop') {
    return {
      id: node.id,
      type: 'loop',
      name: node.name || '',
      maxIterations: node.max_iterations ?? 3,
      endConditionCel: node.end_condition?.cel || '',
      steps: (node.steps ?? []).map(fromDefinitionNode),
      ...basePos,
    }
  }
  if (node.type === 'router') {
    return {
      id: node.id,
      type: 'router',
      name: node.name || '',
      selectorCel: node.selector?.cel || '',
      choices: (node.choices ?? []).map((choice) => ({
        id: choice.id,
        name: choice.name,
        steps: (choice.steps ?? []).map(fromDefinitionNode),
      })),
      ...basePos,
    }
  }
  if (node.type === 'workflow_ref') {
    return {
      id: node.id,
      type: 'workflow_ref',
      name: node.name || '',
      workflowId: node.workflow_id || '',
      ...basePos,
    }
  }
  return {
    id: node.id,
    type: 'step',
    kind: 'agent',
    targetId: node.executor?.ref || '',
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


/** Keep multi/single selection when a saved record reloads steps (e.g. mid-run save). */
export const preserveSelectionAfterReload = (
  steps: WorkflowNode[],
  selectedId: string | null | undefined,
  selectedIds: string[] | undefined,
  fallbackId: string | null | undefined,
): { selectedId: string | null; selectedIds: string[] } => {
  const keep = (selectedIds ?? []).filter((id) => Boolean(findNode(steps, id)))
  if (keep.length) {
    const primary =
      selectedId && keep.includes(selectedId) ? selectedId : keep[0] ?? null
    return { selectedId: primary, selectedIds: keep }
  }
  if (selectedId && findNode(steps, selectedId)) {
    return { selectedId, selectedIds: [selectedId] }
  }
  const fallback = fallbackId && findNode(steps, fallbackId) ? fallbackId : null
  return { selectedId: fallback, selectedIds: fallback ? [fallback] : [] }
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

/** Resolve canvas subtitle for a node (executor display name when available). */
type CanvasSubtitleT = (key: string, options?: Record<string, unknown>) => string

export const resolveNodeCanvasSubtitle = (
  node: WorkflowNode,
  t: CanvasSubtitleT,
  executorNames: ReadonlyMap<string, string> | Record<string, string> = {},
): string => {
  if (node.type === 'step') {
    const ref = (node.targetId || '').trim()
    if (!ref) return t('subtitleAgent')
    let mapped: string | undefined
    if (executorNames instanceof Map) {
      mapped = executorNames.get(ref)
    } else {
      mapped = (executorNames as Record<string, string>)[ref]
    }
    const name = (mapped || '').trim()
    return name || ref
  }
  if (node.type === 'condition') return node.evaluatorCel || 'CEL'
  if (node.type === 'router') return node.selectorCel || 'selector'
  if (node.type === 'workflow_ref') return node.workflowId || t('subtitleNested')
  if (node.type === 'loop') return t('subtitleMaxIter', { count: node.maxIterations ?? 3 })
  if (node.type === 'parallel') return t('subtitleBranches', { count: node.steps?.length ?? 0 })
  return node.type
}

/** Stable key fragment for executor catalog (drives presentation refresh). */
export const executorNamesKey = (
  executorNames: ReadonlyMap<string, string> | Record<string, string>,
): string => {
  const entries =
    executorNames instanceof Map
      ? [...executorNames.entries()]
      : Object.entries(executorNames as Record<string, string>)
  return entries
    .map(([ref, name]) => `${ref}=${name}`)
    .sort()
    .join('|')
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
    const thenSteps = (node.steps ?? []).map((child) => emitCodeNode(child, indent + '    ')).join(',\n')
    const elseSteps = (node.else ?? []).map((child) => emitCodeNode(child, indent + '    ')).join(',\n')
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
    `agent=agents[${JSON.stringify(node.executor?.ref ?? '')}], ` +
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

type MultiSelectAgentSummary = {
  agentCount: number
  sharedTargetId: string | undefined
  skillsMixed: boolean
  sharedSkills: string[]
  instructionsMixed: boolean
  sharedInstructions: string
  allConfirm: boolean
  noneConfirm: boolean
  allUserInput: boolean
  noneUserInput: boolean
  allOutputReview: boolean
  noneOutputReview: boolean
}

const skillKey = (skills: string[] | undefined) =>
  JSON.stringify([...(skills ?? [])].map(String).sort())

/** Derive multi-select Inspector controls from currently selected Agent steps. */
export const summarizeSelectedAgentSteps = (
  agentSteps: WorkflowNode[],
): MultiSelectAgentSummary => {
  const agentCount = agentSteps.length
  const first = agentSteps[0]
  const sharedTargetId =
    agentCount > 0 && agentSteps.every((node) => node.targetId === first?.targetId)
      ? first?.targetId
      : undefined
  const skillsMixed =
    agentCount > 0 &&
    !agentSteps.every((node) => skillKey(node.skills) === skillKey(first?.skills))
  const sharedSkills = skillsMixed ? [] : [...(first?.skills ?? [])]
  const instructionsMixed =
    agentCount > 0 &&
    !agentSteps.every((node) => (node.instructions ?? '') === (first?.instructions ?? ''))
  const sharedInstructions = instructionsMixed ? '' : (first?.instructions ?? '')
  return {
    agentCount,
    sharedTargetId,
    skillsMixed,
    sharedSkills,
    instructionsMixed,
    sharedInstructions,
    allConfirm: agentCount > 0 && agentSteps.every((node) => node.requiresConfirmation),
    noneConfirm: agentCount > 0 && agentSteps.every((node) => !node.requiresConfirmation),
    allUserInput: agentCount > 0 && agentSteps.every((node) => node.requiresUserInput),
    noneUserInput: agentCount > 0 && agentSteps.every((node) => !node.requiresUserInput),
    allOutputReview: agentCount > 0 && agentSteps.every((node) => node.requiresOutputReview),
    noneOutputReview: agentCount > 0 && agentSteps.every((node) => !node.requiresOutputReview),
  }
}

type PasteSelectionResult = {
  steps: WorkflowNode[]
  /** Clones that could not enter Parallel because of HITL (appended at root). */
  divertedHitlCount: number
  /** Multi-select (2+) forces root append; single-select pastes into/after the host. */
  multiSelectRootPaste: boolean
}

/**
 * Insert cloned nodes relative to the current selection:
 * - single container selected → default empty/primary branch
 * - single non-container selected → sibling after that node
 * - multi-select / none → append at roots
 *
 * Parallel never receives HITL trees (Agno constraint); those clones fall back to root.
 */
export const pasteNodesIntoSelection = (
  steps: WorkflowNode[],
  clones: WorkflowNode[],
  selectedIds: string[],
  selectedId: string | null,
): PasteSelectionResult => {
  if (!clones.length) return { steps, divertedHitlCount: 0, multiSelectRootPaste: false }
  const soleId =
    selectedIds.length === 1
      ? selectedIds[0]
      : selectedId && selectedIds.length <= 1
        ? selectedId
        : null
  const host = soleId ? findNode(steps, soleId) : null

  // Multi-select or empty selection: root append.
  if (!host) {
    return {
      steps: [...steps, ...clones],
      divertedHitlCount: 0,
      multiSelectRootPaste: selectedIds.length > 1,
    }
  }

  // Container: paste into default slot (then/else/steps/choice).
  if (isContainerType(host.type)) {
    const drop = defaultDropTarget(host)
    if (!drop || drop.kind === 'root') {
      return { steps: [...steps, ...clones], divertedHitlCount: 0, multiSelectRootPaste: false }
    }
    const intoParallel = isInsideParallel(steps, host.id)

    let next = steps
    const rootFallback: WorkflowNode[] = []
    for (const clone of clones) {
      if (clone.id === drop.parentId) continue
      if (isDescendantOf([clone], drop.parentId, clone.id)) continue
      if (intoParallel && nodeTreeHasHitl(clone)) {
        rootFallback.push(clone)
        continue
      }
      next = insertChild(next, drop, clone)
    }
    return {
      steps: rootFallback.length ? [...next, ...rootFallback] : next,
      divertedHitlCount: rootFallback.length,
      multiSelectRootPaste: false,
    }
  }

  // Non-container: insert as siblings after the selected node.
  const location = locateNode(steps, host.id)
  if (!location) {
    return { steps: [...steps, ...clones], divertedHitlCount: 0, multiSelectRootPaste: false }
  }

  // Sibling under a Parallel (or deeper) cannot receive HITL trees.
  const siblingUnderParallel = isInsideParallel(steps, host.id)

  let next = steps
  const rootFallback: WorkflowNode[] = []
  // insertAfterLocation shifts indexes; insert in reverse so order is preserved.
  const ordered = [...clones].reverse()
  for (const clone of ordered) {
    if (siblingUnderParallel && nodeTreeHasHitl(clone)) {
      rootFallback.push(clone)
      continue
    }
    next = insertAfterLocation(next, location, clone)
  }
  // rootFallback was collected in reverse order too
  rootFallback.reverse()
  return {
    steps: rootFallback.length ? [...next, ...rootFallback] : next,
    divertedHitlCount: rootFallback.length,
    multiSelectRootPaste: false,
  }
}
