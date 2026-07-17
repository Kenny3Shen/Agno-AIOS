import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'
import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { getModels } from '@/features/settings/api'
import { ApiError } from '@/shared/api/client'
import {
  createWorkflow,
  deleteWorkflow,
  listExecutors,
  listWorkflowVersions,
  getWorkflow,
  listWorkflows,
  listWorkflowTemplates,
  restoreWorkflowVersion,
  publishWorkflow,
  cancelWorkflowRun,
  streamWorkflowRun,
  updateWorkflow,
} from './api'
import type {
  WorkflowNode,
  WorkflowNodeType,
  WorkflowRunHistoryItem,
  WorkflowRunLogItem,
  WorkflowState,
  WorkflowTriggers,
} from './types'
import {
  appendRunLog,
  applyNodeRunStatusEvent,
  historyStatusFromEvent,
  historySummaryFromEvent,
} from './runStatus'
import {
  addChildToNode,
  applyAutoLayout,
  cloneNodeDeep,
  createNode,
  defaultTriggers,
  findNode,
  fromDefinition,
  fromRecord,
  insertChild,
  isInsideParallel,
  locateNode,
  pasteNodesIntoSelection,
  triggerEnableBlocked,
  moveNodeAfter,
  moveStep,
  parseEmptySlot,
  removeNodeInTree,
  removeNodesInTree,
  reparentNode,
  reparentTargetFromHandle,
  toDefinition,
  updateNodeInTree,
  validateWorkflowDraft,
  validateWorkflowName,
  type ReparentTarget,
  type ReparentBlockedReason,
} from './utils'

const HISTORY_LIMIT = 40

type HistorySnap = {
  steps: WorkflowNode[]
  selectedId: string | null
  selectedIds: string[]
}

const initialState = (): WorkflowState => ({
  workflowId: null,
  name: '',
  description: '',
  input: '',
  sessionId: crypto.randomUUID(),
  modelId: null,
  version: 0,
  publishedVersion: null,
  publishedAt: null,
  hasPublished: false,
  nextCronAt: null,
  steps: [],
  triggers: defaultTriggers(),
  selectedId: null,
  selectedIds: [],
  dirty: false,
  loading: false,
  saving: false,
  running: false,
  runLog: [],
  nodeRunStatus: {},
  runHistory: [],
  error: null,
  validationIssues: [],
  validationEpoch: 0,
  focusEpoch: 0,
  lastRunId: null,
  lastSessionId: null,
  lastApprovalId: null,
})

const snapOf = (state: Pick<WorkflowState, 'steps' | 'selectedId' | 'selectedIds'>): HistorySnap => ({
  steps: structuredClone(state.steps),
  selectedId: state.selectedId,
  selectedIds: [...state.selectedIds],
})

export function useWorkflow() {
  const { t } = useTranslation('workflow')
  const [state, setState] = useState<WorkflowState>(initialState)
  const abortRef = useRef<AbortController | null>(null)
  const pastRef = useRef<HistorySnap[]>([])
  const futureRef = useRef<HistorySnap[]>([])
  const clipboardRef = useRef<WorkflowNode[]>([])
  const [historyTick, setHistoryTick] = useState(0)
  const [librarySearch, setLibrarySearch] = useState('')
  const debouncedLibrarySearch = useDebouncedValue(librarySearch, 300)

  const workflowsQuery = useInfiniteQuery({
    queryKey: ['workflows', 'list', debouncedLibrarySearch.trim()],
    queryFn: ({ pageParam }) => listWorkflows(pageParam, 100, debouncedLibrarySearch.trim()),
    initialPageParam: 1,
    placeholderData: keepPreviousData,
    getNextPageParam: (lastPage) => {
      const page = lastPage.meta.page
      const limit = Math.max(1, lastPage.meta.limit)
      const totalPages = lastPage.meta.total_pages
      const totalCount = lastPage.meta.total_count
      if (totalPages > 0) return page < totalPages ? page + 1 : undefined
      if (totalCount > 0) {
        const loadedApprox = (page - 1) * limit + lastPage.data.length
        return loadedApprox < totalCount ? page + 1 : undefined
      }
      // Fallback when meta totals missing: full page implies another may exist.
      if (lastPage.data.length >= limit) return page + 1
      return undefined
    },
  })
  const workflowRecords = workflowsQuery.data?.pages.flatMap((page) => page.data) ?? []
  const workflowListMeta = workflowsQuery.data?.pages.at(-1)?.meta
  const executorsQuery = useQuery({
    queryKey: ['workflows', 'executors'],
    queryFn: listExecutors,
  })
  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: getModels,
  })
  const versionsQuery = useQuery({
    queryKey: ['workflows', 'versions', state.workflowId],
    queryFn: () => listWorkflowVersions(state.workflowId!),
    enabled: Boolean(state.workflowId),
  })
  const templatesQuery = useQuery({
    queryKey: ['workflows', 'templates'],
    queryFn: listWorkflowTemplates,
  })

  useEffect(() => {
    const active = modelsQuery.data?.active_model_id
    if (active && !state.modelId) {
      setState((current) => ({ ...current, modelId: active }))
    }
  }, [modelsQuery.data?.active_model_id, state.modelId])

  const bumpHistory = () => setHistoryTick((n) => n + 1)

  const pushHistory = useCallback((current: WorkflowState) => {
    pastRef.current = [...pastRef.current.slice(-(HISTORY_LIMIT - 1)), snapOf(current)]
    futureRef.current = []
    bumpHistory()
  }, [])

  const withHistory = useCallback(
    (recipe: (current: WorkflowState) => WorkflowState) => {
      setState((current) => {
        const next = recipe(current)
        if (next === current) return current
        pushHistory(current)
        return { ...next, validationIssues: [] }
      })
    },
    [pushHistory]
  )

  const canUndo = pastRef.current.length > 0
  const canRedo = futureRef.current.length > 0
  // historyTick forces re-render of canUndo/canRedo consumers
  void historyTick

  const undo = useCallback(() => {
    setState((current) => {
      const prev = pastRef.current.pop()
      if (!prev) return current
      futureRef.current.push(snapOf(current))
      bumpHistory()
      return {
        ...current,
        steps: prev.steps,
        selectedId: prev.selectedId,
        selectedIds: prev.selectedIds,
        dirty: true,
      }
    })
  }, [])

  const redo = useCallback(() => {
    setState((current) => {
      const next = futureRef.current.pop()
      if (!next) return current
      pastRef.current.push(snapOf(current))
      bumpHistory()
      return {
        ...current,
        steps: next.steps,
        selectedId: next.selectedId,
        selectedIds: next.selectedIds,
        dirty: true,
      }
    })
  }, [])

  const patch = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value, dirty: value.dirty !== false }))
  }, [])

  const patchMeta = useCallback((value: Partial<WorkflowState>) => {
    setState((current) => ({ ...current, ...value }))
  }, [])

  const select = useCallback((id: string | null, multi = false) => {
    setState((current) => {
      if (!id) {
        return { ...current, selectedId: null, selectedIds: [] }
      }
      if (multi) {
        const exists = current.selectedIds.includes(id)
        const selectedIds = exists
          ? current.selectedIds.filter((item) => item !== id)
          : [...current.selectedIds, id]
        return {
          ...current,
          selectedId: selectedIds[selectedIds.length - 1] ?? null,
          selectedIds,
        }
      }
      return { ...current, selectedId: id, selectedIds: [id] }
    })
  }, [])

  const selectMany = useCallback((ids: string[]) => {
    setState((current) => ({
      ...current,
      selectedId: ids[ids.length - 1] ?? null,
      selectedIds: ids,
    }))
  }, [])

  const add = (type: WorkflowNodeType = 'step') => {
    const node = createNode(type)
    withHistory((current) => ({
      ...current,
      steps: [...current.steps, node],
      selectedId: node.id,
      selectedIds: [node.id],
      dirty: true,
    }))
  }

  const addAt = (
    type: WorkflowNodeType,
    position: { x: number; y: number },
    target?: ReparentTarget | null
  ) => {
    const node = createNode(type)
    node.position = { x: position.x, y: position.y }
    withHistory((current) => {
      const steps = target
        ? insertChild(current.steps, target, node)
        : [...current.steps, node]
      return {
        ...current,
        steps,
        selectedId: node.id,
        selectedIds: [node.id],
        dirty: true,
      }
    })
  }

  const addChild = (
    parentId: string,
    branch: 'steps' | 'thenSteps' | 'elseSteps' = 'steps',
    type: WorkflowNodeType = 'step'
  ) => {
    const child = createNode(type)
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: addChildToNode(current.steps, parentId, branch, child),
      selectedId: child.id,
      selectedIds: [child.id],
    }))
  }

  const addToSlot = (parentId: string, slotKey: string, type: WorkflowNodeType = 'step') => {
    withHistory((current) => {
      const parent = findNode(current.steps, parentId)
      if (!parent) return current
      const target = parseEmptySlot(parent, slotKey)
      if (!target) return current
      const child = createNode(type)
      const parentPos = parent.position
      if (parentPos) {
        child.position = { x: parentPos.x + 220, y: parentPos.y + 40 }
      }
      return {
        ...current,
        dirty: true,
        steps: insertChild(current.steps, target, child),
        selectedId: child.id,
        selectedIds: [child.id],
      }
    })
  }

  // Inspector field edits: push one undo snapshot per burst (typing does not spam history).
  const inspectorHistoryNodeRef = useRef<string | null>(null)
  const inspectorHistoryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const update = (node: WorkflowNode) => {
    setState((current) => {
      if (inspectorHistoryNodeRef.current !== node.id) {
        pushHistory(current)
        inspectorHistoryNodeRef.current = node.id
      }
      if (inspectorHistoryTimerRef.current) clearTimeout(inspectorHistoryTimerRef.current)
      inspectorHistoryTimerRef.current = setTimeout(() => {
        inspectorHistoryNodeRef.current = null
        inspectorHistoryTimerRef.current = null
      }, 600)
      let nextNode = node
      // Agno Parallel cannot pause for step HITL — strip flags if nested under Parallel.
      if (
        nextNode.type === 'step' &&
        isInsideParallel(current.steps, nextNode.id) &&
        (nextNode.requiresConfirmation || nextNode.requiresUserInput || nextNode.requiresOutputReview)
      ) {
        nextNode = {
          ...nextNode,
          requiresConfirmation: false,
          requiresUserInput: false,
          requiresOutputReview: false,
          confirmationMessage: undefined,
          userInputMessage: undefined,
          outputReviewMessage: undefined,
        }
      }
      return {
        ...current,
        dirty: true,
        validationIssues: [],
        steps: updateNodeInTree(current.steps, nextNode.id, () => nextNode),
      }
    })
  }


  /** Apply a patch to every selected Agent step (multi-select bulk edit).
   * Returns how many Parallel-nested steps skipped enabling HITL.
   */
  const updateSelectedSteps = (
    patch: Partial<Pick<WorkflowNode, 'targetId' | 'skills' | 'requiresConfirmation' | 'requiresUserInput' | 'requiresOutputReview' | 'instructions'>>,
  ): number => {
    // Precompute against current snapshot so toast count is Strict Mode-safe.
    const ids = (
      state.selectedIds.length
        ? state.selectedIds
        : state.selectedId
          ? [state.selectedId]
          : []
    )
    if (!ids.length) return 0
    const hitlPatch =
      patch.requiresConfirmation === true ||
      patch.requiresUserInput === true ||
      patch.requiresOutputReview === true
    let skippedHitl = 0
    if (hitlPatch) {
      for (const id of ids) {
        const node = findNode(state.steps, id)
        if (node?.type === 'step' && isInsideParallel(state.steps, id)) {
          skippedHitl += 1
        }
      }
    }

    // Burst undo for typing (instructions); discrete Select/Checkbox still one snapshot per burst.
    setState((current) => {
      const liveIds = new Set(
        current.selectedIds.length
          ? current.selectedIds
          : current.selectedId
            ? [current.selectedId]
            : [],
      )
      if (!liveIds.size) return current
      if (inspectorHistoryNodeRef.current !== 'multi-select') {
        pushHistory(current)
        inspectorHistoryNodeRef.current = 'multi-select'
      }
      if (inspectorHistoryTimerRef.current) clearTimeout(inspectorHistoryTimerRef.current)
      inspectorHistoryTimerRef.current = setTimeout(() => {
        inspectorHistoryNodeRef.current = null
        inspectorHistoryTimerRef.current = null
      }, 600)
      let steps = current.steps
      const enablingHitl =
        patch.requiresConfirmation === true ||
        patch.requiresUserInput === true ||
        patch.requiresOutputReview === true
      for (const id of liveIds) {
        const node = findNode(steps, id)
        if (!node || node.type !== 'step') continue
        if (enablingHitl && isInsideParallel(steps, id)) {
          // Skip enabling HITL under Parallel; allow clearing flags.
          const cleared = { ...patch }
          if (patch.requiresConfirmation === true) cleared.requiresConfirmation = false
          if (patch.requiresUserInput === true) cleared.requiresUserInput = false
          if (patch.requiresOutputReview === true) cleared.requiresOutputReview = false
          steps = updateNodeInTree(steps, id, (item) => ({ ...item, ...cleared }))
          continue
        }
        steps = updateNodeInTree(steps, id, (item) => ({ ...item, ...patch }))
      }
      return {
        ...current,
        dirty: true,
        validationIssues: [],
        steps,
      }
    })
    return skippedHitl
  }

  const remove = (id: string) =>
    withHistory((current) => {
      const selectedIds = current.selectedIds.filter((item) => item !== id)
      return {
        ...current,
        dirty: true,
        steps: removeNodeInTree(current.steps, id),
        selectedId: current.selectedId === id ? selectedIds[0] ?? null : current.selectedId,
        selectedIds,
      }
    })

  const removeSelected = () => {
    withHistory((current) => {
      const ids = current.selectedIds.length
        ? current.selectedIds
        : current.selectedId
          ? [current.selectedId]
          : []
      if (!ids.length) return current
      return {
        ...current,
        dirty: true,
        steps: removeNodesInTree(current.steps, ids),
        selectedId: null,
        selectedIds: [],
      }
    })
  }

  const move = (id: string, direction: -1 | 1) =>
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: moveStep(current.steps, id, direction),
    }))

  const applyPositions = (positions: Record<string, { x: number; y: number }>) => {
    withHistory((current) => {
      let steps = current.steps
      for (const [id, position] of Object.entries(positions)) {
        steps = updateNodeInTree(steps, id, (node) => ({ ...node, position }))
      }
      return { ...current, steps, dirty: true }
    })
  }

  const reparent = (nodeId: string, target: ReparentTarget): ReparentBlockedReason | null => {
    // Precompute against current state so Strict Mode double-invoke cannot clear the reason.
    const preview = reparentNode(state.steps, nodeId, target)
    if (preview.blocked) return preview.blocked
    if (preview.steps === state.steps) return null
    withHistory((current) => {
      const outcome =
        current.steps === state.steps
          ? preview
          : reparentNode(current.steps, nodeId, target)
      if (outcome.blocked || outcome.steps === current.steps) return current
      return {
        ...current,
        steps: outcome.steps,
        dirty: true,
        selectedId: nodeId,
        selectedIds: [nodeId],
      }
    })
    return null
  }

  const connectSequence = (sourceId: string, targetId: string) => {
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: moveNodeAfter(current.steps, targetId, sourceId),
    }))
  }

  /** Wire target under source's branch handle (condition/router/parallel). */
  const connectBranch = (
    sourceId: string,
    targetId: string,
    sourceHandle?: string | null,
  ): ReparentBlockedReason | null => {
    const source = findNode(state.steps, sourceId)
    if (!source) return null
    const target = reparentTargetFromHandle(source, sourceHandle)
    if (!target) return null
    const preview = reparentNode(state.steps, targetId, target)
    if (preview.blocked) return preview.blocked
    if (preview.steps === state.steps) return null
    withHistory((current) => {
      const liveSource = findNode(current.steps, sourceId)
      if (!liveSource) return current
      const liveTarget = reparentTargetFromHandle(liveSource, sourceHandle)
      if (!liveTarget) return current
      const outcome =
        current.steps === state.steps
          ? preview
          : reparentNode(current.steps, targetId, liveTarget)
      if (outcome.blocked || outcome.steps === current.steps) return current
      return {
        ...current,
        dirty: true,
        steps: outcome.steps,
        selectedId: targetId,
        selectedIds: [targetId],
      }
    })
    return null
  }

  const organizeLayout = () => {
    withHistory((current) => ({
      ...current,
      dirty: true,
      steps: applyAutoLayout(current.steps),
    }))
  }

  const copySelected = (): boolean => {
    const ids = state.selectedIds.length
      ? state.selectedIds
      : state.selectedId
        ? [state.selectedId]
        : []
    const nodes = ids
      .map((id) => findNode(state.steps, id))
      .filter((node): node is WorkflowNode => Boolean(node))
    // Prefer top-most selection only (skip nodes nested under another selected node).
    const tops = nodes.filter(
      (node) => !nodes.some((other) => other.id !== node.id && Boolean(findNode([other], node.id)))
    )
    const payload = (tops.length ? tops : nodes).map(cloneNodeDeep)
    clipboardRef.current = payload
    return payload.length > 0
  }

  const pasteClipboard = (): {
    divertedHitlCount: number
    multiSelectRootPaste: boolean
    pasted: boolean
  } => {
    const items = clipboardRef.current
    if (!items.length) {
      return { divertedHitlCount: 0, multiSelectRootPaste: false, pasted: false }
    }

    const soleId =
      state.selectedIds.length === 1
        ? state.selectedIds[0]
        : state.selectedId && state.selectedIds.length <= 1
          ? state.selectedId
          : null
    const host = soleId ? findNode(state.steps, soleId) : null
    let anchor: { x: number; y: number } | null = null
    if (host?.position) {
      anchor = { x: host.position.x + 220, y: host.position.y + 40 }
    } else if (host) {
      const parentLoc = locateNode(state.steps, host.id)
      if (parentLoc && parentLoc.kind !== 'root') {
        const parent = findNode(state.steps, parentLoc.parentId)
        if (parent?.position) {
          anchor = { x: parent.position.x + 220, y: parent.position.y + 40 }
        }
      }
    }

    const clones = items.map((node, index) => {
      const clone = cloneNodeDeep(node)
      if (anchor) {
        clone.position = { x: anchor.x, y: anchor.y + index * 100 }
      } else {
        const pos = clone.position
        clone.position = pos
          ? { x: pos.x + 40, y: pos.y + 40 }
          : { x: 80 + index * 40, y: 80 + index * 40 }
      }
      return clone
    })
    // refresh clipboard offsets for repeated paste
    clipboardRef.current = clones.map(cloneNodeDeep)
    const ids = clones.map((c) => c.id)
    const pasted = pasteNodesIntoSelection(
      state.steps,
      clones,
      state.selectedIds,
      state.selectedId,
    )

    withHistory((current) => {
      // If state raced, re-paste against latest tree with same clones/selection intent.
      if (
        current.steps !== state.steps ||
        current.selectedId !== state.selectedId ||
        current.selectedIds.join() !== state.selectedIds.join()
      ) {
        const again = pasteNodesIntoSelection(
          current.steps,
          clones.map(cloneNodeDeep),
          current.selectedIds,
          current.selectedId,
        )
        return {
          ...current,
          dirty: true,
          steps: again.steps,
          selectedId: ids[ids.length - 1] ?? null,
          selectedIds: ids,
          focusEpoch: current.focusEpoch + 1,
        }
      }
      return {
        ...current,
        dirty: true,
        steps: pasted.steps,
        selectedId: ids[ids.length - 1] ?? null,
        selectedIds: ids,
        focusEpoch: current.focusEpoch + 1,
      }
    })
    return {
      divertedHitlCount: pasted.divertedHitlCount,
      multiSelectRootPaste: pasted.multiSelectRootPaste,
      pasted: true,
    }
  }

  const duplicateSelected = (): {
    divertedHitlCount: number
    multiSelectRootPaste: boolean
    pasted: boolean
  } => {
    // snapshot selection into clipboard then paste with offset
    const ids = state.selectedIds.length
      ? state.selectedIds
      : state.selectedId
        ? [state.selectedId]
        : []
    const nodes = ids
      .map((id) => findNode(state.steps, id))
      .filter((node): node is WorkflowNode => Boolean(node))
    const tops = nodes.filter(
      (node) => !nodes.some((other) => other.id !== node.id && Boolean(findNode([other], node.id)))
    )
    clipboardRef.current = (tops.length ? tops : nodes).map(cloneNodeDeep)
    return pasteClipboard()
  }

  const patchTriggers = (triggers: WorkflowTriggers) => {
    setState((current) => {
      const enablingWebhook =
        triggers.webhook.enabled && !current.triggers.webhook.enabled
      const enablingCron = triggers.cron.enabled && !current.triggers.cron.enabled
      if (enablingWebhook || enablingCron) {
        const block = triggerEnableBlocked(current)
        if (block === 'unpublished') {
          return {
            ...current,
            error: t('errorTriggerNeedsPublish'),
          }
        }
        if (block === 'dirty') {
          return {
            ...current,
            error: t('errorTriggerNeedsSavePublish'),
          }
        }
      }
      return { ...current, triggers, dirty: true, error: null }
    })
  }

  const applyRecord = useCallback((record: NonNullable<ReturnType<typeof fromRecord>>) => {
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    setState((current) => ({
      ...current,
      ...record,
      selectedIds: record.selectedId ? [record.selectedId] : [],
      input: current.input,
      sessionId: crypto.randomUUID(),
      runLog: [],
      error: null,
      validationIssues: [],
      dirty: false,
      loading: false,
      focusEpoch: current.focusEpoch + 1,
    }))
  }, [])

  const load = useCallback(
    (id: string) => {
      const cached = workflowRecords.find((item) => item.id === id)
      if (cached) {
        applyRecord(fromRecord(cached))
        return
      }
      setState((current) => ({ ...current, loading: true, error: null }))
      void getWorkflow(id)
        .then((record) => {
          applyRecord(fromRecord(record))
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : t('errorLoadFailed')
          setState((current) => ({ ...current, loading: false, error: message }))
        })
        .finally(() => {
          setState((current) => ({ ...current, loading: false }))
        })
    },
    [applyRecord, workflowRecords],
  )

  const applyTemplate = (templateId: string) => {
    const template = (templatesQuery.data ?? []).find((item) => item.id === templateId)
    if (!template) return
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    const loaded = fromDefinition(template.definition, {
      name: template.definition.name || template.name,
      description: template.definition.description || template.description,
    })
    if (loaded.steps?.length) {
      loaded.steps = applyAutoLayout(loaded.steps)
    }
    setState((current) => ({
      ...current,
      ...loaded,
      version: 0,
      publishedVersion: null,
      publishedAt: null,
      hasPublished: false,
      nextCronAt: null,
      selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
      input: current.input,
      sessionId: crypto.randomUUID(),
      modelId: current.modelId,
      runLog: [],
      nodeRunStatus: {},
      runHistory: [],
      error: null,
      validationIssues: [],
      dirty: true,
      focusEpoch: current.focusEpoch + 1,
      lastRunId: null,
      lastSessionId: null,
      lastApprovalId: null,
    }))
  }

  /** Load IR-triage (or first) template into a fresh draft. */
  const startFromTemplate = (templateId = 'ir-triage') => {
    const list = templatesQuery.data ?? []
    const id = list.some((item) => item.id === templateId)
      ? templateId
      : list[0]?.id
    if (!id) return
    applyTemplate(id)
  }

  /** Apply template, save immediately, keep Publish path obvious (dirty=false, has id). */
  const applyTemplateAndSave = async (templateId: string) => {
    const template = (templatesQuery.data ?? []).find((item) => item.id === templateId)
    if (!template) return
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    const loaded = fromDefinition(template.definition, {
      name: template.definition.name || template.name,
      description: template.definition.description || template.description,
    })
    if (loaded.steps?.length) {
      loaded.steps = applyAutoLayout(loaded.steps)
    }
    const draftSteps = loaded.steps ?? []
    const draftName = loaded.name || template.name
    const draftDescription = loaded.description || template.description
    setState((current) => ({
      ...current,
      ...loaded,
      version: 0,
      publishedVersion: null,
      publishedAt: null,
      hasPublished: false,
      nextCronAt: null,
      selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
      input: current.input,
      sessionId: crypto.randomUUID(),
      modelId: current.modelId,
      runLog: [],
      nodeRunStatus: {},
      runHistory: [],
      error: null,
      validationIssues: [],
      dirty: true,
      saving: true,
      focusEpoch: current.focusEpoch + 1,
      lastRunId: null,
      lastSessionId: null,
      lastApprovalId: null,
    }))
    try {
      const definition = toDefinition({
        name: draftName,
        description: draftDescription,
        steps: draftSteps,
      })
      const body = {
        name: definition.name,
        description: definition.description,
        definition,
        triggers: defaultTriggers(),
      }
      const record = await createWorkflow(body)
      const saved = fromRecord(record)
      setState((current) => ({
        ...current,
        ...saved,
        selectedIds: saved.selectedId ? [saved.selectedId] : [],
        saving: false,
        dirty: false,
        error: null,
        focusEpoch: current.focusEpoch + 1,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
    } catch (error) {
      setState((current) => ({
        ...current,
        saving: false,
        error: error instanceof Error ? error.message : t('errorSaveFailed'),
      }))
    }
  }

  const reset = () => {
    abortRef.current?.abort()
    pastRef.current = []
    futureRef.current = []
    bumpHistory()
    setState(initialState())
  }

  const save = async (): Promise<boolean> => {
    const translate = (key: string, options?: Record<string, string | number>) => t(key, options)
    const issues = validateWorkflowDraft(state.steps, translate, state.workflowId)
    const nameIssue = validateWorkflowName(state.name, translate)
    if (nameIssue) issues.unshift(nameIssue)
    if (issues.length) {
      setState((current) => ({
        ...current,
        validationIssues: issues,
        validationEpoch: current.validationEpoch + 1,
        error: issues[0]?.message ?? t('validationFixBeforeSave'),
        selectedId: issues[0]?.nodeId ?? current.selectedId,
        selectedIds: issues[0]?.nodeId ? [issues[0].nodeId] : current.selectedIds,
      }))
      return false
    }
    setState((current) => ({ ...current, saving: true, error: null, validationIssues: [] }))
    try {
      const definition = toDefinition(state)
      const body = {
        name: definition.name,
        description: definition.description,
        definition,
        triggers: state.triggers,
      }
      const record = state.workflowId
        ? await updateWorkflow(state.workflowId, body)
        : await createWorkflow(body)
      const loaded = fromRecord(record)
      setState((current) => ({
        ...current,
        ...loaded,
        selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
        saving: false,
        dirty: false,
        error: null,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
      return true
    } catch (error) {
      setState((current) => ({
        ...current,
        saving: false,
        error: error instanceof Error ? error.message : t('errorSaveFailed'),
      }))
      return false
    }
  }

  const publish = async (): Promise<boolean> => {
    if (!state.workflowId) {
      setState((current) => ({ ...current, error: t('errorPublishNeedsSave') }))
      return false
    }
    if (state.dirty) {
      setState((current) => ({ ...current, error: t('errorPublishNeedsClean') }))
      return false
    }
    setState((current) => ({ ...current, saving: true, error: null }))
    try {
      const record = await publishWorkflow(state.workflowId)
      const loaded = fromRecord(record)
      setState((current) => ({
        ...current,
        ...loaded,
        selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
        saving: false,
        dirty: false,
        error: null,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
      return true
    } catch (error) {
      setState((current) => ({
        ...current,
        saving: false,
        error: error instanceof Error ? error.message : t('errorPublishFailed'),
      }))
      return false
    }
  }

  const restoreVersion = async (version: number) => {
    if (!state.workflowId) return
    try {
      const record = await restoreWorkflowVersion(state.workflowId, version)
      pastRef.current = []
      futureRef.current = []
      bumpHistory()
      const loaded = fromRecord(record)
      setState((current) => ({
        ...current,
        ...loaded,
        selectedIds: loaded.selectedId ? [loaded.selectedId] : [],
        dirty: false,
        error: null,
      }))
      await workflowsQuery.refetch()
      await versionsQuery.refetch()
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : t('errorRestoreFailed'),
      }))
    }
  }

  const removeSaved = async () => {
    if (!state.workflowId) return
    await deleteWorkflow(state.workflowId)
    reset()
    await workflowsQuery.refetch()
  }

  const run = async () => {
    if (!state.workflowId) {
      setState((current) => ({ ...current, error: t('errorRunNeedsSave') }))
      return
    }
    if (state.dirty) {
      setState((current) => ({ ...current, error: t('errorRunNeedsClean') }))
      return
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const sessionId = crypto.randomUUID()
    const runId = crypto.randomUUID()
    const historyId = crypto.randomUUID()
    setState((current) => ({
      ...current,
      running: true,
      error: null,
      runLog: [],
      nodeRunStatus: {},
      sessionId,
      lastSessionId: sessionId,
      lastRunId: runId,
      lastApprovalId: null,
      runHistory: [
        {
          id: historyId,
          runId,
          sessionId,
          status: 'running' as const,
          startedAt: Date.now(),
        } satisfies WorkflowRunHistoryItem,
        ...current.runHistory,
      ].slice(0, 20),
    }))
    try {
      await streamWorkflowRun(
        state.workflowId,
        {
          input: state.input,
          session_id: sessionId,
          model_id: state.modelId,
          run_id: runId,
        },
        (item) => {
          setState((current) => {
            const runLog = appendRunLog(current.runLog, item, 200)
            const nodeRunStatus = applyNodeRunStatusEvent(
              current.steps,
              current.nodeRunStatus,
              item
            )
            const histStatus = historyStatusFromEvent(item.type)
            let runHistory = current.runHistory
            if (histStatus || item.runId || item.approvalId) {
              runHistory = current.runHistory.map((entry) => {
                if (entry.id !== historyId) return entry
                return {
                  ...entry,
                  runId: item.runId || entry.runId,
                  sessionId: item.sessionId || entry.sessionId,
                  status: histStatus ?? entry.status,
                  finishedAt:
                    histStatus && histStatus !== 'running'
                      ? Date.now()
                      : entry.finishedAt,
                  approvalId: item.approvalId ?? entry.approvalId,
                  summary: historySummaryFromEvent(item) || entry.summary,
                }
              })
            }
            return {
              ...current,
              runLog,
              nodeRunStatus,
              runHistory,
              lastRunId: item.runId || current.lastRunId,
              lastSessionId: item.sessionId || current.lastSessionId,
              lastApprovalId: item.approvalId ?? current.lastApprovalId,
              // stream ends on pause; treat as not actively streaming
              running:
                item.type === 'workflow.paused' ||
                item.type === 'workflow.completed' ||
                item.type === 'workflow.failed' ||
                item.type === 'workflow.cancelled'
                  ? false
                  : current.running,
            }
          })
        },
        controller.signal
      )
      setState((current) => ({ ...current, running: false }))
    } catch (error) {
      if (controller.signal.aborted) {
        setState((current) => ({ ...current, running: false }))
        return
      }
      setState((current) => ({
        ...current,
        running: false,
        error: error instanceof Error ? error.message : t('errorRunFailed'),
      }))
    }
  }

  const stop = () => {
    const runId = state.lastRunId
    // Always stop the client SSE first so the UI unblocks immediately.
    abortRef.current?.abort()
    setState((current) => {
      const cancelItem: WorkflowRunLogItem = {
        id: crypto.randomUUID(),
        type: 'workflow.cancelled',
        message: t('runStoppedByUser'),
        runId: runId || current.lastRunId,
        sessionId: current.lastSessionId,
        at: Date.now(),
      }
      // Avoid duplicate cancelled rows if stop is double-clicked.
      const alreadyCancelled =
        current.runLog.length > 0 &&
        current.runLog[current.runLog.length - 1]?.type === 'workflow.cancelled'
      const runLog = alreadyCancelled
        ? current.runLog
        : appendRunLog(current.runLog, cancelItem, 200)
      return {
        ...current,
        running: false,
        // Local stop succeeded; clear prior banners until server cancel reports failure.
        error: null,
        runLog,
        nodeRunStatus: applyNodeRunStatusEvent(
          current.steps,
          current.nodeRunStatus,
          cancelItem,
        ),
        runHistory: current.runHistory.map((entry, index) =>
          index === 0 && entry.status === 'running'
            ? {
                ...entry,
                status: 'cancelled' as const,
                finishedAt: Date.now(),
                summary: t('runStoppedByUser'),
              }
            : entry
        ),
      }
    })
    if (!runId) return
    void cancelWorkflowRun(runId).catch((error: unknown) => {
      // 404 = run already finished or never registered (race with terminal event).
      if (error instanceof ApiError && error.status === 404) return
      const detail = error instanceof Error ? error.message : String(error)
      console.warn(`[workflow] server cancel failed for run ${runId}: ${detail}`)
      // Local stop already applied; surface server cancel failure as dismissible banner.
      setState((current) => ({
        ...current,
        error: t('cancelServerFailed'),
      }))
    })
  }

  const selected = useMemo(
    () => (state.selectedId ? findNode(state.steps, state.selectedId) : null),
    [state.selectedId, state.steps]
  )

  return {
    state,
    selected,
    canUndo,
    canRedo,
    workflowsQuery,
    workflowRecords,
    workflowListMeta,
    librarySearch,
    setLibrarySearch,
    executorsQuery,
    modelsQuery,
    versionsQuery,
    templatesQuery,
    patch,
    patchMeta,
    patchTriggers,
    select,
    selectMany,
    add,
    addAt,
    addChild,
    addToSlot,
    update,
    updateSelectedSteps,
    remove,
    removeSelected,
    move,
    applyPositions,
    reparent,
    connectSequence,
    connectBranch,
    organizeLayout,
    copySelected,
    pasteClipboard,
    duplicateSelected,
    undo,
    redo,
    load,
    applyTemplate,
    applyTemplateAndSave,
    startFromTemplate,
    reset,
    save,
    publish,
    restoreVersion,
    removeSaved,
    run,
    stop,
  }
}
