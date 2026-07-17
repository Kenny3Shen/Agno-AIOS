/**
 * Workflow Studio page shell (draw.io-style three-pane layout).
 *
 * Layout:
 * - Left: shapes palette + templates + library
 * - Center: React Flow canvas
 * - Right: inspector + run log
 *
 * Orchestration state lives in `useWorkflow`. This file wires UI chrome only
 * (toolbar groups, panels, inspector forms). Keep save/run/publish handlers
 * delegated to the hook so behavior stays centralized.
 */
import {
  Alert,
  App,
  Button,
  Checkbox,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  ApiOutlined,
  BranchesOutlined,
  ClusterOutlined,
  CloseOutlined,
  DeleteOutlined,
  DeploymentUnitOutlined,
  NodeIndexOutlined,
  PlayCircleOutlined,
  PartitionOutlined,
  RetweetOutlined,
  SaveOutlined,
  StopOutlined,
  PlusOutlined,
  UndoOutlined,
  RedoOutlined,
  ApartmentOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  ReloadOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { Markdown } from '@/shared/ui/Markdown'
import { useQuery } from '@tanstack/react-query'
import { useBlocker, useRouter } from '@tanstack/react-router'
import { useWorkflow } from './useWorkflow'
import { runEventLabelKey } from './runStatus'
import { WorkflowCanvas, paletteDragStart } from './WorkflowCanvas'
import type { WorkflowNodeType } from './types'
import {
  buildWorkflowCode,
  fieldForValidationIssue,
  rotateWebhookSecret,
  triggerEnableBlocked,
  workflowWebhookCurl,
  workflowWebhookUrl,
  findNode,
  isInsideParallel,
  summarizeSelectedAgentSteps,
} from './utils'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import { listWorkflowTriggerHistory } from './api'
import { listSkills } from '@/features/skills/api'
import { CelExpressionField } from './CelExpressionField'
import { currentUserQuery } from '@/features/auth'
import { hasScope } from '@/shared/auth/permissions'
import { useFormatDate } from '@/shared/lib/format'
import { isOverlayEscapeTarget } from '@/shared/lib/keyboard'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

const PALETTE: Array<{
  type: WorkflowNodeType
  icon: ReactNode
  color: string
}> = [
  { type: 'step', icon: <ApiOutlined />, color: '#1677ff' },
  { type: 'parallel', icon: <PartitionOutlined />, color: '#722ed1' },
  { type: 'condition', icon: <BranchesOutlined />, color: '#d48806' },
  { type: 'loop', icon: <RetweetOutlined />, color: '#08979c' },
  { type: 'router', icon: <ClusterOutlined />, color: '#c41d7f' },
  { type: 'workflow_ref', icon: <DeploymentUnitOutlined />, color: '#389e0d' },
]

const studioPopupContainer = (node: HTMLElement) =>
  (node.closest('.workflow-studio') as HTMLElement | null) ?? document.body

export function WorkflowPage() {
  const { t } = useTranslation('workflow')
  const { modal, message } = App.useApp()
  const formatDate = useFormatDate()
  const routerNav = useRouter()
  const workflow = useWorkflow()
  const copyWithGuard = () => {
    if (!workflow.copySelected()) {
      message.info(t('copyEmptySelection'))
    }
  }

  /**
   * Prompt before wiping Studio state (load / reset / template / restore).
   * Running runs are stopped first; dirty drafts need discard confirmation.
   */
  const confirmLeaveStudio = (action: () => void) => {
    const proceed = () => {
      if (!workflow.state.dirty) {
        action()
        return
      }
      modal.confirm({
        title: t('discardDirtyTitle'),
        content: t('discardDirtyContent'),
        okText: t('discardDirtyConfirm'),
        cancelText: t('common:cancel'),
        okButtonProps: { danger: true },
        onOk: () => {
          action()
        },
      })
    }
    if (workflow.state.running) {
      modal.confirm({
        title: t('stopRunBeforeLeaveTitle'),
        content: t('stopRunBeforeLeaveContent'),
        okText: t('stopRunAndContinue'),
        cancelText: t('common:cancel'),
        okButtonProps: { danger: true },
        onOk: () => {
          workflow.stop()
          // Let the stop dialog close before any dirty-discard dialog.
          window.setTimeout(() => proceed(), 0)
        },
      })
      return
    }
    proceed()
  }
  const pasteWithHitlGuard = () => {
    const result = workflow.pasteClipboard()
    if (!result.pasted) {
      message.info(t('pasteEmptyClipboard'))
      return
    }
    if (result.divertedHitlCount > 0) {
      message.warning(t('pasteHitlDiverted', { count: result.divertedHitlCount }))
    } else if (result.multiSelectRootPaste) {
      message.info(t('pasteMultiSelectRoot'))
    }
  }
  const duplicateWithHitlGuard = () => {
    const result = workflow.duplicateSelected()
    if (!result.pasted) {
      message.info(t('pasteEmptyClipboard'))
      return
    }
    if (result.divertedHitlCount > 0) {
      message.warning(t('pasteHitlDiverted', { count: result.divertedHitlCount }))
    } else if (result.multiSelectRootPaste) {
      message.info(t('pasteMultiSelectRoot'))
    }
  }
  const warnReparentBlocked = (blocked: string | null | undefined) => {
    if (blocked === 'hitl_in_parallel') {
      message.warning(t('reparentHitlBlocked'))
    } else if (blocked === 'cycle') {
      message.warning(t('reparentCycleBlocked'))
    } else if (blocked === 'invalid') {
      message.warning(t('reparentInvalidBlocked'))
    }
  }
  const reparentWithHitlGuard = (
    nodeId: string,
    target: Parameters<typeof workflow.reparent>[1],
  ) => {
    warnReparentBlocked(workflow.reparent(nodeId, target))
  }
  const connectBranchWithHitlGuard = (
    sourceId: string,
    targetId: string,
    sourceHandle?: string | null,
  ) => {
    warnReparentBlocked(workflow.connectBranch(sourceId, targetId, sourceHandle))
  }
  const bulkHitlWithGuard = (
    patch: Parameters<typeof workflow.updateSelectedSteps>[0],
  ) => {
    const skipped = workflow.updateSelectedSteps(patch)
    if (skipped > 0) {
      message.warning(t('multiSelectHitlSkipped', { count: skipped }))
    }
  }

  // Esc stops an in-flight Studio run (page-level; canvas also handles when focused).
  const stopRef = useRef(workflow.stop)
  stopRef.current = workflow.stop
  useEffect(() => {
    if (!workflow.state.running) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (isOverlayEscapeTarget(event.target)) return
      event.preventDefault()
      stopRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [workflow.state.running])

  // SPA nav + tab close with active run or unsaved draft.
  const stopForLeaveRef = useRef(workflow.stop)
  stopForLeaveRef.current = workflow.stop
  const leaveGuardRef = useRef({ running: false, dirty: false })
  leaveGuardRef.current = {
    running: workflow.state.running,
    dirty: workflow.state.dirty,
  }
  const leaveGuardActive = workflow.state.running || workflow.state.dirty
  useBlocker({
    disabled: !leaveGuardActive,
    enableBeforeUnload: leaveGuardActive,
    shouldBlockFn: async () => {
      const { running, dirty } = leaveGuardRef.current
      if (!running && !dirty) return false
      const leave = await new Promise<boolean>((resolve) => {
        modal.confirm({
          title: running ? t('leaveWhileRunningTitle') : t('leaveWhileDirtyTitle'),
          content: running ? t('leaveWhileRunningContent') : t('leaveWhileDirtyContent'),
          okText: running ? t('stopAndLeave') : t('discardAndLeave'),
          cancelText: t('common:cancel'),
          okButtonProps: { danger: true },
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
      if (!leave) return true
      if (running) stopForLeaveRef.current()
      return false
    },
  })

  const runLogListRef = useRef<HTMLDivElement>(null)
  const inspectorPanelRef = useRef<HTMLElement | null>(null)
  const focusFieldRef = useRef<string | null>(null)
  const [runPanelKeys, setRunPanelKeys] = useState<string[]>(['run'])
  const currentUser = useQuery(currentUserQuery())
  const canRun =
    hasScope(currentUser.data, 'workflows:run') ||
    hasScope(currentUser.data, 'workflows:write')
  const canWrite = hasScope(currentUser.data, 'workflows:write')

  // Soft banners (e.g. server cancel failed, validation) auto-dismiss; keep hard
  // run failure visible via run-status Alert while a failed duty banner is shown.
  useEffect(() => {
    if (!workflow.state.error) return
    if (workflow.state.running || workflow.state.saving) return
    const timer = window.setTimeout(() => {
      workflow.patchMeta({ error: null })
    }, 8_000)
    return () => window.clearTimeout(timer)
  }, [workflow.state.error, workflow.state.running, workflow.state.saving, workflow.patchMeta])

  // Ctrl/⌘S save from canvas or inspector (not when a modal owns keyboard).

  const saveRef = useRef(workflow.save)
  saveRef.current = workflow.save
  const canWriteSaveRef = useRef(canWrite)
  canWriteSaveRef.current = canWrite
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 's') return
      if (event.defaultPrevented) return
      if (isOverlayEscapeTarget(event.target)) return
      if (!canWriteSaveRef.current) return
      if (workflow.state.saving || workflow.state.loading) return
      event.preventDefault()
      void saveRef.current().then((ok) => {
        if (ok) message.success(t('saveSuccess'))
      })
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [workflow.state.saving, workflow.state.loading])


  const publishStatusLabel = (() => {
    const { publishedVersion, publishedAt, hasPublished, dirty } = workflow.state
    if (!hasPublished) {
      return t('statusUnpublished')
    }
    const time =
      publishedAt != null && publishedAt > 0 ? formatDate(publishedAt) : ''
    const base =
      publishedVersion != null
        ? t('statusPublished', { version: publishedVersion, time })
        : t('statusPublishedUnknown')
    return dirty ? `${base} · ${t('statusDirtyDraft')}` : base
  })()

  const draftStatusLabel =
    workflow.state.workflowId != null && workflow.state.version > 0
      ? t('statusDraft', { version: workflow.state.version })
      : t('statusDraftNew')

  const latestRun = workflow.state.runHistory[0] ?? null
  const runDutyStatus = workflow.state.running
    ? 'running'
    : latestRun?.status ?? (workflow.state.error ? 'failed' : null)
  const openLatestTrace = () => {
    const sessionId = workflow.state.lastSessionId ?? latestRun?.sessionId
    const runId = workflow.state.lastRunId ?? latestRun?.runId ?? undefined
    if (!sessionId && !runId) return
    void routerNav.navigate({
      to: '/trace',
      search: {
        session_id: sessionId ?? undefined,
        run_id: runId || undefined,
        selected_session: sessionId ?? undefined,
        trace: runId || undefined,
      },
    })
  }
  const openLatestApproval = () => {
    const approvalId = workflow.state.lastApprovalId ?? latestRun?.approvalId
    if (!approvalId) return
    window.location.hash = `#/approvals?approval_id=${encodeURIComponent(approvalId)}`
  }
  const expandRunLog = () => {
    setRunPanelKeys((keys) => (keys.includes('run') ? keys : [...keys, 'run']))
    // Scroll run log into view if present
    window.requestAnimationFrame(() => {
      runLogListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  const requestEnableTrigger = (
    kind: 'webhook' | 'cron',
    enabled: boolean
  ) => {
    if (!enabled) {
      if (kind === 'webhook') {
        workflow.patchTriggers({
          ...workflow.state.triggers,
          webhook: { ...workflow.state.triggers.webhook, enabled: false },
        })
      } else {
        workflow.patchTriggers({
          ...workflow.state.triggers,
          cron: { ...workflow.state.triggers.cron, enabled: false },
        })
      }
      return
    }
    const block = triggerEnableBlocked(workflow.state)
    if (block === 'unpublished') {
      modal.warning({
        title: t('triggerNeedsPublishTitle'),
        content: t('triggerNeedsPublishBody'),
        okText: t('publish'),
        onOk: () => {
          if (workflow.state.workflowId && !workflow.state.dirty) {
            void workflow.publish().then((ok) => {
              if (ok) message.success(t('publishSuccess'))
            })
          } else if (canWrite) {
            void workflow.save().then((ok) => {
              if (ok) message.success(t('saveSuccess'))
            })
          }
        },
      })
      return
    }
    if (block === 'dirty') {
      modal.warning({
        title: t('triggerNeedsSavePublishTitle'),
        content: t('triggerNeedsSavePublishBody'),
        okText: t('save'),
        onOk: () => {
          if (canWrite) {
            void workflow.save().then((ok) => {
              if (ok) message.success(t('saveSuccess'))
            })
          }
        },
      })
      return
    }
    if (kind === 'webhook') {
      workflow.patchTriggers({
        ...workflow.state.triggers,
        webhook: { ...workflow.state.triggers.webhook, enabled: true },
      })
    } else {
      workflow.patchTriggers({
        ...workflow.state.triggers,
        cron: { ...workflow.state.triggers.cron, enabled: true },
      })
    }
  }

  const triggerHistoryQuery = useQuery({
    queryKey: ['workflows', 'trigger-history', workflow.state.workflowId],
    queryFn: () => listWorkflowTriggerHistory(workflow.state.workflowId!, { limit: 12 }),
    enabled: Boolean(workflow.state.workflowId),
    refetchInterval: 30_000,
  })
  const skillsQuery = useQuery({
    queryKey: ['skills', 'workflow-bind'],
    queryFn: listSkills,
    staleTime: 60_000,
  })
  const enabledSkillOptions = (skillsQuery.data ?? [])
    .filter((skill) => skill.enabled)
    .map((skill) => {
      const short = skill.name.replace(/-skill$/i, '')
      const label = skill.description
        ? `${skill.description} (${short})`
        : short
      return { value: skill.name, label }
    })
  const step = workflow.selected
  const stepInsideParallel = Boolean(
    step && isInsideParallel(workflow.state.steps, step.id),
  )
  const executors = workflow.executorsQuery.data ?? []
  const executorNames = useMemo(() => {
    const map = new Map<string, string>()
    for (const item of executors) {
      const ref = (item.ref || '').trim()
      if (!ref) continue
      const name = (item.name || '').trim()
      if (name) map.set(ref, name)
    }
    return map
  }, [executors])
  const models = workflow.modelsQuery.data?.models ?? []
  const saved = workflow.workflowRecords
  const workflowListMeta = workflow.workflowListMeta
  const versions = workflow.versionsQuery.data ?? []

  const currentWorkflowId = workflow.state.workflowId
  const loadWorkflow = workflow.load
  // Deep link: #/workflow?workflow_id=... (load fetches by id when not in first page)
  useEffect(() => {
    const raw = window.location.hash.split('?')[1] ?? ''
    const id = new URLSearchParams(raw).get('workflow_id')
    if (!id || currentWorkflowId === id) return
    loadWorkflow(id)
  }, [currentWorkflowId, loadWorkflow])

  // Pin to latest events (list is chronological; newest at bottom).
  useEffect(() => {
    if (!workflow.state.running && !workflow.state.runLog.length) return
    const node = runLogListRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [workflow.state.runLog, workflow.state.running])

  // When validation fails (or issue clicked), scroll inspector into view and focus the problem field.
  useEffect(() => {
    if (!workflow.state.validationEpoch) return
    const issues = workflow.state.validationIssues
    if (!issues.length) return
    const primary = issues[0]
    const field = focusFieldRef.current ?? fieldForValidationIssue(primary)
    focusFieldRef.current = null

    const panel = inspectorPanelRef.current
    panel?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })

    const nodeId = workflow.state.selectedId
    if (!nodeId) return
    const timer = window.setTimeout(() => {
      const root = inspectorPanelRef.current
      if (!root) return
      const target =
        root.querySelector<HTMLElement>(`[data-inspector-field="${field}"]`) ??
        root.querySelector<HTMLElement>('[data-inspector-field="name"]')
      if (!target) return
      target.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      const focusable =
        target.matches('input, textarea, button, [tabindex]')
          ? target
          : target.querySelector<HTMLElement>('input, textarea, button, .ant-select-selector')
      if (focusable && typeof focusable.focus === 'function') {
        try {
          focusable.focus({ preventScroll: true })
        } catch {
          focusable.focus()
        }
      }
    }, 80)
    return () => window.clearTimeout(timer)
  }, [workflow.state.validationEpoch, workflow.state.validationIssues, workflow.state.selectedId])

  const focusInspectorForNode = useCallback(
    (nodeId: string) => {
      focusFieldRef.current = 'name'
      workflow.select(nodeId)
      // Direct focus (validation effect only runs when issues exist).
      window.setTimeout(() => {
        const panel = inspectorPanelRef.current
        if (!panel) return
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        const field = focusFieldRef.current ?? 'name'
        focusFieldRef.current = null
        const target =
          panel.querySelector<HTMLElement>(`[data-inspector-field="${field}"]`) ??
          panel.querySelector<HTMLElement>('[data-inspector-field="name"]')
        if (!target) return
        target.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        const focusable = target.matches('input, textarea, button, [tabindex]')
          ? target
          : target.querySelector<HTMLElement>('input, textarea, button, .ant-select-selector')
        if (focusable && typeof focusable.focus === 'function') {
          try {
            focusable.focus({ preventScroll: true })
          } catch {
            focusable.focus()
          }
        }
      }, 80)
    },
    [workflow.select],
  )

  // Expand run log when a run starts so output is visible without manual open.
  useEffect(() => {
    if (workflow.state.running) {
      setRunPanelKeys((keys) => (keys.includes('run') ? keys : [...keys, 'run']))
    }
  }, [workflow.state.running])


  const paletteLabel = (type: WorkflowNodeType) => {
    const map: Record<WorkflowNodeType, string> = {
      step: t('addStep'),
      parallel: t('addParallel'),
      condition: t('addCondition'),
      loop: t('addLoop'),
      router: t('addRouter'),
      workflow_ref: t('addWorkflowRef'),
    }
    return map[type]
  }

  return (
    <main className="page workflow-studio">
      <header className="workflow-studio__toolbar">
        <div className="workflow-studio__brand">
          <NodeIndexOutlined />
          <Typography.Title level={5} className="workflow-studio__title">
            {t('title')}
          </Typography.Title>
        </div>
        <div className="workflow-studio__toolbar-main">
          <Input
            className="workflow-studio__name"
            data-inspector-field="workflowName"
            value={workflow.state.name}
            disabled={!canWrite || workflow.state.running}
            onChange={(e) => workflow.patch({ name: e.target.value })}
            placeholder={t('namePlaceholder')}
            variant="borderless"
            status={
              workflow.state.validationIssues.some((issue) => issue.code === 'empty_name')
                ? 'error'
                : undefined
            }
          />
          <Select
            getPopupContainer={studioPopupContainer}
            size="middle"
            style={{ minWidth: 180 }}
            placeholder={t('modelPlaceholder')}
            value={workflow.state.modelId ?? undefined}
            options={models
              .filter((model) => model.enabled)
              .map((model) => ({ value: model.id, label: model.name || model.model_id }))}
            onChange={(value) =>
              workflow.patchMeta({ modelId: value, dirty: workflow.state.dirty })
            }
          />
          <div className="workflow-studio__status" aria-label={t('statusAria')}>
            <Tag className="workflow-studio__status-tag">
              {draftStatusLabel}
              {workflow.state.dirty ? (
                <span className="workflow-studio__dirty-dot" title={t('statusDirty')}>
                  {' '}
                  *
                </span>
              ) : null}
            </Tag>
            <Tag
              color={workflow.state.hasPublished ? 'success' : 'default'}
              className="workflow-studio__status-tag"
            >
              {publishStatusLabel}
            </Tag>
          </div>
        </div>
        {/* Draw.io-style action strip: visual groups only; handlers unchanged. */}
        <div className="workflow-studio__actions workflow-studio__actions--drawio">
          <div
            className="workflow-studio__action-group"
            role="group"
            aria-label={t('toolbarGroupFile')}
          >
            <Button onClick={workflow.reset}>{t('new')}</Button>
          </div>
          <span className="workflow-studio__action-sep" aria-hidden />
          <div
            className="workflow-studio__action-group"
            role="group"
            aria-label={t('toolbarGroupEdit')}
          >
            <Tooltip title={t('undoHint')} getPopupContainer={studioPopupContainer}>
              <Button
                icon={<UndoOutlined />}
                disabled={!workflow.canUndo || workflow.state.running}
                onClick={workflow.undo}
              />
            </Tooltip>
            <Tooltip title={t('redoHint')} getPopupContainer={studioPopupContainer}>
              <Button
                icon={<RedoOutlined />}
                disabled={!workflow.canRedo || workflow.state.running}
                onClick={workflow.redo}
              />
            </Tooltip>
          </div>
          <span className="workflow-studio__action-sep" aria-hidden />
          <div
            className="workflow-studio__action-group"
            role="group"
            aria-label={t('toolbarGroupLayout')}
          >
            <Tooltip title={t('organizeHint')} getPopupContainer={studioPopupContainer}>
              <Button
                icon={<ApartmentOutlined />}
                disabled={workflow.state.running}
                onClick={workflow.organizeLayout}
                aria-label={t('organize')}
              />
            </Tooltip>
            <Tooltip
              title={t('keyboardHints')}
              classNames={{ root: 'workflow-studio__kbd-tooltip' }}
              styles={{
                container: {
                  maxWidth: 320,
                  whiteSpace: 'pre-line',
                  fontSize: 12,
                  lineHeight: 1.55,
                  textAlign: 'left',
                },
              }}
              getPopupContainer={studioPopupContainer}
            >
              <Button type="text" icon={<QuestionCircleOutlined />} aria-label={t('keyboardHintsTitle')} />
            </Tooltip>
          </div>
          <span className="workflow-studio__action-sep" aria-hidden />
          <div
            className="workflow-studio__action-group"
            role="group"
            aria-label={t('toolbarGroupDeploy')}
          >
            <Button
              icon={<SaveOutlined />}
              type="primary"
              loading={workflow.state.saving}
              disabled={!canWrite}
              onClick={() => {
                void workflow.save().then((ok) => {
                  if (ok) message.success(t('saveSuccess'))
                })
              }}
            >
              {t('save')}
              {workflow.state.dirty ? ' *' : ''}
            </Button>
            <Tooltip title={t('publishHint')} getPopupContainer={studioPopupContainer}>
              <Button
                icon={<CloudUploadOutlined />}
                type={
                  Boolean(workflow.state.workflowId) &&
                  !workflow.state.dirty &&
                  !workflow.state.hasPublished
                    ? 'primary'
                    : 'default'
                }
                loading={workflow.state.saving}
                disabled={!canWrite || !workflow.state.workflowId || workflow.state.dirty}
                onClick={() => {
                  void workflow.publish().then((ok) => {
                    if (ok) message.success(t('publishSuccess'))
                  })
                }}
              >
                {t('publish')}
              </Button>
            </Tooltip>
          </div>
          <span className="workflow-studio__action-sep" aria-hidden />
          <div
            className="workflow-studio__action-group"
            role="group"
            aria-label={t('toolbarGroupRun')}
          >
            <Tooltip
              title={
                !canRun
                  ? t('runScopeHint')
                  : !workflow.state.workflowId
                    ? t('errorRunNeedsSave')
                    : workflow.state.dirty
                      ? t('errorRunNeedsClean')
                      : undefined
              }
              getPopupContainer={studioPopupContainer}
            >
              <Button
                icon={<PlayCircleOutlined />}
                disabled={
                  workflow.state.running ||
                  !canRun ||
                  !workflow.state.workflowId ||
                  workflow.state.dirty
                }
                onClick={() => void workflow.run()}
              >
                {t('run')}
              </Button>
            </Tooltip>
            {workflow.state.running ? (
              <Tooltip title={t('stopRunHint')} getPopupContainer={studioPopupContainer}>
                <Button danger icon={<StopOutlined />} onClick={workflow.stop}>
                  {t('stop')}
                </Button>
              </Tooltip>
            ) : null}
          </div>
        </div>
      </header>
      {workflowListMeta &&
      !workflow.librarySearch.trim() &&
      workflowListMeta.total_count > saved.length &&
      !workflow.workflowsQuery.hasNextPage ? (
        <Alert
          type="info"
          showIcon
          className="workflow-studio__list-cap"
          title={t('listTruncated', {
            shown: saved.length,
            total: workflowListMeta.total_count,
          })}
        />
      ) : null}

      {workflow.state.loading ? (
        <Alert
          type="info"
          showIcon
          className="workflow-studio__banner"
          title={
            <Space size={8}>
              <Spin size="small" />
              <span>{t('loadingWorkflow')}</span>
            </Space>
          }
        />
      ) : null}

      {workflow.state.error ? (
        <Alert
          type="error"
          showIcon
          className="workflow-studio__banner"
          title={workflow.state.error}
          closable={{ onClose: () => workflow.patchMeta({ error: null }) }}
        />
      ) : null}

      {runDutyStatus && runDutyStatus !== 'completed' ? (
        <Alert
          type={
            runDutyStatus === 'failed'
              ? 'error'
              : runDutyStatus === 'paused'
                ? 'warning'
                : runDutyStatus === 'running'
                  ? 'info'
                  : 'warning'
          }
          showIcon
          className="workflow-studio__banner"
          title={
            runDutyStatus === 'running'
              ? workflow.state.dirty
                ? t('runBannerRunningDirty')
                : t('runBannerRunning')
              : runDutyStatus === 'paused'
                ? t('runBannerPaused')
                : runDutyStatus === 'failed'
                  ? t('runBannerFailed')
                  : t('runBannerCancelled')
          }
          description={
            <Space size={8} wrap>
              {(workflow.state.lastSessionId || latestRun?.sessionId || workflow.state.lastRunId || latestRun?.runId) ? (
                <Button type="link" size="small" style={{ paddingInline: 0 }} onClick={openLatestTrace}>
                  {t('openTrace')}
                </Button>
              ) : null}
              {(workflow.state.lastApprovalId || latestRun?.approvalId) &&
              (runDutyStatus === 'paused' || runDutyStatus === 'failed') ? (
                <Button type="link" size="small" style={{ paddingInline: 0 }} onClick={openLatestApproval}>
                  {t('openApproval')}
                </Button>
              ) : null}
              <Button type="link" size="small" style={{ paddingInline: 0 }} onClick={expandRunLog}>
                {t('openRunLog')}
              </Button>
            </Space>
          }
        />
      ) : null}

      <div className="workflow-studio__body">
        {/* Left rail: shapes palette + templates + library (draw.io "Shapes") */}
        <aside className="workflow-studio__left workflow-studio__shapes">
          <section className="workflow-studio__panel">
            <div className="workflow-studio__panel-title">{t('palette')}</div>
            <div className="workflow-palette">
              {PALETTE.map((item) => (
                <div
                  key={item.type}
                  className="workflow-palette__item"
                  draggable={!workflow.state.running && canWrite}
                  aria-disabled={workflow.state.running || !canWrite}
                  onDragStart={(event) => {
                    if (workflow.state.running || !canWrite) {
                      event.preventDefault()
                      return
                    }
                    paletteDragStart(event, item.type)
                  }}
                  onDoubleClick={() => {
                    if (workflow.state.running || !canWrite) return
                    workflow.add(item.type)
                  }}
                  style={{ borderColor: item.color }}
                  title={
                    workflow.state.running
                      ? t('errorEditWhileRunning')
                      : t('paletteDragHint')
                  }
                >
                  <span className="workflow-palette__icon" style={{ color: item.color }}>
                    {item.icon}
                  </span>
                  <span>{paletteLabel(item.type)}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="workflow-studio__panel">
            <div className="workflow-studio__panel-title">{t('templates')}</div>
            <div className="workflow-templates">
              {(workflow.templatesQuery.data ?? []).map((tpl) => (
                <div key={tpl.id} className="workflow-templates__item">
                  <button
                    type="button"
                    className="workflow-templates__load"
                    title={tpl.description || tpl.name}
                    disabled={!canWrite}
                    onClick={() => confirmLeaveStudio(() => workflow.applyTemplate(tpl.id))}
                  >
                    <strong>{tpl.name}</strong>
                  </button>
                  <Button
                    type="link"
                    size="small"
                    className="workflow-templates__save"
                    disabled={!canWrite || workflow.state.saving}
                    onClick={() => confirmLeaveStudio(() => void workflow.applyTemplateAndSave(tpl.id))}
                  >
                    {t('templateSaveAndOpen')}
                  </Button>
                </div>
              ))}
              {!workflow.templatesQuery.data?.length && !workflow.templatesQuery.isLoading ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('templatesEmpty')}
                </Typography.Text>
              ) : null}
            </div>
          </section>

          <section className="workflow-studio__panel workflow-studio__panel--grow">
            <div className="workflow-studio__panel-title">{t('library')}</div>
            <Select
              getPopupContainer={studioPopupContainer}
              style={{ width: '100%' }}
              placeholder={t('loadPlaceholder')}
              value={workflow.state.workflowId ?? undefined}
              allowClear
              showSearch
              filterOption={false}
              searchValue={workflow.librarySearch}
              onSearch={workflow.setLibrarySearch}
              onClear={() => workflow.setLibrarySearch('')}
              loading={
                workflow.state.loading ||
                workflow.workflowsQuery.isLoading ||
                workflow.workflowsQuery.isFetchingNextPage
              }
              disabled={workflow.state.loading}
              options={saved.map((item) => ({
                value: item.id,
                label: `${item.name} (v${item.version})`,
              }))}
              notFoundContent={
                workflow.workflowsQuery.isFetching
                  ? t('librarySearching')
                  : workflow.librarySearch.trim()
                    ? t('librarySearchEmpty')
                    : t('libraryEmpty')
              }
              onChange={(value) => {
                if (value) {
                  confirmLeaveStudio(() => {
                    workflow.setLibrarySearch('')
                    workflow.load(value)
                  })
                } else {
                  confirmLeaveStudio(() => {
                    workflow.setLibrarySearch('')
                    workflow.reset()
                  })
                }
              }}
            />
            {workflow.workflowsQuery.hasNextPage ? (
              <Button
                type="link"
                size="small"
                style={{ paddingInline: 0, marginTop: 2 }}
                loading={Boolean(workflow.workflowsQuery.isFetchingNextPage)}
                onClick={() => void workflow.workflowsQuery.fetchNextPage()}
              >
                {t('libraryLoadMore', {
                  shown: saved.length,
                  total: workflowListMeta?.total_count ?? saved.length,
                })}
              </Button>
            ) : null}
            {!workflow.librarySearch.trim() &&
            !workflow.workflowsQuery.isFetching &&
            (workflowListMeta?.total_count ?? saved.length) === 0 &&
            canWrite ? (
              <Button
                type="link"
                size="small"
                style={{ paddingInline: 0, marginTop: 4 }}
                onClick={() => confirmLeaveStudio(() => workflow.startFromTemplate('ir-triage'))}
              >
                {t('startFromTemplate')}
              </Button>
            ) : null}
            {workflow.state.workflowId ? (
              <Button
                danger
                type="link"
                style={{ paddingInline: 0, marginTop: 4 }}
                onClick={() => {
                  modal.confirm({
                    title: t('deleteSavedTitle'),
                    content: workflow.state.running
                      ? t('deleteSavedRunningContent')
                      : workflow.state.dirty
                        ? t('deleteSavedDirtyContent')
                        : t('deleteSavedContent'),
                    okText: t('deleteSavedConfirm'),
                    cancelText: t('common:cancel'),
                    okButtonProps: { danger: true },
                    onOk: () => {
                      if (workflow.state.running) workflow.stop()
                      void workflow.removeSaved()
                    },
                  })
                }}
              >
                {t('deleteSaved')}
              </Button>
            ) : null}
            {versions.length ? (
              <>
                <div className="workflow-studio__panel-title" style={{ marginTop: 12 }}>
                  {t('versions')}
                </div>
                <Select
                  getPopupContainer={studioPopupContainer}
                  style={{ width: '100%' }}
                  placeholder={t('restoreVersion')}
                  options={versions.map((item) => ({
                    value: item.version,
                    label: `v${item.version}`,
                  }))}
                  onChange={(version) =>
                    confirmLeaveStudio(() => void workflow.restoreVersion(Number(version)))
                  }
                />
              </>
            ) : null}
          </section>
        </aside>

        {/* Center stage: React Flow canvas (chrome only in WorkflowCanvas) */}
        <section className="workflow-studio__canvas">
          <WorkflowCanvas
            steps={workflow.state.steps}
            selectedId={workflow.state.selectedId}
            selectedIds={workflow.state.selectedIds}
            running={workflow.state.running}
            onStop={workflow.stop}
            executorNames={executorNames}
            onSelect={workflow.select}
            onSelectMany={workflow.selectMany}
            onPositionsChange={workflow.applyPositions}
            onConnectSequence={workflow.connectSequence}
            onConnectBranch={connectBranchWithHitlGuard}
            onDropNode={(type, position, target) => workflow.addAt(type, position, target)}
            onReparent={reparentWithHitlGuard}
            onEmptySlot={(parentId, slotKey) => workflow.addToSlot(parentId, slotKey)}
            onDeleteSelected={workflow.removeSelected}
            onFocusInspector={focusInspectorForNode}
            onUndo={workflow.undo}
            onRedo={workflow.redo}
            onCopy={copyWithGuard}
            onPaste={pasteWithHitlGuard}
            onOrganize={workflow.organizeLayout}
            onDuplicateSelected={duplicateWithHitlGuard}
            nodeRunStatus={workflow.state.nodeRunStatus}
            validationIssues={workflow.state.validationIssues}
            validationEpoch={workflow.state.validationEpoch}
            focusEpoch={workflow.state.focusEpoch}
            emptyHint={t('canvasEmptyHint')}
            emptyActionLabel={canWrite ? t('startFromTemplate') : undefined}
            onEmptyAction={
              canWrite ? () => confirmLeaveStudio(() => workflow.startFromTemplate('ir-triage')) : undefined
            }
          />
        </section>

        {/* Right rail: inspector forms + run log (domain actions via useWorkflow) */}
        <aside className="workflow-studio__right">
          <section
            ref={inspectorPanelRef}
            className={`workflow-studio__panel workflow-studio__panel--grow${
              workflow.state.running ? ' is-definition-locked' : ''
            }`}
          >
            {workflow.state.validationIssues.length ? (
              <Alert
                type="error"
                showIcon
                className="workflow-studio__validation"
                title={t('validationTitle')}
                description={
                  <ul className="workflow-validation-list">
                    {workflow.state.validationIssues.slice(0, 8).map((issue, index) => (
                      <li key={`${issue.code}-${issue.nodeId ?? 'root'}-${index}`}>
                        <Button
                          type="link"
                          size="small"
                          style={{ paddingInline: 0, height: 'auto' }}
                          onClick={() => {
                            focusFieldRef.current = fieldForValidationIssue(issue)
                            if (issue.nodeId) workflow.select(issue.nodeId)
                            // Re-trigger inspector focus even if the node was already selected.
                            workflow.patchMeta({
                              validationEpoch: workflow.state.validationEpoch + 1,
                            })
                          }}
                        >
                          {issue.message}
                        </Button>
                      </li>
                    ))}
                  </ul>
                }
              />
            ) : null}
            <div className="workflow-studio__panel-title">
              {t('inspector')}
              {workflow.state.running ? (
                <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                  {t('inspectorLockedWhileRunning')}
                </Typography.Text>
              ) : null}
              {workflow.state.selectedIds.length > 1 ? (
                <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                  {t('selectedCount', { count: workflow.state.selectedIds.length })}
                </Typography.Text>
              ) : null}
              {workflow.state.selectedIds.length > 1 ? (
                <>
                  <Tooltip title={t('clearSelection')} getPopupContainer={studioPopupContainer}>
                    <Button
                      size="small"
                      type="text"
                      icon={<CloseOutlined />}
                      aria-label={t('clearSelection')}
                      onClick={() => workflow.select(null)}
                    />
                  </Tooltip>
                  <Tooltip title={t('deleteSelected')} getPopupContainer={studioPopupContainer}>
                    <Button
                      size="small"
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      disabled={workflow.state.running}
                      onClick={() => workflow.removeSelected()}
                    />
                  </Tooltip>
                </>
              ) : step ? (
                <Tooltip title={t('deleteNode')} getPopupContainer={studioPopupContainer}>
                  <Button
                    size="small"
                    type="text"
                    danger
                    disabled={workflow.state.running}
                    icon={<DeleteOutlined />}
                    onClick={() => workflow.remove(step.id)}
                  />
                </Tooltip>
              ) : null}
            </div>

            {workflow.state.selectedIds.length > 1 ? (
              <div className="workflow-inspector nodrag nowheel">
                <Alert
                  type="info"
                  showIcon
                  className="workflow-studio__validation"
                  title={t('multiSelectHint', { count: workflow.state.selectedIds.length })}
                  description={t('multiSelectAgentHint')}
                  style={{ marginBottom: 12 }}
                />
                {(() => {
                  const agentSteps = workflow.state.selectedIds
                    .map((id) => findNode(workflow.state.steps, id))
                    .filter((node): node is NonNullable<typeof node> => Boolean(node))
                    .filter((node) => node.type === 'step')
                  const summary = summarizeSelectedAgentSteps(agentSteps)
                  const {
                    agentCount,
                    sharedTargetId: sharedTarget,
                    skillsMixed,
                    sharedSkills,
                    instructionsMixed,
                    sharedInstructions,
                    allConfirm,
                    noneConfirm,
                    allUserInput,
                    noneUserInput,
                    allOutputReview,
                    noneOutputReview,
                  } = summary
                  if (!agentCount) {
                    return (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t('multiSelectNoAgents')}
                      </Typography.Text>
                    )
                  }
                  return (
                    <Space orientation="vertical" style={{ width: '100%' }} size={10}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t('multiSelectAgentCount', { count: agentCount })}
                      </Typography.Text>
                      <div data-inspector-field="executor">
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 11, display: 'block', marginBottom: 4 }}
                        >
                          {t('executorLabel')}
                        </Typography.Text>
                        <Select
                          getPopupContainer={studioPopupContainer}
                          style={{ width: '100%' }}
                          placeholder={t('multiSelectExecutorPlaceholder')}
                          value={sharedTarget}
                          optionLabelProp="label"
                          options={executors.map((item) => ({
                            value: item.ref,
                            label: item.name,
                            title: item.description,
                            item,
                          }))}
                          optionRender={(option) => {
                            const item = (option.data as { item?: (typeof executors)[number] }).item
                            if (!item) return option.label
                            return (
                              <div className="workflow-executor-option">
                                <div className="workflow-executor-option__title">
                                  <strong>{item.name}</strong>
                                </div>
                                {item.description ? (
                                  <Typography.Text
                                    type="secondary"
                                    style={{ fontSize: 11, display: 'block' }}
                                  >
                                    {item.description}
                                  </Typography.Text>
                                ) : null}
                              </div>
                            )
                          }}
                          onChange={(value) => {
                            if (!value) return
                            workflow.updateSelectedSteps({ targetId: value })
                          }}
                        />
                      </div>
                      <div data-inspector-field="skills">
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 11, display: 'block', marginBottom: 4 }}
                        >
                          {t('stepSkills')}
                        </Typography.Text>
                        <Select
                          mode="multiple"
                          allowClear
                          size="small"
                          className="nodrag nowheel"
                          style={{ width: '100%' }}
                          placeholder={t('multiSelectSkillsPlaceholder')}
                          options={enabledSkillOptions}
                          optionFilterProp="label"
                          value={sharedSkills}
                          loading={skillsQuery.isLoading}
                          getPopupContainer={studioPopupContainer}
                          onChange={(value) =>
                            workflow.updateSelectedSteps({
                              skills: Array.isArray(value) ? value.map(String) : [],
                            })
                          }
                          maxTagCount="responsive"
                        />
                        <Typography.Paragraph
                          type="secondary"
                          style={{ fontSize: 11, marginTop: 4, marginBottom: 0 }}
                        >
                          {skillsMixed ? t('multiSelectSkillsMixed') : t('stepSkillsHint')}
                        </Typography.Paragraph>
                      </div>
                      <div data-inspector-field="instructions">
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 11, display: 'block', marginBottom: 4 }}
                        >
                          {t('instructionsLabel')}
                        </Typography.Text>
                        <Input.TextArea
                          className="nodrag nowheel"
                          rows={3}
                          value={sharedInstructions}
                          placeholder={
                            instructionsMixed
                              ? t('multiSelectInstructionsMixed')
                              : t('instructionsPlaceholder')
                          }
                          onChange={(e) =>
                            workflow.updateSelectedSteps({ instructions: e.target.value })
                          }
                        />
                        {instructionsMixed ? (
                          <Typography.Paragraph
                            type="secondary"
                            style={{ fontSize: 11, marginTop: 4, marginBottom: 0 }}
                          >
                            {t('multiSelectInstructionsHint')}
                          </Typography.Paragraph>
                        ) : null}
                      </div>
                      {agentSteps.some((node) => isInsideParallel(workflow.state.steps, node.id)) ? (
                        <Typography.Paragraph
                          type="secondary"
                          style={{ fontSize: 11, marginBottom: 4 }}
                        >
                          {t('multiSelectHitlParallelHint')}
                        </Typography.Paragraph>
                      ) : null}
                      <Checkbox
                        className="nodrag"
                        checked={allConfirm}
                        indeterminate={!allConfirm && !noneConfirm}
                        onChange={(e) =>
                          bulkHitlWithGuard({
                            requiresConfirmation: e.target.checked,
                          })
                        }
                      >
                        {t('requiresConfirmation')}
                      </Checkbox>
                      <Checkbox
                        className="nodrag"
                        checked={allUserInput}
                        indeterminate={!allUserInput && !noneUserInput}
                        onChange={(e) =>
                          bulkHitlWithGuard({
                            requiresUserInput: e.target.checked,
                          })
                        }
                      >
                        {t('requiresUserInput')}
                      </Checkbox>
                      <Checkbox
                        className="nodrag"
                        checked={allOutputReview}
                        indeterminate={!allOutputReview && !noneOutputReview}
                        onChange={(e) =>
                          bulkHitlWithGuard({
                            requiresOutputReview: e.target.checked,
                          })
                        }
                      >
                        {t('requiresOutputReview')}
                      </Checkbox>
                      <Space size={8} wrap>
                        <Button size="small" onClick={() => workflow.select(null)}>
                          {t('clearSelection')}
                        </Button>
                        <Button size="small" danger onClick={() => workflow.removeSelected()}>
                          {t('deleteSelected')}
                        </Button>
                      </Space>
                    </Space>
                  )
                })()}
              </div>
            ) : !step ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectStep')} />
            ) : (
              <div className="workflow-inspector nodrag nowheel">
                <Tag color="processing">{t(`nodeType_${step.type}`)}</Tag>
                <Input
                  className="nodrag nowheel"
                  data-inspector-field="name"
                  value={step.name}
                  onChange={(e) => workflow.update({ ...step, name: e.target.value })}
                  placeholder={
                    step.type === 'step'
                      ? executorNames.get(step.targetId || '') || t('stepNamePlaceholder')
                      : t('stepNamePlaceholder')
                  }
                  style={{ marginTop: 8 }}
                />
                {step.type === 'step' && !(step.name || '').trim() ? (
                  <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    {t('stepNameHint')}
                  </Typography.Text>
                ) : null}

                {step.type === 'step' ? (
                  <>
                    <div data-inspector-field="executor" style={{ marginTop: 8 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                        {t('executorLabel')}
                      </Typography.Text>
                      <Select
                        getPopupContainer={studioPopupContainer}
                        style={{ width: '100%' }}
                        placeholder={t('executorPlaceholder')}
                        value={step.targetId}
                        optionLabelProp="label"
                        options={executors.map((item) => ({
                          value: item.ref,
                          label: item.name,
                          title: item.description,
                          item,
                        }))}
                        optionRender={(option) => {
                          const item = (option.data as { item?: (typeof executors)[number] }).item
                          if (!item) return option.label
                          return (
                            <div className="workflow-executor-option">
                              <div className="workflow-executor-option__title">
                                <strong>{item.name}</strong>
                                <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
                                  {item.ref}
                                </Typography.Text>
                              </div>
                              {item.description ? (
                                <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                                  {item.description}
                                </Typography.Text>
                              ) : null}
                              {item.recommendedFor ? (
                                <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
                                  {t('executorRecommended', { text: item.recommendedFor })}
                                </Typography.Text>
                              ) : null}
                            </div>
                          )
                        }}
                        onChange={(value) => workflow.update({ ...step, targetId: value })}
                      />
                      {(() => {
                        const selected = executors.find((item) => item.ref === step.targetId)
                        if (!selected?.description) return null
                        return (
                          <Typography.Paragraph type="secondary" style={{ fontSize: 11, marginTop: 6, marginBottom: 0 }}>
                            {selected.description}
                            {selected.recommendedFor
                              ? ` · ${t('executorRecommended', { text: selected.recommendedFor })}`
                              : ''}
                          </Typography.Paragraph>
                        )
                      })()}
                    </div>
                    <Typography.Text
                      type="secondary"
                      style={{ fontSize: 11, display: 'block', marginTop: 8 }}
                    >
                      {t('instructionsLabel')}
                    </Typography.Text>
                    <Input.TextArea
                      style={{ marginTop: 4 }}
                      value={step.instructions}
                      onChange={(e) =>
                        workflow.update({ ...step, instructions: e.target.value })
                      }
                      placeholder={t('instructionsPlaceholder')}
                      rows={4}
                    />
                    <Typography.Text
                      type="secondary"
                      style={{ fontSize: 11, display: 'block', marginTop: 8 }}
                    >
                      {t('stepSkills')}
                    </Typography.Text>
                    <Select
                      mode="multiple"
                      allowClear
                      size="small"
                      style={{ width: '100%', marginTop: 4 }}
                      placeholder={t('stepSkillsPlaceholder')}
                      options={enabledSkillOptions}
                      optionFilterProp="label"
                      value={step.skills ?? []}
                      loading={skillsQuery.isLoading}
                      getPopupContainer={studioPopupContainer}
                      onChange={(value) =>
                        workflow.update({
                          ...step,
                          skills: Array.isArray(value) ? value.map(String) : [],
                        })
                      }
                      maxTagCount="responsive"
                    />
                    <Typography.Paragraph
                      type="secondary"
                      style={{ fontSize: 11, marginTop: 4, marginBottom: 0 }}
                    >
                      {t('stepSkillsHint')}
                    </Typography.Paragraph>
                    <div className="workflow-inspector__switch" data-inspector-field="hitl">
                      <Switch
                        size="small"
                        disabled={stepInsideParallel}
                        checked={Boolean(step.requiresConfirmation)}
                        onChange={(checked) =>
                          workflow.update({ ...step, requiresConfirmation: checked })
                        }
                      />
                      <span>{t('requiresConfirmation')}</span>
                    </div>
                    {stepInsideParallel ? (
                      <Typography.Paragraph
                        type="secondary"
                        style={{ fontSize: 11, marginTop: 0, marginBottom: 8 }}
                      >
                        {t('hitlBlockedInParallel')}
                      </Typography.Paragraph>
                    ) : null}
                    {step.requiresConfirmation ? (
                      <Input.TextArea
                        value={step.confirmationMessage || ''}
                        onChange={(e) =>
                          workflow.update({ ...step, confirmationMessage: e.target.value })
                        }
                        placeholder={t('confirmationMessagePlaceholder')}
                        rows={2}
                      />
                    ) : null}
                    <div className="workflow-inspector__switch" data-inspector-field="userInput">
                      <Switch
                        size="small"
                        disabled={stepInsideParallel}
                        checked={Boolean(step.requiresUserInput)}
                        onChange={(checked) =>
                          workflow.update({
                            ...step,
                            requiresUserInput: checked,
                            userInputSchema:
                              checked && !(step.userInputSchema?.length)
                                ? [
                                    {
                                      name: 'response',
                                      field_type: 'str',
                                      description: '',
                                      required: true,
                                    },
                                  ]
                                : step.userInputSchema,
                          })
                        }
                      />
                      <span>{t('requiresUserInput')}</span>
                    </div>
                    {step.requiresUserInput ? (
                      <>
                        <Input.TextArea
                          value={step.userInputMessage || ''}
                          onChange={(e) =>
                            workflow.update({ ...step, userInputMessage: e.target.value })
                          }
                          placeholder={t('userInputMessagePlaceholder')}
                          rows={2}
                        />
                        <div className="workflow-inspector__schema" style={{ marginTop: 8 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {t('userInputSchemaLabel')}
                          </Typography.Text>
                          <Space orientation="vertical" style={{ width: '100%', marginTop: 6 }} size={8}>
                            {(
                              step.userInputSchema ?? [
                                {
                                  name: 'response',
                                  field_type: 'str',
                                  description: '',
                                  required: true,
                                },
                              ]
                            ).map((field, index) => (
                              <div
                                key={`schema-${index}`}
                                style={{
                                  border: '1px solid var(--ant-color-border-secondary, #f0f0f0)',
                                  borderRadius: 8,
                                  padding: 8,
                                }}
                              >
                                <Space wrap style={{ width: '100%' }} size={6}>
                                  <Input
                                    style={{ width: 120 }}
                                    value={field.name}
                                    placeholder={t('userInputFieldName')}
                                    onChange={(e) => {
                                      const next = [
                                        ...(step.userInputSchema ?? [
                                          {
                                            name: 'response',
                                            field_type: 'str',
                                            description: '',
                                            required: true,
                                          },
                                        ]),
                                      ]
                                      next[index] = { ...next[index], name: e.target.value }
                                      workflow.update({ ...step, userInputSchema: next })
                                    }}
                                  />
                                  <Select
                                    style={{ width: 110 }}
                                    value={field.field_type || 'str'}
                                    options={[
                                      { value: 'str', label: t('fieldTypeStr') },
                                      { value: 'text', label: t('fieldTypeText') },
                                      { value: 'number', label: t('fieldTypeNumber') },
                                      { value: 'bool', label: t('fieldTypeBool') },
                                    ]}
                                    onChange={(value) => {
                                      const base =
                                        step.userInputSchema ??
                                        [
                                          {
                                            name: 'response',
                                            field_type: 'str',
                                            description: '',
                                            required: true,
                                          },
                                        ]
                                      const next = base.map((item, i) =>
                                        i === index ? { ...item, field_type: value } : item,
                                      )
                                      workflow.update({ ...step, userInputSchema: next })
                                    }}
                                  />
                                  <Switch
                                    size="small"
                                    checked={field.required !== false}
                                    onChange={(checked) => {
                                      const base =
                                        step.userInputSchema ??
                                        [
                                          {
                                            name: 'response',
                                            field_type: 'str',
                                            description: '',
                                            required: true,
                                          },
                                        ]
                                      const next = base.map((item, i) =>
                                        i === index ? { ...item, required: checked } : item,
                                      )
                                      workflow.update({ ...step, userInputSchema: next })
                                    }}
                                  />
                                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                                    {t('userInputFieldRequired')}
                                  </Typography.Text>
                                  <Button
                                    type="text"
                                    danger
                                    size="small"
                                    disabled={
                                      (step.userInputSchema ?? [{ name: 'response' }]).length <= 1
                                    }
                                    onClick={() => {
                                      const base =
                                        step.userInputSchema ??
                                        [
                                          {
                                            name: 'response',
                                            field_type: 'str',
                                            description: '',
                                            required: true,
                                          },
                                        ]
                                      workflow.update({
                                        ...step,
                                        userInputSchema: base.filter((_, i) => i !== index),
                                      })
                                    }}
                                  >
                                    {t('userInputFieldRemove')}
                                  </Button>
                                </Space>
                                <Input
                                  style={{ marginTop: 6 }}
                                  value={field.description || ''}
                                  placeholder={t('userInputFieldDescription')}
                                  onChange={(e) => {
                                    const base =
                                      step.userInputSchema ??
                                      [
                                        {
                                          name: 'response',
                                          field_type: 'str',
                                          description: '',
                                          required: true,
                                        },
                                      ]
                                    const next = base.map((item, i) =>
                                      i === index ? { ...item, description: e.target.value } : item,
                                    )
                                    workflow.update({ ...step, userInputSchema: next })
                                  }}
                                />
                              </div>
                            ))}
                            <Button
                              size="small"
                              type="dashed"
                              block
                              onClick={() => {
                                const base =
                                  step.userInputSchema ??
                                  [
                                    {
                                      name: 'response',
                                      field_type: 'str',
                                      description: '',
                                      required: true,
                                    },
                                  ]
                                workflow.update({
                                  ...step,
                                  userInputSchema: [
                                    ...base,
                                    {
                                      name: `field_${base.length + 1}`,
                                      field_type: 'str',
                                      description: '',
                                      required: true,
                                    },
                                  ],
                                })
                              }}
                            >
                              {t('userInputFieldAdd')}
                            </Button>
                          </Space>
                          <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
                            {t('userInputSchemaHint')}
                          </Typography.Text>
                        </div>
                      </>
                    ) : null}
                    <div className="workflow-inspector__switch">
                      <Switch
                        size="small"
                        disabled={stepInsideParallel}
                        checked={Boolean(step.requiresOutputReview)}
                        onChange={(checked) =>
                          workflow.update({ ...step, requiresOutputReview: checked })
                        }
                      />
                      <span>{t('requiresOutputReview')}</span>
                    </div>
                    {step.requiresOutputReview ? (
                      <Input.TextArea
                        value={step.outputReviewMessage || ''}
                        onChange={(e) =>
                          workflow.update({ ...step, outputReviewMessage: e.target.value })
                        }
                        placeholder={t('outputReviewMessagePlaceholder')}
                        rows={2}
                      />
                    ) : null}
                  </>
                ) : null}

                {step.type === 'condition' ? (
                  <>
                    <div data-inspector-field="evaluator">
                      <Typography.Text type="secondary">{t('evaluatorCel')}</Typography.Text>
                      <CelExpressionField
                        mode="condition"
                        value={step.evaluatorCel}
                        onChange={(value) => workflow.update({ ...step, evaluatorCel: value })}
                        placeholder={t('celPlaceholder')}
                      />
                    </div>
                    <div data-inspector-field="children" style={{ marginTop: 8 }}>
                      <Space wrap>
                        <Button
                          size="small"
                          icon={<PlusOutlined />}
                          onClick={() => workflow.addChild(step.id, 'thenSteps', 'step')}
                        >
                          {t('addThenStep')}
                        </Button>
                        <Button
                          size="small"
                          icon={<PlusOutlined />}
                          onClick={() => workflow.addChild(step.id, 'elseSteps', 'step')}
                        >
                          {t('addElseStep')}
                        </Button>
                      </Space>
                    </div>
                  </>
                ) : null}

                {step.type === 'loop' ? (
                  <>
                    <Typography.Text type="secondary">{t('maxIterations')}</Typography.Text>
                    <InputNumber
                      min={1}
                      max={20}
                      style={{ width: '100%', marginTop: 4 }}
                      value={step.maxIterations ?? 3}
                      onChange={(value) =>
                        workflow.update({ ...step, maxIterations: Number(value) || 3 })
                      }
                    />
                    <Typography.Text type="secondary">{t('endConditionCel')}</Typography.Text>
                    <CelExpressionField
                      mode="loop"
                      value={step.endConditionCel}
                      onChange={(value) => workflow.update({ ...step, endConditionCel: value })}
                      placeholder={t('celPlaceholder')}
                    />
                    <Button
                      size="small"
                      icon={<PlusOutlined />}
                      data-inspector-field="children"
                      style={{ marginTop: 8 }}
                      onClick={() => workflow.addChild(step.id, 'steps', 'step')}
                    >
                      {t('addLoopStep')}
                    </Button>
                  </>
                ) : null}

                {step.type === 'parallel' ? (
                  <Button
                    size="small"
                    icon={<PlusOutlined />}
                    data-inspector-field="children"
                    style={{ marginTop: 8 }}
                    onClick={() => workflow.addChild(step.id, 'steps', 'step')}
                  >
                    {t('addParallelBranch')}
                  </Button>
                ) : null}

                {step.type === 'router' ? (
                  <>
                    <div data-inspector-field="selector">
                      <Typography.Text type="secondary">{t('selectorCel')}</Typography.Text>
                      <CelExpressionField
                        mode="router"
                        value={step.selectorCel}
                        onChange={(value) => workflow.update({ ...step, selectorCel: value })}
                        placeholder={t('celPlaceholder')}
                      />
                    </div>
                    <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                      {t('routerChoicesHint')}
                    </Typography.Paragraph>
                  </>
                ) : null}

                {step.type === 'workflow_ref' ? (
                  <div data-inspector-field="workflow_ref" style={{ marginTop: 8 }}>
                    <Select
                      getPopupContainer={studioPopupContainer}
                      style={{ width: '100%' }}
                      placeholder={t('nestedWorkflowPlaceholder')}
                      value={step.workflowId || undefined}
                      options={saved
                        .filter((item) => item.id !== workflow.state.workflowId)
                        .map((item) => ({ value: item.id, label: item.name }))}
                      onChange={(value) => workflow.update({ ...step, workflowId: value })}
                    />
                  </div>
                ) : null}
              </div>
            )}
          </section>

          <section className="workflow-studio__panel">
            <Collapse
              size="small"
              bordered={false}
              activeKey={runPanelKeys}
              onChange={(keys) =>
                setRunPanelKeys(Array.isArray(keys) ? keys.map(String) : [String(keys)])
              }
              destroyOnHidden
              items={[
                {
                  key: 'run',
                  label: t('runLog'),
                  children: (
                    <>
                      <Input.TextArea
                        value={workflow.state.input}
                        onChange={(e) =>
                          workflow.patchMeta({
                            input: e.target.value,
                            dirty: workflow.state.dirty,
                          })
                        }
                        placeholder={t('inputPlaceholder')}
                        rows={3}
                        style={{ marginBottom: 8 }}
                      />
                      <Space size={8} wrap style={{ marginBottom: 8 }}>
                        {workflow.state.lastSessionId ? (
                          <Button
                            type="link"
                            size="small"
                            style={{ paddingInline: 0 }}
                            onClick={() =>
                              void routerNav.navigate({
                                to: '/trace',
                                search: {
                                  session_id: workflow.state.lastSessionId ?? undefined,
                                  run_id: workflow.state.lastRunId ?? undefined,
                                  selected_session: workflow.state.lastSessionId ?? undefined,
                                  trace: workflow.state.lastRunId ?? undefined,
                                },
                              })
                            }
                          >
                            {t('openTrace')}
                          </Button>
                        ) : null}
                        {workflow.state.lastApprovalId ? (
                          <Button
                            type="link"
                            size="small"
                            style={{ paddingInline: 0 }}
                            onClick={() => {
                              window.location.hash = `#/approvals?approval_id=${encodeURIComponent(workflow.state.lastApprovalId!)}`
                            }}
                          >
                            {t('openApproval')}
                          </Button>
                        ) : null}
                      </Space>
                      {workflow.state.runHistory.length ? (
                        <div style={{ marginBottom: 10 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {t('runHistory')}
                          </Typography.Text>
                          <div className="workflow-compact-list">
                            {workflow.state.runHistory.slice(0, 8).map((item) => (
                              <div key={item.id} className="workflow-compact-list__item">
                                <Space size={4} wrap>
                                  <Tag
                                    color={
                                      item.status === 'completed'
                                        ? 'success'
                                        : item.status === 'failed'
                                          ? 'error'
                                          : item.status === 'cancelled' || item.status === 'paused'
                                            ? 'warning'
                                            : 'processing'
                                    }
                                    style={{ margin: 0 }}
                                  >
                                    {t(`historyStatus_${item.status}`)}
                                  </Tag>
                                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                    {item.summary || item.runId || item.sessionId}
                                  </Typography.Text>
                                  {item.sessionId ? (
                                    <Button
                                      type="link"
                                      size="small"
                                      style={{ paddingInline: 0, fontSize: 12 }}
                                      onClick={() =>
                                        void routerNav.navigate({
                                          to: '/trace',
                                          search: {
                                            session_id: item.sessionId,
                                            run_id: item.runId || undefined,
                                            selected_session: item.sessionId,
                                            trace: item.runId || undefined,
                                          },
                                        })
                                      }
                                    >
                                      Trace
                                    </Button>
                                  ) : null}
                                  {item.approvalId ? (
                                    <Button
                                      type="link"
                                      size="small"
                                      style={{ paddingInline: 0, fontSize: 12 }}
                                      onClick={() => {
                                        window.location.hash = `#/approvals?approval_id=${encodeURIComponent(item.approvalId!)}`
                                      }}
                                    >
                                      {t('openApproval')}
                                    </Button>
                                  ) : null}
                                </Space>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      {(() => {
                        const latestOutput = [...workflow.state.runLog]
                          .reverse()
                          .find(
                            (item) =>
                              Boolean(item.content?.trim()) &&
                              (item.type === 'step.completed' ||
                                item.type === 'workflow.completed' ||
                                item.type.includes('completed')),
                          )
                        return latestOutput?.content ? (
                          <div className="workflow-run-output" style={{ marginBottom: 10 }}>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {t('latestOutput')}
                              {latestOutput.stepName ? ` · ${latestOutput.stepName}` : ''}
                            </Typography.Text>
                            <div className="workflow-run-output__body">
                              <Markdown content={latestOutput.content} openLinksInNewTab escapeRawHtml />
                            </div>
                          </div>
                        ) : null
                      })()}
                      {workflow.state.runLog.length ? (
                        <div className="workflow-compact-list workflow-run-log-list" ref={runLogListRef}>
                          {/* Chronological (oldest → newest): matches auto-scroll to bottom on new events. */}
                          {workflow.state.runLog.slice(-40).map((item) => (
                            <div key={item.id} className="workflow-compact-list__item">
                              <Space size={4} wrap>
                                <Tag
                                  color={
                                    item.type === 'workflow.paused' ||
                                    item.type === 'workflow.cancelled'
                                      ? 'warning'
                                      : item.type.includes('error') || item.type.includes('failed')
                                        ? 'error'
                                        : item.type.includes('completed')
                                          ? 'success'
                                          : 'default'
                                  }
                                  style={{ margin: 0 }}
                                >
                                  {(() => {
                                    const key = runEventLabelKey(item.type)
                                    return key ? t(key) : item.type
                                  })()}
                                </Tag>
                                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                  {item.stepName || item.message}
                                </Typography.Text>
                                {item.approvalId ? (
                                  <Button
                                    type="link"
                                    size="small"
                                    style={{ paddingInline: 0, fontSize: 12 }}
                                    onClick={() => {
                                      window.location.hash = `#/approvals?approval_id=${encodeURIComponent(item.approvalId!)}`
                                    }}
                                  >
                                    {t('openApproval')}
                                  </Button>
                                ) : null}
                              </Space>
                              {item.content &&
                              (item.type === 'step.completed' ||
                                item.type === 'workflow.completed' ||
                                item.type.includes('completed')) ? (
                                <div className="workflow-run-log-content">
                                  <Markdown content={item.content} openLinksInNewTab escapeRawHtml />
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={t('emptyRunLog')}
                        />
                      )}
                    </>
                  ),
                },
                {
                  key: 'def',
                  label: t('definition'),
                  children: (
                    <>
                      <Input.TextArea
                        value={workflow.state.description}
                        onChange={(e) => workflow.patch({ description: e.target.value })}
                        placeholder={t('descriptionPlaceholder')}
                        rows={2}
                      />
                      <div className="workflow-inspector__switch" style={{ marginTop: 8 }}>
                        <Switch
                          size="small"
                          checked={workflow.state.triggers.webhook.enabled}
                          disabled={!canWrite || workflow.state.running}
                          onChange={(enabled) => requestEnableTrigger('webhook', enabled)}
                        />
                        <span>{t('webhookTrigger')}</span>
                      </div>
                      {workflow.state.triggers.webhook.enabled && workflow.state.workflowId ? (
                        <div className="workflow-trigger-ops" style={{ marginTop: 8 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            {t('webhookUrl')}
                          </Typography.Text>
                          <Space.Compact style={{ width: '100%', marginTop: 4 }}>
                            <Input
                              size="small"
                              readOnly
                              value={workflowWebhookUrl(workflow.state.workflowId)}
                            />
                            <Tooltip title={t('copy')}>
                              <Button
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => {
                                  void copyToClipboard(
                                    workflowWebhookUrl(workflow.state.workflowId!)
                                  ).then((ok) =>
                                    ok
                                      ? message.success(t('copied'))
                                      : message.error(t('copyFailed'))
                                  )
                                }}
                              />
                            </Tooltip>
                          </Space.Compact>
                          <Typography.Text
                            type="secondary"
                            style={{ fontSize: 11, display: 'block', marginTop: 8 }}
                          >
                            {t('webhookSecret')}
                          </Typography.Text>
                          <Space.Compact style={{ width: '100%', marginTop: 4 }}>
                            <Input.Password
                              size="small"
                              value={workflow.state.triggers.webhook.secret}
                              onChange={(e) =>
                                workflow.patchTriggers({
                                  ...workflow.state.triggers,
                                  webhook: {
                                    ...workflow.state.triggers.webhook,
                                    secret: e.target.value,
                                  },
                                })
                              }
                              placeholder={t('webhookSecret')}
                            />
                            <Tooltip title={t('rotateSecret')}>
                              <Button
                                size="small"
                                icon={<ReloadOutlined />}
                                disabled={!canWrite || workflow.state.running}
                                onClick={() =>
                                  workflow.patchTriggers({
                                    ...workflow.state.triggers,
                                    webhook: {
                                      ...workflow.state.triggers.webhook,
                                      secret: rotateWebhookSecret(),
                                    },
                                  })
                                }
                              />
                            </Tooltip>
                            <Tooltip title={t('copy')}>
                              <Button
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => {
                                  void copyToClipboard(
                                    workflow.state.triggers.webhook.secret
                                  ).then((ok) =>
                                    ok
                                      ? message.success(t('copied'))
                                      : message.error(t('copyFailed'))
                                  )
                                }}
                              />
                            </Tooltip>
                          </Space.Compact>
                          <Typography.Text
                            type="secondary"
                            style={{ fontSize: 11, display: 'block', marginTop: 8 }}
                          >
                            {t('webhookCurl')}
                          </Typography.Text>
                          <Input.TextArea
                            size="small"
                            readOnly
                            autoSize={{ minRows: 3, maxRows: 5 }}
                            style={{ marginTop: 4, fontFamily: 'monospace', fontSize: 11 }}
                            value={workflowWebhookCurl(
                              workflow.state.workflowId,
                              workflow.state.triggers.webhook.secret
                            )}
                          />
                          <Button
                            type="link"
                            size="small"
                            style={{ paddingInline: 0, marginTop: 4 }}
                            icon={<CopyOutlined />}
                            onClick={() => {
                              void copyToClipboard(
                                workflowWebhookCurl(
                                  workflow.state.workflowId!,
                                  workflow.state.triggers.webhook.secret
                                )
                              ).then((ok) =>
                                ok
                                  ? message.success(t('copied'))
                                  : message.error(t('copyFailed'))
                              )
                            }}
                          >
                            {t('copyCurl')}
                          </Button>
                          <Typography.Paragraph
                            type="secondary"
                            style={{ fontSize: 11, marginTop: 4, marginBottom: 0 }}
                          >
                            {t('webhookSseHint')}
                          </Typography.Paragraph>
                        </div>
                      ) : workflow.state.triggers.webhook.enabled ? (
                        <Typography.Paragraph type="secondary" style={{ fontSize: 11, marginTop: 4 }}>
                          {t('webhookSaveFirst')}
                        </Typography.Paragraph>
                      ) : null}
                      <div className="workflow-inspector__switch" style={{ marginTop: 12 }}>
                        <Switch
                          size="small"
                          checked={workflow.state.triggers.cron.enabled}
                          disabled={!canWrite || workflow.state.running}
                          onChange={(enabled) => requestEnableTrigger('cron', enabled)}
                        />
                        <span>{t('cronTrigger')}</span>
                      </div>
                      {workflow.state.triggers.cron.enabled ? (
                        <div className="workflow-trigger-ops" style={{ marginTop: 4 }}>
                          <Input
                            size="small"
                            value={workflow.state.triggers.cron.expression}
                            onChange={(e) =>
                              workflow.patchTriggers({
                                ...workflow.state.triggers,
                                cron: {
                                  ...workflow.state.triggers.cron,
                                  expression: e.target.value,
                                },
                              })
                            }
                            placeholder={t('cronExpression')}
                          />
                          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--tais-muted)' }}>
                            <div>
                              {t('cronLastRun')}:{' '}
                              {workflow.state.triggers.cron.last_run_at
                                ? formatDate(workflow.state.triggers.cron.last_run_at)
                                : t('cronNever')}
                            </div>
                            <div>
                              {t('cronNextRun')}:{' '}
                              {workflow.state.nextCronAt
                                ? formatDate(workflow.state.nextCronAt)
                                : workflow.state.hasPublished
                                  ? t('cronNextUnknown')
                                  : t('cronNextNeedsPublish')}
                            </div>
                          </div>
                        </div>
                      ) : null}
                      <Typography.Paragraph type="secondary" style={{ fontSize: 11, marginTop: 8 }}>
                        {!workflow.state.hasPublished
                          ? t('publishTriggersHintUnpublished')
                          : workflow.state.dirty
                            ? t('publishTriggersHintDirty')
                            : t('publishTriggersHint')}
                      </Typography.Paragraph>
                      {workflow.state.workflowId ? (
                        <div style={{ marginTop: 12 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {t('triggerHistory')}
                          </Typography.Text>
                          {(triggerHistoryQuery.data?.data?.length ?? 0) > 0 ? (
                            <div className="workflow-compact-list">
                              {(triggerHistoryQuery.data?.data ?? []).map((item) => (
                                <div key={String(item.id)} className="workflow-compact-list__item">
                                  <Space size={4} wrap>
                                    <Tag
                                      color={
                                        item.status === 'success'
                                          ? 'success'
                                          : item.status === 'paused'
                                            ? 'warning'
                                            : item.status === 'started'
                                              ? 'processing'
                                              : 'error'
                                      }
                                      style={{ margin: 0 }}
                                    >
                                      {item.source === 'cron' || item.source === 'webhook'
                                        ? t(`triggerSource_${item.source}`)
                                        : item.source}
                                    </Tag>
                                    <Tag style={{ margin: 0 }}>
                                      {['success', 'error', 'failed', 'paused', 'started'].includes(
                                        String(item.status),
                                      )
                                        ? t(`triggerStatus_${item.status}`)
                                        : item.status}
                                    </Tag>
                                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                                      {item.created_at
                                        ? formatDate(item.created_at)
                                        : item.run_id || '-'}
                                    </Typography.Text>
                                    {item.status === 'error' || item.status === 'failed' ? (
                                      <Tag color="error" style={{ margin: 0 }}>
                                        {t('triggerFailed')}
                                      </Tag>
                                    ) : null}
                                    {item.session_id ? (
                                      <Button
                                        type="link"
                                        size="small"
                                        style={{ paddingInline: 0, fontSize: 12 }}
                                        onClick={() =>
                                          void routerNav.navigate({
                                            to: '/trace',
                                            search: {
                                              session_id: item.session_id,
                                              run_id: item.run_id || undefined,
                                              selected_session: item.session_id,
                                              trace: item.run_id || undefined,
                                            },
                                          })
                                        }
                                      >
                                        Trace
                                      </Button>
                                    ) : null}
                                  </Space>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <Typography.Paragraph type="secondary" style={{ fontSize: 11, marginTop: 4 }}>
                              {triggerHistoryQuery.isLoading ? '…' : t('triggerHistoryEmpty')}
                            </Typography.Paragraph>
                          )}
                        </div>
                      ) : null}
                    </>
                  ),
                },
                {
                  key: 'code',
                  label: t('generatedCode'),
                  children: <PayloadViewer value={buildWorkflowCode(workflow.state)} />,
                },
              ]}
            />
          </section>
        </aside>
      </div>
    </main>
  )
}
