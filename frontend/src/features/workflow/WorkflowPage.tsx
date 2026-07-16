import {
  Alert,
  App,
  Button,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  ApiOutlined,
  BranchesOutlined,
  ClusterOutlined,
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
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { useWorkflow } from './useWorkflow'
import { WorkflowCanvas, paletteDragStart } from './WorkflowCanvas'
import type { WorkflowNodeType } from './types'
import {
  buildWorkflowCode,
  rotateWebhookSecret,
  triggerEnableBlocked,
  workflowWebhookCurl,
  workflowWebhookUrl,
} from './utils'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import { listWorkflowTriggerHistory } from './api'
import { listSkills } from '@/features/skills/api'
import { CelExpressionField } from './CelExpressionField'
import { currentUserQuery } from '@/features/auth'
import { hasScope } from '@/shared/auth/permissions'
import { useFormatDate } from '@/shared/lib/format'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { useEffect, type ReactNode } from 'react'

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
  const currentUser = useQuery(currentUserQuery())
  const canRun =
    hasScope(currentUser.data, 'workflows:run') ||
    hasScope(currentUser.data, 'workflows:write')
  const canWrite = hasScope(currentUser.data, 'workflows:write')

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
            void workflow.publish()
          } else if (canWrite) {
            void workflow.save()
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
          if (canWrite) void workflow.save()
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
    .map((skill) => ({
      value: skill.name,
      label: skill.description ? `${skill.name} — ${skill.description}` : skill.name,
    }))
  const step = workflow.selected
  const executors = workflow.executorsQuery.data ?? []
  const models = workflow.modelsQuery.data?.models ?? []
  const saved = workflow.workflowsQuery.data?.data ?? []
  const workflowListMeta = workflow.workflowsQuery.data?.meta
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
          <div>
            <Typography.Title level={5} className="workflow-studio__title">
              {t('title')}
            </Typography.Title>
            <Typography.Text type="secondary" className="workflow-studio__subtitle">
              {t('studioHint')}
            </Typography.Text>
          </div>
        </div>
        <div className="workflow-studio__toolbar-main">
          <Input
            className="workflow-studio__name"
            value={workflow.state.name}
            onChange={(e) => workflow.patch({ name: e.target.value })}
            placeholder={t('namePlaceholder')}
            variant="borderless"
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
        <Space wrap className="workflow-studio__actions">
          <Button onClick={workflow.reset}>{t('new')}</Button>
          <Tooltip title={t('undoHint')} getPopupContainer={studioPopupContainer}>
            <Button
              icon={<UndoOutlined />}
              disabled={!workflow.canUndo}
              onClick={workflow.undo}
            />
          </Tooltip>
          <Tooltip title={t('redoHint')} getPopupContainer={studioPopupContainer}>
            <Button
              icon={<RedoOutlined />}
              disabled={!workflow.canRedo}
              onClick={workflow.redo}
            />
          </Tooltip>
          <Tooltip title={t('organizeHint')} getPopupContainer={studioPopupContainer}>
            <Button icon={<ApartmentOutlined />} onClick={workflow.organizeLayout}>
              {t('organize')}
            </Button>
          </Tooltip>
          <Button
            icon={<SaveOutlined />}
            type="primary"
            loading={workflow.state.saving}
            disabled={!canWrite}
            onClick={() => void workflow.save()}
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
              onClick={() => void workflow.publish()}
            >
              {t('publish')}
            </Button>
          </Tooltip>
          <Tooltip
            title={!canRun ? t('runScopeHint') : undefined}
            getPopupContainer={studioPopupContainer}
          >
            <Button
              icon={<PlayCircleOutlined />}
              disabled={workflow.state.running || !canRun}
              onClick={() => void workflow.run()}
            >
              {t('run')}
            </Button>
          </Tooltip>
          {workflow.state.running ? (
            <Button danger icon={<StopOutlined />} onClick={workflow.stop}>
              {t('stop')}
            </Button>
          ) : null}
        </Space>
      </header>
      {workflowListMeta && workflowListMeta.total_count > saved.length ? (
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


      {workflow.state.error ? (
        <Alert
          type="error"
          showIcon
          className="workflow-studio__banner"
          title={workflow.state.error}
          closable={{ onClose: () => workflow.patchMeta({ error: null }) }}
        />
      ) : null}

      <div className="workflow-studio__body">
        {/* Left: palette + library */}
        <aside className="workflow-studio__left">
          <section className="workflow-studio__panel">
            <div className="workflow-studio__panel-title">{t('palette')}</div>
            <div className="workflow-palette">
              {PALETTE.map((item) => (
                <div
                  key={item.type}
                  className="workflow-palette__item"
                  draggable
                  onDragStart={(event) => paletteDragStart(event, item.type)}
                  onDoubleClick={() => workflow.add(item.type)}
                  style={{ borderColor: item.color }}
                  title={t('paletteDragHint')}
                >
                  <span className="workflow-palette__icon" style={{ color: item.color }}>
                    {item.icon}
                  </span>
                  <span>{paletteLabel(item.type)}</span>
                </div>
              ))}
            </div>
            <Typography.Paragraph type="secondary" className="workflow-studio__hint">
              {t('paletteDragHint')}
            </Typography.Paragraph>
          </section>

          <section className="workflow-studio__panel">
            <div className="workflow-studio__panel-title">{t('templates')}</div>
            <div className="workflow-templates">
              {(workflow.templatesQuery.data ?? []).map((tpl) => (
                <div key={tpl.id} className="workflow-templates__item">
                  <button
                    type="button"
                    className="workflow-templates__load"
                    title={tpl.description}
                    disabled={!canWrite}
                    onClick={() => workflow.applyTemplate(tpl.id)}
                  >
                    <strong>{tpl.name}</strong>
                    <span>{tpl.description}</span>
                  </button>
                  <div className="workflow-templates__actions">
                    <Button
                      type="link"
                      size="small"
                      disabled={!canWrite || workflow.state.saving}
                      onClick={() => workflow.applyTemplate(tpl.id)}
                    >
                      {t('templateLoadDraft')}
                    </Button>
                    <Button
                      type="link"
                      size="small"
                      disabled={!canWrite || workflow.state.saving}
                      onClick={() => void workflow.applyTemplateAndSave(tpl.id)}
                    >
                      {t('templateSaveAndOpen')}
                    </Button>
                  </div>
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
              options={saved.map((item) => ({
                value: item.id,
                label: `${item.name} (v${item.version})`,
              }))}
              onChange={(value) => {
                if (value) workflow.load(value)
                else workflow.reset()
              }}
            />
            {workflow.state.workflowId ? (
              <Button
                danger
                type="link"
                style={{ paddingInline: 0, marginTop: 4 }}
                onClick={() => void workflow.removeSaved()}
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
                  onChange={(version) => void workflow.restoreVersion(Number(version))}
                />
              </>
            ) : null}
          </section>
        </aside>

        {/* Center: canvas */}
        <section className="workflow-studio__canvas">
          <WorkflowCanvas
            steps={workflow.state.steps}
            selectedId={workflow.state.selectedId}
            selectedIds={workflow.state.selectedIds}
            onSelect={workflow.select}
            onSelectMany={workflow.selectMany}
            onPositionsChange={workflow.applyPositions}
            onConnectSequence={workflow.connectSequence}
            onConnectBranch={workflow.connectBranch}
            onDropNode={(type, position, target) => workflow.addAt(type, position, target)}
            onReparent={workflow.reparent}
            onEmptySlot={(parentId, slotKey) => workflow.addToSlot(parentId, slotKey)}
            onDeleteSelected={workflow.removeSelected}
            onUndo={workflow.undo}
            onRedo={workflow.redo}
            onCopy={workflow.copySelected}
            onPaste={workflow.pasteClipboard}
            onOrganize={workflow.organizeLayout}
            onDuplicateSelected={workflow.duplicateSelected}
            nodeRunStatus={workflow.state.nodeRunStatus}
            validationIssues={workflow.state.validationIssues}
            emptyHint={t('canvasEmpty')}
            emptyActionLabel={canWrite ? t('startFromTemplate') : undefined}
            onEmptyAction={
              canWrite ? () => workflow.startFromTemplate('ir-triage') : undefined
            }
          />
        </section>

        {/* Right: inspector + run */}
        <aside className="workflow-studio__right">
          <section className="workflow-studio__panel workflow-studio__panel--grow">
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
                            if (issue.nodeId) workflow.select(issue.nodeId)
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
              {step ? (
                <Tooltip title={t('deleteNode')} getPopupContainer={studioPopupContainer}>
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => workflow.remove(step.id)}
                  />
                </Tooltip>
              ) : null}
            </div>

            {!step ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectStep')} />
            ) : (
              <div className="workflow-inspector nodrag nowheel">
                <Tag color="processing">{step.type}</Tag>
                <Input
                  className="nodrag nowheel"
                  value={step.name}
                  onChange={(e) => workflow.update({ ...step, name: e.target.value })}
                  placeholder={t('stepNamePlaceholder')}
                  style={{ marginTop: 8 }}
                />

                {step.type === 'step' ? (
                  <>
                    <Select
                      getPopupContainer={studioPopupContainer}
                      style={{ width: '100%', marginTop: 8 }}
                      placeholder={t('executorPlaceholder')}
                      value={step.targetId}
                      options={executors.map((item) => ({
                        value: item.ref,
                        label: `${item.name} (${item.ref})`,
                      }))}
                      onChange={(value) => workflow.update({ ...step, targetId: value })}
                    />
                    <Input.TextArea
                      style={{ marginTop: 8 }}
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
                    <div className="workflow-inspector__switch">
                      <Switch
                        size="small"
                        checked={Boolean(step.requiresConfirmation)}
                        onChange={(checked) =>
                          workflow.update({ ...step, requiresConfirmation: checked })
                        }
                      />
                      <span>{t('requiresConfirmation')}</span>
                    </div>
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
                    <div className="workflow-inspector__switch">
                      <Switch
                        size="small"
                        checked={Boolean(step.requiresUserInput)}
                        onChange={(checked) =>
                          workflow.update({ ...step, requiresUserInput: checked })
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
                        <Input.TextArea
                          style={{ marginTop: 8 }}
                          value={JSON.stringify(
                            step.userInputSchema ?? [
                              {
                                name: 'response',
                                field_type: 'str',
                                description: 'User response',
                                required: true,
                              },
                            ],
                            null,
                            2
                          )}
                          onChange={(e) => {
                            try {
                              const parsed = JSON.parse(e.target.value) as unknown
                              if (Array.isArray(parsed)) {
                                workflow.update({
                                  ...step,
                                  userInputSchema: parsed as Array<{
                                    name: string
                                    field_type?: string
                                    description?: string
                                    required?: boolean
                                  }>,
                                })
                              }
                            } catch {
                              // ignore partial JSON while typing
                            }
                          }}
                          placeholder={t('userInputSchemaPlaceholder')}
                          rows={5}
                        />
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                          {t('userInputSchemaHint')}
                        </Typography.Text>
                      </>
                    ) : null}
                    <div className="workflow-inspector__switch">
                      <Switch
                        size="small"
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
                    <Typography.Text type="secondary">{t('evaluatorCel')}</Typography.Text>
                    <CelExpressionField
                      mode="condition"
                      value={step.evaluatorCel}
                      onChange={(value) => workflow.update({ ...step, evaluatorCel: value })}
                      placeholder={t('celPlaceholder')}
                    />
                    <Space wrap style={{ marginTop: 8 }}>
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
                    style={{ marginTop: 8 }}
                    onClick={() => workflow.addChild(step.id, 'steps', 'step')}
                  >
                    {t('addParallelBranch')}
                  </Button>
                ) : null}

                {step.type === 'router' ? (
                  <>
                    <Typography.Text type="secondary">{t('selectorCel')}</Typography.Text>
                    <CelExpressionField
                      mode="router"
                      value={step.selectorCel}
                      onChange={(value) => workflow.update({ ...step, selectorCel: value })}
                      placeholder={t('celPlaceholder')}
                    />
                    <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                      {t('routerChoicesHint')}
                    </Typography.Paragraph>
                  </>
                ) : null}

                {step.type === 'workflow_ref' ? (
                  <Select
                    getPopupContainer={studioPopupContainer}
                    style={{ width: '100%', marginTop: 8 }}
                    placeholder={t('nestedWorkflowPlaceholder')}
                    value={step.workflowId || undefined}
                    options={saved
                      .filter((item) => item.id !== workflow.state.workflowId)
                      .map((item) => ({ value: item.id, label: item.name }))}
                    onChange={(value) => workflow.update({ ...step, workflowId: value })}
                  />
                ) : null}
              </div>
            )}
          </section>

          <section className="workflow-studio__panel">
            <Collapse
              size="small"
              bordered={false}
              defaultActiveKey={['run']}
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
                                        : item.status === 'failed' || item.status === 'cancelled'
                                          ? 'error'
                                          : item.status === 'paused'
                                            ? 'warning'
                                            : 'processing'
                                    }
                                    style={{ margin: 0 }}
                                  >
                                    {item.status}
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
                      {workflow.state.runLog.length ? (
                        <div className="workflow-compact-list">
                          {[...workflow.state.runLog].reverse().slice(0, 40).map((item) => (
                            <div key={item.id} className="workflow-compact-list__item">
                              <Space size={4} wrap>
                                <Tag
                                  color={
                                    item.type === 'workflow.paused'
                                      ? 'warning'
                                      : item.type.includes('error') || item.type.includes('failed')
                                        ? 'error'
                                        : item.type.includes('completed')
                                          ? 'success'
                                          : 'default'
                                  }
                                  style={{ margin: 0 }}
                                >
                                  {item.type}
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
                          disabled={!canWrite}
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
                                disabled={!canWrite}
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
                          disabled={!canWrite}
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
                                      {item.source}
                                    </Tag>
                                    <Tag style={{ margin: 0 }}>{item.status}</Tag>
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
