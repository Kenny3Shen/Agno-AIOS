import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Collapse, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import { ApiOutlined, CheckCircleOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import { DEEPSEEK_REASONING_EFFORTS, openaiReasoningEfforts, reasoningEffortLabel } from '@/shared/lib/reasoning'
import { getChatSettings, getModels, saveChatSettings, saveModels, testModel, type ChatSettings } from './api'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'
import { useTranslation } from 'react-i18next'

const providerDefaults = (provider: ModelConfig['provider']) => {
  if (provider === 'deepseek')
    return { api_protocol: 'chat-completions' as const, structured_output_mode: 'json' as const, default_reasoning_effort: 'max' as const }
  if (provider === 'openai')
    return { api_protocol: 'responses' as const, structured_output_mode: 'native' as const, default_reasoning_effort: 'high' as const }
  return { api_protocol: 'chat-completions' as const, structured_output_mode: 'json' as const, default_reasoning_effort: null }
}

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
]

const parallelToolCallsOptions = [
  { value: true, label: 'Enabled' },
  { value: false, label: 'Disabled' },
]

const reasoningOptions = (provider: ModelConfig['provider'], protocol: ModelConfig['api_protocol']) => {
  if (provider === 'deepseek') return DEEPSEEK_REASONING_EFFORTS.map((value) => ({ value, label: reasoningEffortLabel(value) }))
  if (provider === 'openai') return openaiReasoningEfforts(protocol).map((value) => ({ value, label: reasoningEffortLabel(value) }))
  return []
}

export function SettingsPage() {
  const { t } = useTranslation('settings')
  const { message } = App.useApp()
  const client = useQueryClient()
  const models = useQuery({ queryKey: ['settings', 'models'], queryFn: getModels })
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const chatSettings = useQuery({ queryKey: ['settings', 'chat'], queryFn: getChatSettings, enabled: isAdmin })
  const [editing, setEditing] = useState<ModelConfig | null>(null)
  const [form] = Form.useForm<ModelConfig>()
  const [saving, setSaving] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('models')

  const setChatSetting = async (key: keyof ChatSettings, value: boolean) => {
    try {
      await saveChatSettings({ [key]: value })
      await client.invalidateQueries({ queryKey: ['settings', 'chat'] })
      message.success(t('chatUpdated'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('chatUpdateFailed'))
    }
  }

  const openEditor = (model: ModelConfig) => {
    form.resetFields()
    form.setFieldsValue({
      retries: 3,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
      ...model,
    })
    setEditing(model)
  }

  const closeEditor = () => {
    setEditing(null)
    form.resetFields()
  }

  const persist = async (next: ModelConfigResponse) => {
    await saveModels(next)
    await client.invalidateQueries({ queryKey: ['settings', 'models'] })
  }

  const saveModel = async (model: ModelConfig) => {
    const normalized = { ...model, name: model.name.trim(), model_id: model.model_id.trim(), base_url: model.base_url.trim() }
    const current = models.data ?? { active_model_id: normalized.id, models: [] }
    const next = current.models.some((item) => item.id === normalized.id)
      ? current.models.map((item) => (item.id === normalized.id ? normalized : item))
      : [...current.models, normalized]
    setSaving(true)
    try {
      await persist({ ...current, models: next })
      message.success(t('modelSaved'))
      closeEditor()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('modelSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const addModel = () =>
    openEditor({
      id: crypto.randomUUID(),
      name: '',
      model_id: '',
      provider: 'openai-compatible',
      api_protocol: 'chat-completions',
      structured_output_mode: 'json',
      default_reasoning_effort: null,
      parallel_tool_calls: null,
      retries: 3,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
      base_url: '',
      api_key: '',
      description: '',
      enabled: true,
      builtin: false,
    })

  const setActiveModel = async (model: ModelConfig) => {
    const current = models.data
    if (!current || current.active_model_id === model.id) return
    setUpdatingId(model.id)
    try {
      await persist({ ...current, active_model_id: model.id })
      message.success(t('modelActivated', { name: model.name }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('modelActivateFailed'))
    } finally {
      setUpdatingId(null)
    }
  }

  const setEnabled = async (model: ModelConfig, enabled: boolean) => {
    const current = models.data
    if (!current) return
    setUpdatingId(model.id)
    try {
      await persist({ ...current, models: current.models.map((item) => (item.id === model.id ? { ...item, enabled } : item)) })
      message.success(enabled ? t('modelEnabled', { name: model.name }) : t('modelDisabled', { name: model.name }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('modelStatusFailed'))
    } finally {
      setUpdatingId(null)
    }
  }

  const runConnectivityTest = async (model: ModelConfig) => {
    setTestingId(model.id)
    try {
      const result = await testModel(model)
      if (result.success) {
        message.success(t('connectOk', { latency: result.latency_ms ?? '-' }))
      } else {
        message.error(result.message)
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('connectFailed'))
    } finally {
      setTestingId(null)
    }
  }

  const modelConnections = (
    <Table<ModelConfig>
      rowKey="id"
      dataSource={models.data?.models ?? []}
      loading={models.isLoading}
      scroll={{ x: 1240 }}
      columns={[
        {
          title: 'Name',
          dataIndex: 'name',
          width: 220,
          ellipsis: true,
          render: (value, row) => (
            <Space>
              <strong>{value}</strong>
              {models.data?.active_model_id === row.id && <Tag color="blue">active</Tag>}
            </Space>
          ),
        },
        { title: 'Model ID', dataIndex: 'model_id', width: 190, ellipsis: true },
        {
          title: 'Runtime',
          dataIndex: 'provider',
          width: 230,
          render: (value, row) => (
            <Space orientation="vertical" size={2}>
              <Space size={[4, 4]} wrap>
                <Tag>{value}</Tag>
                <Tag color="blue">{row.api_protocol}</Tag>
              </Space>
              <Tag color={row.structured_output_mode === 'json' ? 'green' : 'purple'}>{row.structured_output_mode}</Tag>
            </Space>
          ),
        },
        {
          title: 'Base URL',
          dataIndex: 'base_url',
          width: 260,
          ellipsis: { showTitle: false },
          render: (value) => <Typography.Text ellipsis={{ tooltip: value }}>{value || '-'}</Typography.Text>,
        },
        {
          title: 'Configured',
          dataIndex: 'configured',
          width: 130,
          render: (value) => <Tag color={value ? 'success' : 'warning'}>{value ? 'ready' : 'missing key'}</Tag>,
        },
        {
          title: 'Enabled',
          dataIndex: 'enabled',
          width: 110,
          render: (value, row) => (
            <Switch
              checked={value}
              loading={updatingId === row.id}
              onChange={(checked) => void setEnabled(row, checked)}
              aria-label={`${row.name} enabled`}
            />
          ),
        },
        {
          title: 'Actions',
          width: 170,
          render: (_, row) => (
            <Space>
              <Tooltip title={t('testConnection')}>
                <Button
                  icon={<ApiOutlined />}
                  loading={testingId === row.id}
                  aria-label={t('testConnectionNamed', { name: row.name })}
                  onClick={() => void runConnectivityTest(row)}
                />
              </Tooltip>
              <Tooltip title={t('editModel')}>
                <Button icon={<EditOutlined />} aria-label={t('editModelNamed', { name: row.name })} onClick={() => openEditor(row)} />
              </Tooltip>
              <Tooltip title={models.data?.active_model_id === row.id ? t('currentModel') : t('setCurrentModel')}>
                <Button
                  icon={<CheckCircleOutlined />}
                  disabled={models.data?.active_model_id === row.id}
                  loading={updatingId === row.id}
                  aria-label={t('setCurrentModelNamed', { name: row.name })}
                  onClick={() => void setActiveModel(row)}
                />
              </Tooltip>
            </Space>
          ),
        },
      ]}
    />
  )

  const chatControls = (
    <div>
      <Table<ChatSettings>
        rowKey={(row) => Object.keys(row).join(':')}
        loading={chatSettings.isLoading}
        pagination={false}
        dataSource={chatSettings.data ? [chatSettings.data] : []}
        columns={[
          {
            title: t('securityTimeline'),
            dataIndex: 'show_thought_chain',
            render: (value) => <Switch checked={value} onChange={(next) => void setChatSetting('show_thought_chain', next)} />,
          },
          {
            title: t('rawReasoning'),
            dataIndex: 'show_raw_reasoning',
            render: (value) => <Switch checked={value} onChange={(next) => void setChatSetting('show_raw_reasoning', next)} />,
          },
          {
            title: t('rawToolIo'),
            dataIndex: 'show_raw_tool_io',
            render: (value) => <Switch checked={value} onChange={(next) => void setChatSetting('show_raw_tool_io', next)} />,
          },
          {
            title: t('longTermMemory'),
            dataIndex: 'memory_enabled',
            render: (value) => <Switch checked={value} onChange={(next) => void setChatSetting('memory_enabled', next)} />,
          },
        ]}
      />
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 12 }}>
        {t('privacyNote')}
      </Typography.Paragraph>
    </div>
  )

  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          destroyOnHidden
          tabBarExtraContent={
            activeTab === 'models' ? (
              <Button type="primary" icon={<PlusOutlined />} onClick={addModel}>
                {t('addModel')}
              </Button>
            ) : null
          }
          items={[
            { key: 'models', label: t('modelConnections'), children: modelConnections },
            ...(isAdmin ? [{ key: 'chat', label: t('chatSettings'), children: chatControls }] : []),
          ]}
        />
      </Card>
      <Modal
        width={560}
        open={Boolean(editing)}
        onCancel={closeEditor}
        onOk={() => form.submit()}
        okText={t('saveModel')}
        cancelText={t('common:cancel')}
        confirmLoading={saving}
        title={t('modelConnections')}
        destroyOnHidden
      >
        {editing && (
          <Form form={form} layout="vertical" onFinish={saveModel}>
            <Form.Item name="id" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="name" label="Name" rules={[{ required: true, whitespace: true, message: t('nameRequired') }]}>
              <Input placeholder={t('namePlaceholder')} />
            </Form.Item>
            <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
              <Select
                options={providerOptions}
                onChange={(provider: ModelConfig['provider']) => form.setFieldsValue(providerDefaults(provider))}
              />
            </Form.Item>
            <Form.Item name="model_id" label="Model ID" rules={[{ required: true, whitespace: true, message: t('modelIdRequired') }]}>
              <Input placeholder={t('modelIdPlaceholder')} />
            </Form.Item>
            <Form.Item name="api_key" label="API key" rules={[{ required: true, whitespace: true, message: t('apiKeyRequired') }]}>
              <Input.Password placeholder="sk-..." />
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(previous, current) => previous.provider !== current.provider}>
              {({ getFieldValue }) => {
                const baseUrlRequired = getFieldValue('provider') === 'openai-compatible'
                return (
                  <Form.Item
                    name="base_url"
                    label="Base URL"
                    rules={[
                      { required: baseUrlRequired, whitespace: true, message: t('baseUrlRequired') },
                      { type: 'url', message: t('urlInvalid') },
                    ]}
                  >
                    <Input placeholder="https://api.example.com/v1" />
                  </Form.Item>
                )
              }}
            </Form.Item>
            <Collapse
              ghost
              size="small"
              items={[
                {
                  key: 'advanced',
                  label: 'Advanced',
                  forceRender: true,
                  children: (
                    <>
                      <Form.Item noStyle shouldUpdate={(previous, current) => previous.provider !== current.provider}>
                        {({ getFieldValue }) => (
                          <Form.Item name="api_protocol" label="API protocol" rules={[{ required: true }]}>
                            <Select
                              options={protocolOptions}
                              disabled={getFieldValue('provider') === 'deepseek'}
                              onChange={(protocol: ModelConfig['api_protocol']) => {
                                if (
                                  getFieldValue('provider') === 'openai' &&
                                  protocol === 'chat-completions' &&
                                  getFieldValue('default_reasoning_effort') === 'minimal'
                                )
                                  form.setFieldValue('default_reasoning_effort', 'high')
                              }}
                            />
                          </Form.Item>
                        )}
                      </Form.Item>
                      <Form.Item noStyle shouldUpdate={(previous, current) => previous.provider !== current.provider}>
                        {({ getFieldValue }) => (
                          <Form.Item name="structured_output_mode" label="Structured output" rules={[{ required: true }]}>
                            <Select options={outputModeOptions} disabled={getFieldValue('provider') === 'deepseek'} />
                          </Form.Item>
                        )}
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(previous, current) =>
                          previous.provider !== current.provider || previous.api_protocol !== current.api_protocol
                        }
                      >
                        {({ getFieldValue }) => {
                          const provider = getFieldValue('provider') as ModelConfig['provider']
                          const protocol = getFieldValue('api_protocol') as ModelConfig['api_protocol']
                          if (provider === 'openai-compatible') return null
                          return (
                            <Form.Item name="default_reasoning_effort" label="Default reasoning effort" rules={[{ required: true }]}>
                              <Select options={reasoningOptions(provider, protocol)} />
                            </Form.Item>
                          )
                        }}
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(previous, current) =>
                          previous.provider !== current.provider || previous.api_protocol !== current.api_protocol
                        }
                      >
                        {({ getFieldValue }) => {
                          if (getFieldValue('provider') === 'deepseek') return null
                          return (
                            <Form.Item
                              name="parallel_tool_calls"
                              label={t('parallelToolCalls')}
                              extra={t('parallelToolCallsHelp')}
                            >
                              <Select
                                allowClear
                                placeholder={t('providerDefault')}
                                options={parallelToolCallsOptions}
                              />
                            </Form.Item>
                          )
                        }}
                      </Form.Item>
                      <Form.Item name="retries" label={t('retries')} extra={t('retriesHelp')}>
                        <InputNumber min={0} max={10} style={{ width: '100%' }} />
                      </Form.Item>
                      <Form.Item
                        name="delay_between_retries"
                        label={t('delayBetweenRetries')}
                        extra={t('delayBetweenRetriesHelp')}
                      >
                        <InputNumber min={0} max={60} style={{ width: '100%' }} />
                      </Form.Item>
                      <Form.Item
                        name="exponential_backoff"
                        label={t('exponentialBackoff')}
                        extra={t('exponentialBackoffHelp')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                      <Form.Item
                        name="http_max_retries"
                        label={t('httpMaxRetries')}
                        extra={t('httpMaxRetriesHelp')}
                      >
                        <InputNumber min={0} max={10} style={{ width: '100%' }} placeholder={t('providerDefault')} />
                      </Form.Item>
                      <Form.Item name="description" label="Description">
                        <Input placeholder={t('purposeOptional')} />
                      </Form.Item>
                      <Form.Item name="enabled" label="Enabled" valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </>
                  ),
                },
              ]}
            />
            <Form.Item name="builtin" hidden valuePropName="checked">
              <Switch />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </main>
  )
}
