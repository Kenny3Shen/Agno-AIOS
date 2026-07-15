import {
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  Alert,
  List,
  Dropdown,
} from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  SaveOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import { useWorkflow } from './useWorkflow'
import { buildWorkflowCode, nodeLabel } from './utils'
import { WorkflowCanvas } from './WorkflowCanvas'
import type { WorkflowNode, WorkflowNodeType } from './types'
import { useTranslation } from 'react-i18next'
import { useRouter } from '@tanstack/react-router'

const typeColor: Record<WorkflowNodeType, string> = {
  step: 'blue',
  parallel: 'purple',
  condition: 'gold',
  loop: 'cyan',
  router: 'magenta',
  workflow_ref: 'green',
}

function NodeRow({
  node,
  index,
  depth,
  selectedId,
  onSelect,
}: {
  node: WorkflowNode
  index: number
  depth: number
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const children: Array<{ branch: string; child: WorkflowNode }> = []
  if (node.type === 'condition') {
    for (const child of node.thenSteps ?? []) children.push({ branch: 'then', child })
    for (const child of node.elseSteps ?? []) children.push({ branch: 'else', child })
  } else if (node.type === 'router') {
    for (const choice of node.choices ?? []) {
      for (const child of choice.steps) children.push({ branch: choice.name, child })
    }
  } else {
    for (const child of node.steps ?? []) children.push({ branch: 'steps', child })
  }

  return (
    <>
      <button
        type="button"
        className={`step-row ${node.id === selectedId ? 'selected' : ''}`}
        style={{ paddingLeft: 12 + depth * 16 }}
        onClick={() => onSelect(node.id)}
      >
        <span>{index + 1}</span>
        <div>
          <strong>{nodeLabel(node)}</strong>
          <small>
            {node.type === 'step'
              ? node.targetId || 'agent'
              : node.type === 'condition'
                ? node.evaluatorCel || 'cel'
                : node.type === 'loop'
                  ? `max ${node.maxIterations ?? 3}`
                  : node.type === 'router'
                    ? node.selectorCel || 'selector'
                    : node.type === 'workflow_ref'
                      ? node.workflowId || 'ref'
                      : `${node.steps?.length ?? 0} branches`}
          </small>
        </div>
        <Tag color={typeColor[node.type]}>{node.type}</Tag>
      </button>
      {children.map(({ branch, child }, childIndex) => (
        <div key={child.id}>
          {node.type === 'condition' || node.type === 'router' ? (
            <Typography.Text
              type="secondary"
              style={{ display: 'block', paddingLeft: 28 + depth * 16, fontSize: 12 }}
            >
              {branch}
            </Typography.Text>
          ) : null}
          <NodeRow
            node={child}
            index={childIndex}
            depth={depth + 1}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        </div>
      ))}
    </>
  )
}

export function WorkflowPage() {
  const { t } = useTranslation('workflow')
  const router = useRouter()
  const workflow = useWorkflow()
  const step = workflow.selected
  const executors = workflow.executorsQuery.data ?? []
  const models = workflow.modelsQuery.data?.models ?? []
  const saved = workflow.workflowsQuery.data ?? []
  const versions = workflow.versionsQuery.data ?? []

  const addMenuItems = [
    { key: 'step', label: t('addStep') },
    { key: 'parallel', label: t('addParallel') },
    { key: 'condition', label: t('addCondition') },
    { key: 'loop', label: t('addLoop') },
    { key: 'router', label: t('addRouter') },
    { key: 'workflow_ref', label: t('addWorkflowRef') },
  ]

  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Space wrap>
            <Dropdown
              menu={{
                items: addMenuItems,
                onClick: ({ key }) => workflow.add(key as WorkflowNodeType),
              }}
            >
              <Button icon={<PlusOutlined />}>{t('addNode')}</Button>
            </Dropdown>
            <Button
              icon={<SaveOutlined />}
              type="primary"
              loading={workflow.state.saving}
              onClick={() => void workflow.save()}
            >
              {t('save')}
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
            <Button onClick={workflow.reset}>{t('new')}</Button>
          </Space>
        }
      />

      {workflow.state.error ? (
        <Alert type="error" showIcon style={{ marginBottom: 12 }} message={workflow.state.error} />
      ) : null}

      <div className="workflow-layout">
        <Card className="workbench-card" title={t('library')}>
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
              style={{ paddingInline: 0, marginTop: 8 }}
              onClick={() => void workflow.removeSaved()}
            >
              {t('deleteSaved')}
            </Button>
          ) : null}
          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            {t('pr4Hint')}
          </Typography.Paragraph>
          {versions.length ? (
            <div style={{ marginTop: 12 }}>
              <Typography.Text type="secondary">{t('versions')}</Typography.Text>
              <Select
                style={{ width: '100%', marginTop: 4 }}
                placeholder={t('restoreVersion')}
                options={versions.map((item) => ({
                  value: item.version,
                  label: `v${item.version} · ${new Date(item.created_at * 1000).toLocaleString()}`,
                }))}
                onChange={(version) => void workflow.restoreVersion(Number(version))}
              />
            </div>
          ) : null}
        </Card>

        <Card className="workbench-card" title={t('definition')}>
          <Input
            value={workflow.state.name}
            onChange={(e) => workflow.patch({ name: e.target.value })}
            placeholder={t('namePlaceholder')}
          />
          <Input.TextArea
            value={workflow.state.description}
            onChange={(e) => workflow.patch({ description: e.target.value })}
            placeholder={t('descriptionPlaceholder')}
            rows={3}
            style={{ marginTop: 8 }}
          />
          <Input.TextArea
            value={workflow.state.input}
            onChange={(e) =>
              workflow.patchMeta({ input: e.target.value, dirty: workflow.state.dirty })
            }
            placeholder={t('inputPlaceholder')}
            rows={4}
            style={{ marginTop: 8 }}
          />
          <Select
            style={{ width: '100%', marginTop: 8 }}
            placeholder={t('modelPlaceholder')}
            value={workflow.state.modelId ?? undefined}
            options={models
              .filter((model) => model.enabled)
              .map((model) => ({ value: model.id, label: model.name || model.model_id }))}
            onChange={(value) =>
              workflow.patchMeta({ modelId: value, dirty: workflow.state.dirty })
            }
          />
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
            {t('triggers')}
          </Typography.Text>
          <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
            <Space>
              <Switch
                checked={workflow.state.triggers.webhook.enabled}
                onChange={(enabled) =>
                  workflow.patchTriggers({
                    ...workflow.state.triggers,
                    webhook: { ...workflow.state.triggers.webhook, enabled },
                  })
                }
              />
              <span>{t('webhookTrigger')}</span>
            </Space>
            {workflow.state.triggers.webhook.enabled ? (
              <Input
                value={workflow.state.triggers.webhook.secret}
                onChange={(e) =>
                  workflow.patchTriggers({
                    ...workflow.state.triggers,
                    webhook: { ...workflow.state.triggers.webhook, secret: e.target.value },
                  })
                }
                placeholder={t('webhookSecret')}
              />
            ) : null}
            {workflow.state.workflowId && workflow.state.triggers.webhook.enabled ? (
              <Typography.Text code copyable>
                {`POST /api/workflows/${workflow.state.workflowId}/hooks/webhook?secret=...`}
              </Typography.Text>
            ) : null}
            <Space>
              <Switch
                checked={workflow.state.triggers.cron.enabled}
                onChange={(enabled) =>
                  workflow.patchTriggers({
                    ...workflow.state.triggers,
                    cron: { ...workflow.state.triggers.cron, enabled },
                  })
                }
              />
              <span>{t('cronTrigger')}</span>
            </Space>
            {workflow.state.triggers.cron.enabled ? (
              <Input
                value={workflow.state.triggers.cron.expression}
                onChange={(e) =>
                  workflow.patchTriggers({
                    ...workflow.state.triggers,
                    cron: { ...workflow.state.triggers.cron, expression: e.target.value },
                  })
                }
                placeholder="0 * * * *"
              />
            ) : null}
          </Space>
        </Card>

        <Card className="workbench-card workflow-canvas-card" title={t('canvas')}>
          <WorkflowCanvas
            steps={workflow.state.steps}
            selectedId={workflow.state.selectedId}
            onSelect={(id) =>
              workflow.patchMeta({ selectedId: id, dirty: workflow.state.dirty })
            }
            onPositionsChange={workflow.applyPositions}
            onConnectSequence={workflow.connectSequence}
          />
        </Card>

        <Card className="workbench-card" title={`${t('steps')} (${workflow.state.steps.length})`}>
          {workflow.state.steps.length ? (
            <div className="step-list">
              {workflow.state.steps.map((item, index) => (
                <NodeRow
                  key={item.id}
                  node={item}
                  index={index}
                  depth={0}
                  selectedId={workflow.state.selectedId}
                  onSelect={(id) =>
                    workflow.patchMeta({ selectedId: id, dirty: workflow.state.dirty })
                  }
                />
              ))}
            </div>
          ) : (
            <Empty description={t('emptySteps')} />
          )}
        </Card>

        <Card
          className="workbench-card"
          title={t('inspector')}
          extra={
            step ? (
              <Space>
                {workflow.state.steps.some((item) => item.id === step.id) ? (
                  <>
                    <Button
                      size="small"
                      icon={<ArrowUpOutlined />}
                      onClick={() => workflow.move(step.id, -1)}
                    />
                    <Button
                      size="small"
                      icon={<ArrowDownOutlined />}
                      onClick={() => workflow.move(step.id, 1)}
                    />
                  </>
                ) : null}
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => workflow.remove(step.id)}
                />
              </Space>
            ) : null
          }
        >
          {step ? (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Tag color={typeColor[step.type]}>{step.type}</Tag>
              <Input
                value={step.name}
                onChange={(e) => workflow.update({ ...step, name: e.target.value })}
                placeholder={t('stepNamePlaceholder')}
              />

              {step.type === 'step' ? (
                <>
                  <Select
                    style={{ width: '100%' }}
                    placeholder={t('executorPlaceholder')}
                    value={step.targetId}
                    options={executors.map((item) => ({
                      value: item.ref,
                      label: `${item.name} (${item.ref})`,
                    }))}
                    onChange={(value) => workflow.update({ ...step, targetId: value })}
                  />
                  <Input.TextArea
                    value={step.instructions}
                    onChange={(e) => workflow.update({ ...step, instructions: e.target.value })}
                    placeholder={t('instructionsPlaceholder')}
                    rows={4}
                  />
                  <Space>
                    <Switch
                      checked={Boolean(step.requiresConfirmation)}
                      onChange={(checked) =>
                        workflow.update({ ...step, requiresConfirmation: checked })
                      }
                    />
                    <Typography.Text>{t('requiresConfirmation')}</Typography.Text>
                  </Space>
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
                  <Space>
                    <Switch
                      checked={Boolean(step.requiresUserInput)}
                      onChange={(checked) =>
                        workflow.update({ ...step, requiresUserInput: checked })
                      }
                    />
                    <Typography.Text>{t('requiresUserInput')}</Typography.Text>
                  </Space>
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
                  <Space>
                    <Switch
                      checked={Boolean(step.requiresOutputReview)}
                      onChange={(checked) =>
                        workflow.update({ ...step, requiresOutputReview: checked })
                      }
                    />
                    <Typography.Text>{t('requiresOutputReview')}</Typography.Text>
                  </Space>
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
                    onChange={(e) => workflow.update({ ...step, evaluatorCel: e.target.value })}
                    rows={3}
                  />
                  <Space wrap>
                    <Button size="small" onClick={() => workflow.addChild(step.id, 'thenSteps', 'step')}>
                      {t('addThenStep')}
                    </Button>
                    <Button size="small" onClick={() => workflow.addChild(step.id, 'elseSteps', 'step')}>
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
                    style={{ width: '100%' }}
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
                  />
                  <Button size="small" onClick={() => workflow.addChild(step.id, 'steps', 'step')}>
                    {t('addLoopStep')}
                  </Button>
                </>
              ) : null}

              {step.type === 'parallel' ? (
                <Button size="small" onClick={() => workflow.addChild(step.id, 'steps', 'step')}>
                  {t('addParallelBranch')}
                </Button>
              ) : null}

              {step.type === 'router' ? (
                <>
                  <Typography.Text type="secondary">{t('selectorCel')}</Typography.Text>
                  <Input.TextArea
                    value={step.selectorCel}
                    onChange={(e) => workflow.update({ ...step, selectorCel: e.target.value })}
                    rows={3}
                  />
                  <Typography.Text type="secondary">{t('routerChoicesHint')}</Typography.Text>
                </>
              ) : null}

              {step.type === 'workflow_ref' ? (
                <Select
                  style={{ width: '100%' }}
                  placeholder={t('nestedWorkflowPlaceholder')}
                  value={step.workflowId || undefined}
                  options={saved
                    .filter((item) => item.id !== workflow.state.workflowId)
                    .map((item) => ({ value: item.id, label: item.name }))}
                  onChange={(value) => workflow.update({ ...step, workflowId: value })}
                />
              ) : null}
            </Space>
          ) : (
            <Empty description={t('selectStep')} />
          )}
        </Card>

        <Card
          className="workbench-card"
          title={t('runLog')}
          extra={
            workflow.state.lastSessionId ? (
              <Button
                type="link"
                onClick={() =>
                  void router.navigate({
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
            ) : null
          }
        >
          {workflow.state.runLog.length ? (
            <List
              size="small"
              dataSource={[...workflow.state.runLog].reverse()}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <Tag>{item.type}</Tag>
                        {item.stepName ? <span>{item.stepName}</span> : null}
                      </Space>
                    }
                    description={item.content || item.message}
                  />
                </List.Item>
              )}
            />
          ) : (
            <Empty description={t('emptyRunLog')} />
          )}
        </Card>

        <Card className="workbench-card" title={t('generatedCode')}>
          <PayloadViewer value={buildWorkflowCode(workflow.state)} />
        </Card>
      </div>
    </main>
  )
}
