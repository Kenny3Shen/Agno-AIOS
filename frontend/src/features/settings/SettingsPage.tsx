import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Flex, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import { ApiOutlined, CheckCircleOutlined, DeleteOutlined, EditOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import {
  getChatSettings,
  getGuardrailSettings,
  getKnowledgeRagSettings,
  getModels,
  getNotificationSettings,
  listAdminUsers,
  listRolePresets,
  saveChatSettings,
  saveGuardrailSettings,
  saveKnowledgeRagSettings,
  saveModels,
  saveNotificationSettings,
  SERVER_DEFAULTED_MODEL_FIELDS,
  setUserRole,
  testModel,
  type ChatSettings,
  type GuardrailSettings,
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
  const guardrailSettings = useQuery({
    queryKey: ['settings', 'guardrails'],
    queryFn: getGuardrailSettings,
    enabled: isAdmin && activeTab === 'guardrails',
  })
  const [guardrailForm] = Form.useForm<GuardrailSettings>()
  const [guardrailSaving, setGuardrailSaving] = useState(false)
  useEffect(() => {
    if (guardrailSettings.data) {
      guardrailForm.setFieldsValue(guardrailSettings.data)
    }
  }, [guardrailForm, guardrailSettings.data])
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
  const notificationSettings = useQuery({
    queryKey: ['settings', 'notifications'],
    queryFn: getNotificationSettings,
    enabled: activeTab === 'notifications',
  })
  const [feishuWebhookDraft, setFeishuWebhookDraft] = useState('')
  const [notificationSaving, setNotificationSaving] = useState(false)

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

  const saveFeishuWebhook = async () => {
    setNotificationSaving(true)
    try {
      await saveNotificationSettings({ feishu_webhook_url: feishuWebhookDraft.trim() })
      setFeishuWebhookDraft('')
      await client.invalidateQueries({ queryKey: ['settings', 'notifications'] })
      message.success(t('notificationSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('notificationSaveFailed'))
    } finally {
      setNotificationSaving(false)
    }
  }

  const clearFeishuWebhook = async () => {
    setNotificationSaving(true)
    try {
      await saveNotificationSettings({ feishu_webhook_url: '' })
      setFeishuWebhookDraft('')
      await client.invalidateQueries({ queryKey: ['settings', 'notifications'] })
      message.success(t('notificationCleared'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('notificationSaveFailed'))
    } finally {
      setNotificationSaving(false)
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

  const saveGuardrails = async (values: GuardrailSettings) => {
    setGuardrailSaving(true)
    try {
      const next = await saveGuardrailSettings(values)
      guardrailForm.setFieldsValue(next)
      await client.invalidateQueries({ queryKey: ['settings', 'guardrails'] })
      message.success(t('guardrailsSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('guardrailsSaveFailed'))
    } finally {
      setGuardrailSaving(false)
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

  type ChatField = keyof ChatSettings
  type ChatControl = 'switch' | 'number' | 'optional_number'
  const chatSettingRows: Array<
    SettingRow & { field: ChatField; control: ChatControl; min?: number; max?: number }
  > = [
    {
      key: 'show_thought_chain',
      field: 'show_thought_chain',
      parameter: t('securityTimeline'),
      description: t('securityTimelineDesc'),
      control: 'switch',
    },
    {
      key: 'show_raw_reasoning',
      field: 'show_raw_reasoning',
      parameter: t('rawReasoning'),
      description: t('rawReasoningDesc'),
      control: 'switch',
    },
    {
      key: 'show_raw_tool_io',
      field: 'show_raw_tool_io',
      parameter: t('rawToolIo'),
      description: t('rawToolIoDesc'),
      control: 'switch',
    },
    {
      key: 'memory_enabled',
      field: 'memory_enabled',
      parameter: t('longTermMemory'),
      description: t('longTermMemoryDesc'),
      control: 'switch',
    },
    {
      key: 'enable_agentic_memory',
      field: 'enable_agentic_memory',
      parameter: t('agenticMemoryLabel'),
      description: t('agenticMemoryDesc'),
      control: 'switch',
    },
    {
      key: 'session_summaries_enabled',
      field: 'session_summaries_enabled',
      parameter: t('sessionSummariesLabel'),
      description: t('sessionSummariesDesc'),
      control: 'switch',
    },
    {
      key: 'add_datetime_to_context',
      field: 'add_datetime_to_context',
      parameter: t('addDatetimeLabel'),
      description: t('addDatetimeDesc'),
      control: 'switch',
    },
    {
      key: 'markdown',
      field: 'markdown',
      parameter: t('markdownLabel'),
      description: t('markdownDesc'),
      control: 'switch',
    },
    {
      key: 'num_history_runs',
      field: 'num_history_runs',
      parameter: t('numHistoryRunsLabel'),
      description: t('numHistoryRunsDesc'),
      control: 'number',
      min: 0,
      max: 50,
    },
    {
      key: 'max_tool_calls_from_history',
      field: 'max_tool_calls_from_history',
      parameter: t('maxToolCallsHistoryLabel'),
      description: t('maxToolCallsHistoryDesc'),
      control: 'optional_number',
      min: 1,
      max: 200,
    },
    {
      key: 'default_tool_call_limit',
      field: 'default_tool_call_limit',
      parameter: t('defaultToolCallLimitLabel'),
      description: t('defaultToolCallLimitDesc'),
      control: 'optional_number',
      min: 1,
      max: 200,
    },
  ]

  const [chatForm] = Form.useForm<ChatSettings>()
  const [chatSaving, setChatSaving] = useState(false)
  useEffect(() => {
    if (chatSettings.data) {
      chatForm.setFieldsValue(chatSettings.data)
    }
  }, [chatForm, chatSettings.data])

  const saveChatRuntime = async (values: ChatSettings) => {
    setChatSaving(true)
    try {
      const payload: Partial<ChatSettings> = {
        ...values,
        max_tool_calls_from_history:
          values.max_tool_calls_from_history == null || Number(values.max_tool_calls_from_history) <= 0
            ? null
            : Number(values.max_tool_calls_from_history),
        default_tool_call_limit:
          values.default_tool_call_limit == null || Number(values.default_tool_call_limit) <= 0
            ? null
            : Number(values.default_tool_call_limit),
        num_history_runs: Number(values.num_history_runs ?? 5),
      }
      const next = await saveChatSettings(payload)
      chatForm.setFieldsValue(next)
      await client.invalidateQueries({ queryKey: ['settings', 'chat'] })
      message.success(t('chatSettingsSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('chatSettingsSaveFailed'))
    } finally {
      setChatSaving(false)
    }
  }

  const chatControls = (
    <div className="settings-param-panel">
      <Typography.Paragraph type="secondary">{t('chatRuntimeHint')}</Typography.Paragraph>
      <Form
        form={chatForm}
        layout="vertical"
        initialValues={{
          show_thought_chain: true,
          show_raw_reasoning: false,
          show_raw_tool_io: false,
          memory_enabled: true,
          enable_agentic_memory: false,
          session_summaries_enabled: true,
          add_datetime_to_context: true,
          markdown: true,
          num_history_runs: 5,
          max_tool_calls_from_history: null,
          default_tool_call_limit: null,
        }}
        onFinish={(values) => void saveChatRuntime(values)}
        disabled={chatSettings.isLoading || chatSaving}
      >
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
              width: 260,
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
              width: 160,
              render: (_field, row) => {
                if (row.control === 'switch') {
                  return (
                    <Form.Item name={row.field} noStyle valuePropName="checked">
                      <Switch aria-label={String(row.field)} />
                    </Form.Item>
                  )
                }
                return (
                  <Form.Item name={row.field} noStyle>
                    <InputNumber
                      min={row.min}
                      max={row.max}
                      step={1}
                      style={{ width: '100%' }}
                      placeholder={row.control === 'optional_number' ? '—' : undefined}
                    />
                  </Form.Item>
                )
              },
            },
          ]}
        />
        <div className="settings-param-actions">
          <Button type="primary" htmlType="submit" loading={chatSaving}>
            {t('chatSettingsSave')}
          </Button>
        </div>
      </Form>
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

  type GuardrailField = keyof GuardrailSettings
  const guardrailSettingRows: Array<{
    key: GuardrailField
    field: GuardrailField
    parameter: string
    description: string
  }> = [
    {
      key: 'enabled',
      field: 'enabled',
      parameter: t('guardrailsEnabledLabel'),
      description: t('guardrailsEnabledDesc'),
    },
    {
      key: 'pii_enabled',
      field: 'pii_enabled',
      parameter: t('guardrailsPiiEnabledLabel'),
      description: t('guardrailsPiiEnabledDesc'),
    },
    {
      key: 'pii_mask',
      field: 'pii_mask',
      parameter: t('guardrailsPiiMaskLabel'),
      description: t('guardrailsPiiMaskDesc'),
    },
    {
      key: 'pii_check_email',
      field: 'pii_check_email',
      parameter: t('guardrailsPiiEmailLabel'),
      description: t('guardrailsPiiEmailDesc'),
    },
    {
      key: 'pii_check_phone',
      field: 'pii_check_phone',
      parameter: t('guardrailsPiiPhoneLabel'),
      description: t('guardrailsPiiPhoneDesc'),
    },
    {
      key: 'prompt_injection_enabled',
      field: 'prompt_injection_enabled',
      parameter: t('guardrailsPromptInjectionLabel'),
      description: t('guardrailsPromptInjectionDesc'),
    },
  ]

  const guardrailControls = (
    <div className="settings-param-panel settings-guardrails-panel">
      <Typography.Paragraph type="secondary">{t('guardrailsHint')}</Typography.Paragraph>
      <Form
        form={guardrailForm}
        layout="vertical"
        initialValues={{
          enabled: true,
          pii_enabled: true,
          pii_mask: false,
          pii_check_email: false,
          pii_check_phone: true,
          prompt_injection_enabled: true,
        }}
        onFinish={(values) => void saveGuardrails(values)}
        disabled={guardrailSettings.isLoading || guardrailSaving}
      >
        <Table<(typeof guardrailSettingRows)[number]>
          rowKey="key"
          size="middle"
          loading={guardrailSettings.isLoading}
          pagination={false}
          dataSource={guardrailSettingRows}
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
              width: 120,
              render: (_field, row) => (
                <Form.Item name={row.field} noStyle valuePropName="checked">
                  <Switch />
                </Form.Item>
              ),
            },
          ]}
        />
        <div className="settings-param-actions">
          <Button type="primary" htmlType="submit" loading={guardrailSaving}>
            {t('guardrailsSave')}
          </Button>
        </div>
      </Form>
    </div>
  )

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

  const notificationControls = (
    <div className="settings-param-block">
      <Typography.Paragraph type="secondary">{t('notificationIntro')}</Typography.Paragraph>
      <Typography.Paragraph type="secondary">
        {notificationSettings.data?.feishu_webhook_configured
          ? t('feishuConfigured', { hint: notificationSettings.data.feishu_webhook_hint || '…' })
          : notificationSettings.data?.global_feishu_webhook_configured
            ? t('feishuUsingGlobal')
            : t('feishuNotConfigured')}
      </Typography.Paragraph>
      <Flex vertical gap="middle" style={{ width: '100%', maxWidth: 560 }}>
        <Input.Password
          value={feishuWebhookDraft}
          onChange={(event) => setFeishuWebhookDraft(event.target.value)}
          placeholder={t('feishuWebhookPlaceholder')}
          autoComplete="off"
        />
        <Space wrap>
          <Button type="primary" loading={notificationSaving} onClick={() => void saveFeishuWebhook()}>
            {t('saveFeishuWebhook')}
          </Button>
          <Popconfirm
            title={t('clearFeishuConfirm')}
            onConfirm={() => void clearFeishuWebhook()}
            disabled={!notificationSettings.data?.feishu_webhook_configured}
          >
            <Button
              danger
              loading={notificationSaving}
              disabled={!notificationSettings.data?.feishu_webhook_configured}
            >
              {t('clearFeishuWebhook')}
            </Button>
          </Popconfirm>
        </Space>
      </Flex>
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
            { key: 'notifications', label: t('notificationsTab'), children: notificationControls },
            ...(isAdmin
              ? [
                  { key: 'chat', label: t('chatSettings'), children: chatControls },
                  { key: 'guardrails', label: t('guardrailsTab'), children: guardrailControls },
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
