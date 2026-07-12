import { Button, Card, Empty, Input, Select, Space, Tag } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import { useWorkflow } from './useWorkflow'
import { buildWorkflowCode } from './utils'

export function WorkflowPage() {
  const workflow = useWorkflow()
  const step = workflow.selected
  return (
    <main className="page">
      <PageHeader
        title="Workflow Builder"
        description="组合 Agent、Team 和 Workflow 步骤并生成 Agno 执行代码"
        actions={
          <Space.Compact>
            <Button icon={<PlusOutlined />} onClick={() => workflow.add('agent')}>
              Agent
            </Button>
            <Button onClick={() => workflow.add('team')}>Team</Button>
            <Button onClick={() => workflow.add('workflow')}>Workflow</Button>
          </Space.Compact>
        }
      />
      <div className="workflow-layout">
        <Card className="workbench-card" title="Definition">
          <Input value={workflow.state.name} onChange={(e) => workflow.patch({ name: e.target.value })} placeholder="Workflow name" />
          <Input.TextArea
            value={workflow.state.description}
            onChange={(e) => workflow.patch({ description: e.target.value })}
            placeholder="Description"
            rows={3}
            style={{ marginTop: 8 }}
          />
          <Input.TextArea
            value={workflow.state.input}
            onChange={(e) => workflow.patch({ input: e.target.value })}
            placeholder="Run input"
            rows={5}
            style={{ marginTop: 8 }}
          />
        </Card>
        <Card className="workbench-card" title={`Steps (${workflow.state.steps.length})`}>
          {workflow.state.steps.length ? (
            <div className="step-list">
              {workflow.state.steps.map((item, index) => (
                <button
                  type="button"
                  key={item.id}
                  className={`step-row ${item.id === workflow.state.selectedId ? 'selected' : ''}`}
                  onClick={() => workflow.patch({ selectedId: item.id })}
                >
                  <span>{index + 1}</span>
                  <div>
                    <strong>{item.name || item.targetId || 'Unconfigured step'}</strong>
                    <small>{item.kind}</small>
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
            <Empty description="Add the first workflow step" />
          )}
        </Card>
        <Card className="workbench-card" title="Inspector">
          {step ? (
            <Space orientation="vertical" style={{ width: '100%' }}>
              <Select
                value={step.kind}
                onChange={(kind) => workflow.update({ ...step, kind })}
                options={['agent', 'team', 'workflow'].map((value) => ({ value }))}
              />
              <Input value={step.name} onChange={(e) => workflow.update({ ...step, name: e.target.value })} placeholder="Display name" />
              <Input
                value={step.targetId}
                onChange={(e) => workflow.update({ ...step, targetId: e.target.value })}
                placeholder="Executor ID"
              />
              <Input.TextArea
                value={step.instructions}
                onChange={(e) => workflow.update({ ...step, instructions: e.target.value })}
                rows={7}
                placeholder="Instructions"
              />
            </Space>
          ) : (
            <Empty description="Select a step" />
          )}
        </Card>
      </div>
      <Card className="workbench-card" title="Generated Agno code" style={{ marginTop: 12 }}>
        <PayloadViewer value={buildWorkflowCode(workflow.state)} />
      </Card>
    </main>
  )
}
