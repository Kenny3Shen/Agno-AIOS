import { Button, Card, Empty, Input, Select, Space, Tag, Typography, Alert, List } from 'antd'
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
import { buildWorkflowCode } from './utils'
import { useTranslation } from 'react-i18next'
import { useRouter } from '@tanstack/react-router'

export function WorkflowPage() {
  const { t } = useTranslation('workflow')
  const router = useRouter()
  const workflow = useWorkflow()
  const step = workflow.selected
  const executors = workflow.executorsQuery.data ?? []
  const models = workflow.modelsQuery.data?.models ?? []
  const saved = workflow.workflowsQuery.data ?? []

  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Space wrap>
            <Button icon={<PlusOutlined />} onClick={() => workflow.add('agent')}>
              {t('addStep')}
            </Button>
            <Button icon={<SaveOutlined />} type="primary" loading={workflow.state.saving} onClick={() => void workflow.save()}>
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

      {workflow.state.error ? <Alert type="error" showIcon style={{ marginBottom: 12 }} message={workflow.state.error} /> : null}

      <div className="workflow-layout">
        <Card className="workbench-card" title={t('library')}>
          <Select
            style={{ width: '100%' }}
            placeholder={t('loadPlaceholder')}
            value={workflow.state.workflowId ?? undefined}
            allowClear
            options={saved.map((item) => ({ value: item.id, label: `${item.name} (v${item.version})` }))}
            onChange={(value) => {
              if (value) workflow.load(value)
              else workflow.reset()
            }}
          />
          {workflow.state.workflowId ? (
            <Button danger type="link" style={{ paddingInline: 0, marginTop: 8 }} onClick={() => void workflow.removeSaved()}>
              {t('deleteSaved')}
            </Button>
          ) : null}
          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            {t('pr1Hint')}
          </Typography.Paragraph>
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
            onChange={(e) => workflow.patchMeta({ input: e.target.value, dirty: workflow.state.dirty })}
            placeholder={t('inputPlaceholder')}
            rows={5}
            style={{ marginTop: 8 }}
          />
          <Select
            style={{ width: '100%', marginTop: 8 }}
            placeholder={t('modelPlaceholder')}
            value={workflow.state.modelId ?? undefined}
            options={models
              .filter((model) => model.enabled)
              .map((model) => ({ value: model.id, label: model.name || model.model_id }))}
            onChange={(value) => workflow.patchMeta({ modelId: value, dirty: workflow.state.dirty })}
          />
        </Card>

        <Card className="workbench-card" title={`${t('steps')} (${workflow.state.steps.length})`}>
          {workflow.state.steps.length ? (
            <div className="step-list">
              {workflow.state.steps.map((item, index) => (
                <button
                  type="button"
                  key={item.id}
                  className={`step-row ${item.id === workflow.state.selectedId ? 'selected' : ''}`}
                  onClick={() => workflow.patchMeta({ selectedId: item.id, dirty: workflow.state.dirty })}
                >
                  <span>{index + 1}</span>
                  <div>
                    <strong>{item.name || item.targetId || t('unconfigured')}</strong>
                    <small>{item.targetId || 'agent'}</small>
                  </div>
                  <Tag>{item.kind}</Tag>
                  <Space>
                    <Button
                      type="text"
                      icon={<ArrowUpOutlined />}
                      disabled={index === 0}
                      onClick={(e) => {
                        e.stopPropagation()
                        workflow.move(item.id, -1)
                      }}
                    />
                    <Button
                      type="text"
                      icon={<ArrowDownOutlined />}
                      disabled={index === workflow.state.steps.length - 1}
                      onClick={(e) => {
                        e.stopPropagation()
                        workflow.move(item.id, 1)
                      }}
                    />
                    <Button
                      danger
                      type="text"
                      icon={<DeleteOutlined />}
                      onClick={(e) => {
                        e.stopPropagation()
                        workflow.remove(item.id)
                      }}
                    />
                  </Space>
                </button>
              ))}
            </div>
          ) : (
            <Empty description={t('emptySteps')} />
          )}
        </Card>

        <Card className="workbench-card" title={t('inspector')}>
          {step ? (
            <Space orientation="vertical" style={{ width: '100%' }}>
              <Select
                value={step.targetId || undefined}
                placeholder={t('executorPlaceholder')}
                options={executors.map((item) => ({
                  value: item.ref,
                  label: `${item.name} (${item.ref})`,
                }))}
                onChange={(ref) => workflow.update({ ...step, targetId: ref, name: step.name || ref })}
                style={{ width: '100%' }}
              />
              <Input
                value={step.name}
                onChange={(e) => workflow.update({ ...step, name: e.target.value })}
                placeholder={t('stepNamePlaceholder')}
              />
              <Input.TextArea
                value={step.instructions}
                onChange={(e) => workflow.update({ ...step, instructions: e.target.value })}
                rows={7}
                placeholder={t('instructionsPlaceholder')}
              />
            </Space>
          ) : (
            <Empty description={t('selectStep')} />
          )}
        </Card>
      </div>

      <Card className="workbench-card" title={t('runLog')} style={{ marginTop: 12 }}>
        {workflow.state.runLog.length ? (
          <List
            size="small"
            dataSource={[...workflow.state.runLog].reverse()}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Space>
                    <Tag color={item.type.includes('error') || item.type.includes('failed') ? 'error' : 'processing'}>
                      {item.type}
                    </Tag>
                    {item.stepName ? <Typography.Text strong>{item.stepName}</Typography.Text> : null}
                  </Space>
                  <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 3, expandable: true }}>
                    {item.content || item.message}
                  </Typography.Paragraph>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Empty description={t('emptyRunLog')} />
        )}
        {workflow.state.lastSessionId ? (
          <Button
            type="link"
            style={{ paddingInline: 0 }}
            onClick={() =>
              void router.history.push(
                `/trace?session_id=${encodeURIComponent(workflow.state.lastSessionId ?? '')}&selected_session=${encodeURIComponent(workflow.state.lastSessionId ?? '')}`
              )
            }
          >
            {t('openTrace')}
          </Button>
        ) : null}
      </Card>

      <Card className="workbench-card" title={t('generatedCode')} style={{ marginTop: 12 }}>
        <PayloadViewer value={buildWorkflowCode(workflow.state)} />
      </Card>
    </main>
  )
}
