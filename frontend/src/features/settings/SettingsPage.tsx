import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import { ApiOutlined, CheckCircleOutlined, DeleteOutlined, EditOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import {
  getChatSettings,
  getKnowledgeRagSettings,
  getModels,
  listAdminUsers,
  listRolePresets,
  saveChatSettings,
  saveKnowledgeRagSettings,
  saveModels,
  SERVER_DEFAULTED_MODEL_FIELDS,
  setUserRole,
  testModel,
  type ChatSettings,
  type KnowledgeRagSettings,
  type ModelConfigInput,
  type ModelConfigUpdatePayload,
} from './api'
import type { AuthUser } from '@/shared/types/auth'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'
import { useTranslation } from 'react-i18next'
import './settings.css'

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

const omitProviderManagedFields = (model: ModelConfigInput): ModelConfigInput => {
  const result = { ...model }
  SERVER_DEFAULTED_MODEL_FIELDS.forEach((field) => delete result[field])
  return result
}

export function SettingsPage() {
  const { t } = useTranslation('settings')
  const { message } = App.useApp()
  const client = useQueryClient()
  const models = useQuery({ queryKey: ['settings', 'models'], queryFn: getModels })
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const chatSettings = useQuery({ queryKey: ['settings', 'chat'], queryFn: getChatSettings, enabled: isAdmin })
  const [editing, setEditing] = useState<ModelConfigInput | null>(null)
  const [form] = Form.useForm<ModelConfigInput>()
  const [saving, setSaving] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('models')
  const knowledgeRagSettings = useQuery({
    queryKey: ['settings', 'knowledge'],
    queryFn: getKnowledgeRagSettings,
    enabled: isAdmin && activeTab === 'knowledge',
  })
  const [knowledgeForm] = Form.useForm<KnowledgeRagSettings>()
  const [knowledgeSaving, setKnowledgeSaving] = useState(false)
  useEffect(() => {
    if (knowledgeRagSettings.data) {
      knowledgeForm.setFieldsValue(knowledgeRagSettings.data)
    }
  }, [knowledgeForm, knowledgeRagSettings.data])
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

  const saveKnowledgeRag = async (values: KnowledgeRagSettings) => {
    setKnowledgeSaving(true)
    try {
      const payload: Partial<KnowledgeRagSettings> = {
        ...values,
        similarity_threshold:
          values.similarity_threshold == null || Number(values.similarity_threshold) <= 0
            ? null
            : Number(values.similarity_threshold),
      }
      const next = await saveKnowledgeRagSettings(payload)
      knowledgeForm.setFieldsValue(next)
      await client.invalidateQueries({ queryKey: ['settings', 'knowledge'] })
      message.success(t('knowledgeRagSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('knowledgeRagSaveFailed'))
    } finally {
      setKnowledgeSaving(false)
    }
  }

  const openEditor = (model: ModelConfigInput) => {
    form.resetFields()
    form.setFieldsValue({
      ...model,
      enabled: model.enabled ?? true,
    })
    setEditing(model)
  }

  const closeEditor = () => {
    setEditing(null)
    form.resetFields()
  }

  const persist = async (next: ModelConfigUpdatePayload) => {
    await saveModels(next)
    await client.invalidateQueries({ queryKey: ['settings', 'models'] })
  }

  const saveModel = async (model: ModelConfigInput) => {
    const current: ModelConfigResponse = models.data ?? { active_model_id: model.id, models: [] }
    const previous = current.models.find((item) => item.id === model.id)
    const normalized: ModelConfigInput = {
      ...previous,
      ...model,
      name: model.name.trim(),
      model_id: model.model_id.trim(),
      base_url: (model.base_url ?? '').trim(),
      enabled: model.enabled ?? true,
      builtin: previous?.builtin ?? model.builtin ?? false,
    }
    const submitted = !previous || previous.provider !== model.provider
      ? omitProviderManagedFields(normalized)
      : normalized
    const next: ModelConfigInput[] = current.models.some((item) => item.id === submitted.id)
      ? current.models.map((item) => (item.id === submitted.id ? submitted : item))
      : [...current.models, submitted]
    setSaving(true)
    try {
      await persist({ active_model_id: current.active_model_id, models: next })
      message.success(t('modelSaved'))
      closeEditor()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('modelSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const addModel = () => {
    openEditor({
      id: crypto.randomUUID(),
      name: '',
      model_id: '',
      provider: 'openai-compatible',
      base_url: '',
      api_key: '',
      enabled: true,
      builtin: false,
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

  type SettingRow = {
    key: string
    parameter: string
    description: string
  }

  const chatSettingRows: Array<SettingRow & { field: keyof ChatSettings }> = [
    {
      key: 'show_thought_chain',
      field: 'show_thought_chain',
      parameter: t('securityTimeline'),
      description: t('securityTimelineDesc'),
    },
    {
      key: 'show_raw_reasoning',
      field: 'show_raw_reasoning',
      parameter: t('rawReasoning'),
      description: t('rawReasoningDesc'),
    },
    {
      key: 'show_raw_tool_io',
      field: 'show_raw_tool_io',
      parameter: t('rawToolIo'),
      description: t('rawToolIoDesc'),
    },
    {
      key: 'memory_enabled',
      field: 'memory_enabled',
      parameter: t('longTermMemory'),
      description: t('longTermMemoryDesc'),
    },
  ]

  const chatControls = (
    <div className="settings-param-panel">
      <Table<(typeof chatSettingRows)[number]>
        rowKey="key"
        size="middle"
        loading={chatSettings.isLoading}
        pagination={false}
        dataSource={chatSettingRows}
        columns={[
          {
            title: t('colParameter'),
            dataIndex: 'parameter',
            width: 200,
            render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
          },
          {
            title: t('colDescription'),
            dataIndex: 'description',
            render: (value: string) => (
              <Typography.Text type="secondary" className="settings-param-description">
                {value}
              </Typography.Text>
            ),
          },
          {
            title: t('colValue'),
            dataIndex: 'field',
            width: 120,
            align: 'center',
            render: (field: keyof ChatSettings) => (
              <Switch
                checked={Boolean(chatSettings.data?.[field])}
                loading={chatSettings.isFetching}
                onChange={(next) => void setChatSetting(field, next)}
                aria-label={String(field)}
              />
            ),
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


  const knowledgeSearchTypeOptions = [
    { value: 'hybrid', label: 'hybrid' },
    { value: 'vector', label: 'vector' },
    { value: 'keyword', label: 'keyword' },
  ]

  type KnowledgeField =
    | 'search_type'
    | 'top_k'
    | 'vector_score_weight'
    | 'similarity_threshold'
    | 'content_language'
    | 'prefix_match'
    | 'rerank_enabled'
    | 'rerank_candidate_multiplier'
    | 'rerank_min_candidates'
    | 'rerank_model'

  const knowledgeSettingRows: Array<SettingRow & { field: KnowledgeField; control: 'select' | 'number' | 'switch' | 'text' | 'readonly' }> = [
    {
      key: 'search_type',
      field: 'search_type',
      parameter: t('searchTypeLabel'),
      description: t('searchTypeDesc'),
      control: 'select',
    },
    {
      key: 'top_k',
      field: 'top_k',
      parameter: t('topKLabel'),
      description: t('topKDesc'),
      control: 'number',
    },
    {
      key: 'vector_score_weight',
      field: 'vector_score_weight',
      parameter: t('vectorScoreWeightLabel'),
      description: t('vectorScoreWeightDesc'),
      control: 'number',
    },
    {
      key: 'similarity_threshold',
      field: 'similarity_threshold',
      parameter: t('similarityThresholdLabel'),
      description: t('similarityThresholdDesc'),
      control: 'number',
    },
    {
      key: 'content_language',
      field: 'content_language',
      parameter: t('contentLanguageLabel'),
      description: t('contentLanguageDesc'),
      control: 'text',
    },
    {
      key: 'prefix_match',
      field: 'prefix_match',
      parameter: t('prefixMatchLabel'),
      description: t('prefixMatchDesc'),
      control: 'switch',
    },
    {
      key: 'rerank_enabled',
      field: 'rerank_enabled',
      parameter: t('rerankEnabledLabel'),
      description: t('rerankEnabledDesc'),
      control: 'switch',
    },
    {
      key: 'rerank_candidate_multiplier',
      field: 'rerank_candidate_multiplier',
      parameter: t('rerankMultiplierLabel'),
      description: t('rerankMultiplierDesc'),
      control: 'number',
    },
    {
      key: 'rerank_min_candidates',
      field: 'rerank_min_candidates',
      parameter: t('rerankMinCandidatesLabel'),
      description: t('rerankMinCandidatesDesc'),
      control: 'number',
    },
    {
      key: 'rerank_model',
      field: 'rerank_model',
      parameter: t('rerankModelLabel'),
      description: t('rerankModelDesc'),
      control: 'readonly',
    },
  ]

  const knowledgeControls = (
    <div className="settings-param-panel settings-knowledge-panel">
      <Typography.Paragraph type="secondary">{t('knowledgeRagHint')}</Typography.Paragraph>
      <Form
        form={knowledgeForm}
        layout="vertical"
        initialValues={{
          search_type: 'hybrid',
          top_k: 5,
          vector_score_weight: 0.55,
          similarity_threshold: 0.35,
          content_language: 'english',
          prefix_match: false,
          rerank_enabled: true,
          rerank_candidate_multiplier: 3,
          rerank_min_candidates: 10,
        }}
        onFinish={(values) => void saveKnowledgeRag(values)}
        disabled={knowledgeRagSettings.isLoading || knowledgeSaving}
      >
        <Table<(typeof knowledgeSettingRows)[number]>
          rowKey="key"
          size="middle"
          loading={knowledgeRagSettings.isLoading}
          pagination={false}
          dataSource={knowledgeSettingRows}
          columns={[
            {
              title: t('colParameter'),
              dataIndex: 'parameter',
              width: 240,
              render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
            },
            {
              title: t('colDescription'),
              dataIndex: 'description',
              render: (value: string) => (
                <Typography.Text type="secondary" className="settings-param-description">
                  {value}
                </Typography.Text>
              ),
            },
            {
              title: t('colValue'),
              dataIndex: 'field',
              width: 220,
              render: (_field, row) => {
                if (row.control === 'select') {
                  return (
                    <Form.Item name="search_type" noStyle rules={[{ required: true }]}>
                      <Select options={knowledgeSearchTypeOptions} style={{ width: '100%' }} />
                    </Form.Item>
                  )
                }
                if (row.control === 'switch') {
                  return (
                    <Form.Item name={row.field} noStyle valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  )
                }
                if (row.control === 'text') {
                  return (
                    <Form.Item name="content_language" noStyle>
                      <Input placeholder="english / simple" />
                    </Form.Item>
                  )
                }
                if (row.control === 'readonly') {
                  return (
                    <Typography.Text type="secondary">
                      {knowledgeRagSettings.data?.rerank_model || '—'}
                    </Typography.Text>
                  )
                }
                const numberProps =
                  row.field === 'top_k'
                    ? { min: 1, max: 50, step: 1 }
                    : row.field === 'vector_score_weight' || row.field === 'similarity_threshold'
                      ? { min: 0, max: 1, step: 0.05 }
                      : row.field === 'rerank_candidate_multiplier'
                        ? { min: 1, max: 20, step: 1 }
                        : { min: 1, max: 100, step: 1 }
                return (
                  <Form.Item name={row.field} noStyle>
                    <InputNumber {...numberProps} style={{ width: '100%' }} />
                  </Form.Item>
                )
              },
            },
          ]}
        />
        <div className="settings-param-actions">
          <Button type="primary" htmlType="submit" loading={knowledgeSaving}>
            {t('knowledgeRagSave')}
          </Button>
        </div>
      </Form>
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
                  { key: 'knowledge', label: t('knowledgeRagTab'), children: knowledgeControls },
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
            <Form.Item name="name" label={t('nameLabel')} rules={[{ required: true, whitespace: true, message: t('nameRequired') }]}>
              <Input placeholder={t('namePlaceholder')} />
            </Form.Item>
            <Form.Item name="provider" label={t('provider')} rules={[{ required: true }]}>
              <Select
                options={providerOptions}
                onChange={(provider: ModelConfig['provider']) => {
                  form.setFieldsValue({ provider, base_url: '' })
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
