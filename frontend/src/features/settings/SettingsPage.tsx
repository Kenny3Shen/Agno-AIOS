import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Form, Input, Modal, Radio, Select, Space, Switch, Table, Tag, message } from 'antd'
import { ApiOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { getModels, saveModels, testModel } from './api'
import type { ModelConfig } from '@/shared/types/common'

const providerOptions = [
  { value: 'deepseek', label: 'DeepSeek (native)' },
  { value: 'openai', label: 'OpenAI (native)' },
  { value: 'openai-compatible', label: 'OpenAI-compatible' },
]
const protocolOptions = [
  { value: 'chat-completions', label: 'Chat Completions' },
  { value: 'responses', label: 'Responses' },
]
const outputModeOptions = [
  { value: 'native', label: 'Native schema' },
  { value: 'json', label: 'JSON mode' },
  { value: 'none', label: 'No response format' },
]

export function SettingsPage() {
  const client = useQueryClient()
  const models = useQuery({ queryKey: ['settings', 'models'], queryFn: getModels })
  const [editing, setEditing] = useState<ModelConfig | null>(null)
  const saveModel = async (model: ModelConfig) => {
    const current = models.data ?? { active_model_id: model.id, models: [] }
    const next = current.models.some((item) => item.id === model.id)
      ? current.models.map((item) => item.id === model.id ? model : item)
      : [...current.models, model]
    await saveModels({ ...current, models: next })
    setEditing(null)
    await client.invalidateQueries({ queryKey: ['settings', 'models'] })
  }
  const addModel = () => setEditing({
    id: crypto.randomUUID(),
    name: '',
    model_id: '',
    provider: 'openai-compatible',
    api_protocol: 'chat-completions',
    structured_output_mode: 'none',
    base_url: '',
    api_key: '',
    description: '',
    enabled: true,
    builtin: false,
  })

  return <main className="page">
    <PageHeader title="Settings" description="配置模型连接" />
    <Card className="workbench-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={addModel}>添加模型</Button>}>
      <Table<ModelConfig>
        rowKey="id"
        dataSource={models.data?.models ?? []}
        loading={models.isLoading}
        columns={[
          { title: 'Name', dataIndex: 'name', render: (value, row) => <Space><strong>{value}</strong>{models.data?.active_model_id === row.id && <Tag color="blue">active</Tag>}</Space> },
          { title: 'Model', dataIndex: 'model_id' },
          { title: 'Provider', dataIndex: 'provider', render: (value, row) => <Space><Tag>{value}</Tag><Tag color="blue">{row.api_protocol}</Tag></Space> },
          { title: 'Output', dataIndex: 'structured_output_mode', render: (value) => <Tag>{value}</Tag> },
          { title: 'Base URL', dataIndex: 'base_url', ellipsis: true },
          { title: 'Configured', dataIndex: 'configured', render: (value) => <Tag color={value ? 'success' : 'warning'}>{value ? 'ready' : 'missing key'}</Tag> },
          { title: 'Enabled', dataIndex: 'enabled', render: (value) => <Switch checked={value} disabled /> },
          { title: 'Actions', render: (_, row) => <Space><Button icon={<ApiOutlined />} onClick={async () => { const result = await testModel(row); result.success ? message.success(`${result.latency_ms ?? '-'} ms`) : message.error(result.message) }} /><Button icon={<EditOutlined />} onClick={() => setEditing(row)} /></Space> },
        ]}
      />
    </Card>
    <Modal open={Boolean(editing)} footer={null} onCancel={() => setEditing(null)} title="Model configuration" destroyOnHidden>
      {editing && <Form layout="vertical" initialValues={editing} onFinish={saveModel}>
        <Form.Item name="id" hidden><Input /></Form.Item>
        <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="provider" label="Provider" rules={[{ required: true }]}><Select options={providerOptions} /></Form.Item>
        <Form.Item name="api_protocol" label="API protocol" rules={[{ required: true }]}><Select options={protocolOptions} /></Form.Item>
        <Form.Item name="structured_output_mode" label="Structured output" rules={[{ required: true }]}><Select options={outputModeOptions} /></Form.Item>
        <Form.Item name="model_id" label="Model ID" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="base_url" label="Base URL"><Input /></Form.Item>
        <Form.Item name="api_key" label="API key"><Input.Password /></Form.Item>
        <Form.Item name="description" label="Description"><Input /></Form.Item>
        <Form.Item name="enabled" label="Enabled" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name="builtin" hidden><Radio /></Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form>}
    </Modal>
  </main>
}
