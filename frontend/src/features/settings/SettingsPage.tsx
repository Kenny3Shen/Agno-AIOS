import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import { ApiOutlined, CheckCircleOutlined, DeleteOutlined, EditOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import {
  getChatSettings,
  getModels,
  listAdminUsers,
  listRolePresets,
  saveChatSettings,
  saveModels,
  setUserRole,
  testModel,
  type ChatSettings,
} from './api'
import type { AuthUser } from '@/shared/types/auth'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'
import { useTranslation } from 'react-i18next'
import './settings.css'

/** Optimal runtime knobs from capability profile — not shown in the simple form. */
const providerDefaults = (provider: ModelConfig['provider']): Partial<ModelConfig> => {
  if (provider === 'deepseek')
    return {
      api_protocol: 'chat-completions',
      structured_output_mode: 'json',
      default_reasoning_effort: 'max',
      base_url: 'https://api.deepseek.com',
      parallel_tool_calls: null,
      live_search_enabled: false,
      retries: 4,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
    }
  if (provider === 'openai')
    return {
      api_protocol: 'responses',
      structured_output_mode: 'native',
      default_reasoning_effort: 'high',
      base_url: '',
      parallel_tool_calls: null,
      live_search_enabled: false,
      retries: 4,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
    }
  if (provider === 'xai')
    return {
      api_protocol: 'chat-completions',
      structured_output_mode: 'json',
      default_reasoning_effort: null,
      base_url: 'https://api.x.ai/v1',
      parallel_tool_calls: null,
      live_search_enabled: false,
      retries: 4,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
    }
  return {
    api_protocol: 'chat-completions',
    structured_output_mode: 'json',
    default_reasoning_effort: null,
    parallel_tool_calls: null,
    live_search_enabled: false,
    retries: 4,
    delay_between_retries: 1,
    exponential_backoff: true,
    http_max_retries: null,
  }
}

const providerOptions = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'xai', label: 'xAI / Grok' },
  { value: 'openai-compatible', label: 'OpenAI-compatible' },
]

const baseUrlPlaceholder = (provider: ModelConfig['provider']) => {
  if (provider === 'xai') return 'https://api.x.ai/v1'
  if (provider === 'deepseek') return 'https://api.deepseek.com'
  if (provider === 'openai') return 'https://api.openai.com/v1'
  return 'https://api.example.com/v1'
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
  const usersQuery = useQuery({
    queryKey: ['settings', 'admin-users'],
    queryFn: () => listAdminUsers(1, 100),
    enabled: isAdmin && activeTab === 'users',
  })
  const rolePresetsQuery = useQuery({
    queryKey: ['settings', 'role-presets'],
    queryFn: listRolePresets,
    enabled: isAdmin && activeTab === 'users',
  })
  const [roleUpdatingId, setRoleUpdatingId] = useState<string | null>(null)

  const roleLabel = (role: string) => {
    const key = `role_${role}` as const
    const translated = t(key)
    return translated === key ? role : translated
  }

  const roleOptions = (rolePresetsQuery.data ?? []).map((preset) => ({
    value: String(preset.role),
    label: roleLabel(String(preset.role)),
  }))

  const updateUserRole = async (row: AuthUser, role: string) => {
    if (row.is_superuser && role !== 'admin') {
      message.warning(t('cannotDemoteSuperuser'))
      return
    }
    setRoleUpdatingId(row.id)
    try {
      await setUserRole(row.id, role)
      await client.invalidateQueries({ queryKey: ['settings', 'admin-users'] })
      message.success(t('roleUpdated', { role: roleLabel(role) }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('roleUpdateFailed'))
    } finally {
      setRoleUpdatingId(null)
    }
  }

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
      ...providerDefaults(model.provider),
      ...model,
      enabled: model.enabled ?? true,
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
    const current = models.data ?? { active_model_id: model.id, models: [] }
    const previous = current.models.find((item) => item.id === model.id)
    const defaults = providerDefaults(model.provider)
    // Form only edits connection fields; keep optimal runtime knobs unless already stored.
    const normalized: ModelConfig = {
      ...defaults,
      ...previous,
      ...model,
      name: model.name.trim(),
      model_id: model.model_id.trim(),
      base_url: (model.base_url ?? '').trim(),
      api_protocol: (previous?.api_protocol ?? defaults.api_protocol ?? 'chat-completions') as ModelConfig['api_protocol'],
      structured_output_mode: (previous?.structured_output_mode ??
        defaults.structured_output_mode ??
        'json') as ModelConfig['structured_output_mode'],
      default_reasoning_effort:
        previous?.default_reasoning_effort !== undefined
          ? previous.default_reasoning_effort
          : (defaults.default_reasoning_effort ?? null),
      parallel_tool_calls: previous?.parallel_tool_calls ?? defaults.parallel_tool_calls ?? null,
      live_search_enabled: previous?.live_search_enabled ?? defaults.live_search_enabled ?? false,
      retries: previous?.retries ?? defaults.retries ?? 4,
      delay_between_retries: previous?.delay_between_retries ?? defaults.delay_between_retries ?? 1,
      exponential_backoff: previous?.exponential_backoff ?? defaults.exponential_backoff ?? true,
      http_max_retries: previous?.http_max_retries ?? defaults.http_max_retries ?? null,
      description: previous?.description ?? '',
      enabled: model.enabled ?? true,
      builtin: previous?.builtin ?? model.builtin ?? false,
    }
    // Switching provider: re-apply optimal knobs for the new provider.
    if (previous && previous.provider !== model.provider) {
      Object.assign(normalized, defaults, {
        id: model.id,
        name: normalized.name,
        model_id: normalized.model_id,
        api_key: model.api_key,
        base_url: normalized.base_url || String(defaults.base_url ?? ''),
        enabled: normalized.enabled,
        builtin: normalized.builtin,
        provider: model.provider,
      })
    }
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

  const addModel = () => {
    const defaults = providerDefaults('openai-compatible')
    openEditor({
      id: crypto.randomUUID(),
      name: '',
      model_id: '',
      provider: 'openai-compatible',
      api_protocol: defaults.api_protocol ?? 'chat-completions',
      structured_output_mode: defaults.structured_output_mode ?? 'json',
      default_reasoning_effort: defaults.default_reasoning_effort ?? null,
      base_url: defaults.base_url ?? '',
      api_key: '',
      description: '',
      enabled: true,
      builtin: false,
      parallel_tool_calls: defaults.parallel_tool_calls ?? null,
      live_search_enabled: defaults.live_search_enabled ?? false,
      retries: defaults.retries ?? 4,
      delay_between_retries: defaults.delay_between_retries ?? 1,
      exponential_backoff: defaults.exponential_backoff ?? true,
      http_max_retries: defaults.http_max_retries ?? null,
    })
  }

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

  const deleteModel = async (model: ModelConfig) => {
    const current = models.data
    if (!current) return
    if (model.builtin) {
      message.warning(t('cannotDeleteBuiltin'))
      return
    }
    if (current.models.length <= 1) {
      message.warning(t('cannotDeleteLastModel'))
      return
    }
    const remaining = current.models.filter((item) => item.id !== model.id)
    if (!remaining.length) {
      message.warning(t('cannotDeleteLastModel'))
      return
    }
    let active_model_id = current.active_model_id
    if (active_model_id === model.id) {
      const next =
        remaining.find((item) => item.enabled && item.configured !== false) ??
        remaining.find((item) => item.enabled) ??
        remaining[0]
      active_model_id = next.id
    }
    setUpdatingId(model.id)
    try {
      await persist({ active_model_id, models: remaining })
      message.success(t('modelDeleted', { name: model.name }))
      if (editing?.id === model.id) closeEditor()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('modelDeleteFailed'))
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
      scroll={{ x: 960 }}
      columns={[
        {
          title: t('colName'),
          dataIndex: 'name',
          width: 220,
          ellipsis: true,
          render: (value, row) => (
            <Space>
              <strong>{value}</strong>
              {models.data?.active_model_id === row.id && <Tag color="blue">{t('tagActive')}</Tag>}
            </Space>
          ),
        },
        { title: t('colModelId'), dataIndex: 'model_id', width: 200, ellipsis: true },
        {
          title: t('provider'),
          dataIndex: 'provider',
          width: 140,
          render: (value: ModelConfig['provider']) => <Tag>{value}</Tag>,
        },
        {
          title: t('colBaseUrl'),
          dataIndex: 'base_url',
          width: 240,
          ellipsis: { showTitle: false },
          render: (value) => <Typography.Text ellipsis={{ tooltip: value }}>{value || '—'}</Typography.Text>,
        },
        {
          title: t('colConfigured'),
          dataIndex: 'configured',
          width: 130,
          render: (value) => <Tag color={value ? 'success' : 'warning'}>{value ? t('tagReady') : t('tagMissingKey')}</Tag>,
        },
        {
          title: t('colEnabled'),
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
          title: t('colActions'),
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
              <Tooltip
                title={
                  row.builtin
                    ? t('cannotDeleteBuiltin')
                    : (models.data?.models.length ?? 0) <= 1
                      ? t('cannotDeleteLastModel')
                      : t('deleteModel')
                }
              >
                <Popconfirm
                  title={t('deleteModelConfirm', { name: row.name })}
                  description={
                    models.data?.active_model_id === row.id
                      ? t('deleteActiveModelHint')
                      : undefined
                  }
                  okText={t('deleteModel')}
                  cancelText={t('common:cancel')}
                  okButtonProps={{ danger: true }}
                  disabled={row.builtin || (models.data?.models.length ?? 0) <= 1}
                  onConfirm={() => void deleteModel(row)}
                >
                  <Button
                    danger
                    icon={<DeleteOutlined />}
                    disabled={row.builtin || (models.data?.models.length ?? 0) <= 1}
                    loading={updatingId === row.id}
                    aria-label={t('deleteModelNamed', { name: row.name })}
                  />
                </Popconfirm>
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
      <div className="settings-chat-privacy">
        <Tooltip title={t('privacyNote')}>
          <Typography.Text type="secondary" className="settings-chat-privacy-trigger">
            <QuestionCircleOutlined aria-label={t('privacyNote')} />
            <span>{t('privacyNoteShort')}</span>
          </Typography.Text>
        </Tooltip>
      </div>
    </div>
  )

  const usersPanel = (
    <div className="settings-users-panel">
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {t('usersHint')}
      </Typography.Paragraph>
      <Table<AuthUser>
        rowKey="id"
        size="small"
        loading={usersQuery.isLoading}
        dataSource={usersQuery.data?.data ?? []}
        pagination={false}
        columns={[
          { title: t('colEmail'), dataIndex: 'email', ellipsis: true },
          {
            title: t('colRole'),
            dataIndex: 'role',
            width: 200,
            render: (value: string | undefined, row) => (
              <Select
                size="small"
                style={{ width: '100%' }}
                value={value || 'user'}
                options={roleOptions.length ? roleOptions : [{ value: value || 'user', label: roleLabel(value || 'user') }]}
                loading={roleUpdatingId === row.id}
                disabled={Boolean(row.is_superuser) && (value || 'user') === 'admin'}
                onChange={(role) => void updateUserRole(row, role)}
              />
            ),
          },
          {
            title: t('colSuperuser'),
            dataIndex: 'is_superuser',
            width: 120,
            render: (value: boolean | undefined) => (value ? t('superuserYes') : t('superuserNo')),
          },
        ]}
      />
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
            ...(isAdmin
              ? [
                  { key: 'chat', label: t('chatSettings'), children: chatControls },
                  { key: 'users', label: t('usersTab'), children: usersPanel },
                ]
              : []),
          ]}
        />
      </Card>
      <Modal
        width={480}
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
          <Form form={form} layout="vertical" onFinish={saveModel} requiredMark="optional">
            <Form.Item name="id" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="builtin" hidden valuePropName="checked">
              <Switch />
            </Form.Item>
            {/* Hidden optimal knobs — filled by providerDefaults / save merge */}
            <Form.Item name="api_protocol" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="structured_output_mode" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="default_reasoning_effort" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="retries" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="delay_between_retries" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="exponential_backoff" hidden valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="http_max_retries" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="parallel_tool_calls" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="live_search_enabled" hidden valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="description" hidden>
              <Input />
            </Form.Item>

            <Form.Item name="name" label={t('nameLabel')} rules={[{ required: true, whitespace: true, message: t('nameRequired') }]}>
              <Input placeholder={t('namePlaceholder')} />
            </Form.Item>
            <Form.Item name="provider" label={t('provider')} rules={[{ required: true }]}>
              <Select
                options={providerOptions}
                onChange={(provider: ModelConfig['provider']) => {
                  const defaults = providerDefaults(provider)
                  form.setFieldsValue({
                    ...defaults,
                    base_url: defaults.base_url ?? '',
                  })
                }}
              />
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(previous, current) => previous.provider !== current.provider}>
              {({ getFieldValue }) => (
                <Form.Item
                  name="model_id"
                  label={t('modelIdLabel')}
                  tooltip={getFieldValue('provider') === 'xai' ? t('xaiReasoningHint') : undefined}
                  rules={[{ required: true, whitespace: true, message: t('modelIdRequired') }]}
                >
                  <Input placeholder={t('modelIdPlaceholder')} />
                </Form.Item>
              )}
            </Form.Item>
            <Form.Item name="api_key" label={t('apiKeyLabel')} rules={[{ required: true, whitespace: true, message: t('apiKeyRequired') }]}>
              <Input.Password placeholder="sk-..." autoComplete="off" />
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(previous, current) => previous.provider !== current.provider}>
              {({ getFieldValue }) => {
                const provider = getFieldValue('provider') as ModelConfig['provider']
                const baseUrlRequired = provider === 'openai-compatible'
                return (
                  <Form.Item
                    name="base_url"
                    label="Base URL"
                    tooltip={baseUrlRequired ? t('baseUrlRequired') : t('baseUrlOptional')}
                    rules={[
                      { required: baseUrlRequired, whitespace: true, message: t('baseUrlRequired') },
                      { type: 'url', warningOnly: !baseUrlRequired, message: t('urlInvalid') },
                    ]}
                  >
                    <Input placeholder={baseUrlPlaceholder(provider)} />
                  </Form.Item>
                )
              }}
            </Form.Item>
            <Form.Item name="enabled" label={t('enabledLabel')} valuePropName="checked">
              <Switch />
            </Form.Item>
            <Typography.Paragraph type="secondary" className="settings-model-hint" style={{ marginBottom: 0 }}>
              {t('autoDefaultsHint')}
            </Typography.Paragraph>
          </Form>
        )}
      </Modal>
    </main>
  )
}
