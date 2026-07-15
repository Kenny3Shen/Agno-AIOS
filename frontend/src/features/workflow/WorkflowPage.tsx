import {
  Alert,
  Button,
  Collapse,
  Empty,
  Input,
  InputNumber,
  List,
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
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useRouter } from '@tanstack/react-router'
import { useWorkflow } from './useWorkflow'
import { WorkflowCanvas, paletteDragStart } from './WorkflowCanvas'
import type { WorkflowNodeType } from './types'
import { buildWorkflowCode } from './utils'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import type { ReactNode } from 'react'

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

export function WorkflowPage() {
  const { t } = useTranslation('workflow')
  const routerNav = useRouter()
  const workflow = useWorkflow()
  const step = workflow.selected
  const executors = workflow.executorsQuery.data ?? []
  const models = workflow.modelsQuery.data?.models ?? []
  const saved = workflow.workflowsQuery.data ?? []
  const versions = workflow.versionsQuery.data ?? []

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
            <Typography.Title level={4} style={{ margin: 0 }}>
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
        </div>
        <Space wrap className="workflow-studio__actions">
          <Button onClick={workflow.reset}>{t('new')}</Button>
          <Tooltip title={t('undoHint')}>
            <Button
              icon={<UndoOutlined />}
              disabled={!workflow.canUndo}
              onClick={workflow.undo}
            />
          </Tooltip>
          <Tooltip title={t('redoHint')}>
            <Button
              icon={<RedoOutlined />}
              disabled={!workflow.canRedo}
              onClick={workflow.redo}
            />
          </Tooltip>
          <Tooltip title={t('organizeHint')}>
            <Button icon={<ApartmentOutlined />} onClick={workflow.organizeLayout}>
              {t('organize')}
            </Button>
          </Tooltip>
          <Button
            icon={<SaveOutlined />}
            type="primary"
            loading={workflow.state.saving}
            onClick={() => void workflow.save()}
          >
            {t('save')}
            {workflow.state.dirty ? ' *' : ''}
          </Button>
          <Button
            icon={<PlayCircleOutlined />}
            disabled={workflow.state.running}
            onClick={() => void workflow.run()}
          >
            {t('run')}
          </Button>
          {workflow.state.running ? (
            <Button danger icon={<StopOutlined />} onClick={workflow.stop}>
              {t('stop')}
            </Button>
          ) : null}
        </Space>
      </header>

      {workflow.state.error ? (
        <Alert
          type="error"
          showIcon
          closable
          style={{ margin: '0 12px 8px' }}
          message={workflow.state.error}
          onClose={() => workflow.patchMeta({ error: null })}
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

          <section className="workflow-studio__panel workflow-studio__panel--grow">
            <div className="workflow-studio__panel-title">{t('library')}</div>
            <Select
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
            onDropNode={(type, position, target) => workflow.addAt(type, position, target)}
            onReparent={workflow.reparent}
            onEmptySlot={(parentId, slotKey) => workflow.addToSlot(parentId, slotKey)}
            onDeleteSelected={workflow.removeSelected}
            onUndo={workflow.undo}
            onRedo={workflow.redo}
            onCopy={workflow.copySelected}
            onPaste={workflow.pasteClipboard}
            onOrganize={workflow.organizeLayout}
            emptyHint={t('canvasEmpty')}
          />
        </section>

        {/* Right: inspector + run */}
        <aside className="workflow-studio__right">
          <section className="workflow-studio__panel workflow-studio__panel--grow">
            <div className="workflow-studio__panel-title">
              {t('inspector')}
              {step ? (
                <Tooltip title={t('deleteNode')}>
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
              <div className="workflow-inspector">
                <Tag color="processing">{step.type}</Tag>
                <Input
                  value={step.name}
                  onChange={(e) => workflow.update({ ...step, name: e.target.value })}
                  placeholder={t('stepNamePlaceholder')}
                  style={{ marginTop: 8 }}
                />

                {step.type === 'step' ? (
                  <>
                    <Select
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
                      <Input.TextArea
                        value={step.userInputMessage || ''}
                        onChange={(e) =>
                          workflow.update({ ...step, userInputMessage: e.target.value })
                        }
                        placeholder={t('userInputMessagePlaceholder')}
                        rows={2}
                      />
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
                    <Input.TextArea
                      value={step.evaluatorCel}
                      onChange={(e) =>
                        workflow.update({ ...step, evaluatorCel: e.target.value })
                      }
                      rows={3}
                      style={{ marginTop: 4 }}
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
                    <Input.TextArea
                      value={step.endConditionCel}
                      onChange={(e) =>
                        workflow.update({ ...step, endConditionCel: e.target.value })
                      }
                      rows={3}
                      style={{ marginTop: 4 }}
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
                    <Input.TextArea
                      value={step.selectorCel}
                      onChange={(e) =>
                        workflow.update({ ...step, selectorCel: e.target.value })
                      }
                      rows={3}
                      style={{ marginTop: 4 }}
                    />
                    <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                      {t('routerChoicesHint')}
                    </Typography.Paragraph>
                  </>
                ) : null}

                {step.type === 'workflow_ref' ? (
                  <Select
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
              defaultActiveKey={['run']}
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
                                selected_session: workflow.state.lastSessionId ?? undefined,
                              },
                            })
                          }
                        >
                          {t('openTrace')}
                        </Button>
                      ) : null}
                      {workflow.state.runLog.length ? (
                        <List
                          size="small"
                          dataSource={[...workflow.state.runLog].reverse().slice(0, 40)}
                          renderItem={(item) => (
                            <List.Item style={{ padding: '4px 0' }}>
                              <Space size={4} wrap>
                                <Tag style={{ margin: 0 }}>{item.type}</Tag>
                                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                  {item.stepName || item.message}
                                </Typography.Text>
                              </Space>
                            </List.Item>
                          )}
                        />
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
                          onChange={(enabled) =>
                            workflow.patchTriggers({
                              ...workflow.state.triggers,
                              webhook: { ...workflow.state.triggers.webhook, enabled },
                            })
                          }
                        />
                        <span>{t('webhookTrigger')}</span>
                      </div>
                      {workflow.state.triggers.webhook.enabled ? (
                        <Input
                          size="small"
                          style={{ marginTop: 4 }}
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
