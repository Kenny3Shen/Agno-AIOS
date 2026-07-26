import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Collapse,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  ApiOutlined,
  AuditOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { hasScope, roleOf } from '@/shared/auth/permissions'
import {
  getChatSettings,
  getCveSourceSettings,
  getGuardrailSettings,
  getKnowledgeRagSettings,
  getModels,
  getNotificationSettings,
  listAdminUsers,
  listRolePresets,
  saveChatSettings,
  saveCveSourceSettings,
  saveGuardrailSettings,
  saveKnowledgeRagSettings,
  saveModels,
  saveNotificationSettings,
  SERVER_DEFAULTED_MODEL_FIELDS,
  setUserRole,
  testModel,
  type ChatSettings,
  type CveSourceSetting,
  type GuardrailSettings,
  type KnowledgeRagSettings,
  type MemoryMode,
  type ModelConfigInput,
  type ModelConfigUpdatePayload,
} from './api'
import type { AuthUser, UserRole } from '@/shared/types/auth'
import type { ModelConfig, ModelConfigResponse } from '@/shared/types/common'
import { useTranslation } from 'react-i18next'
import { createModelId } from './modelId'
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

/** Product defaults for Settings forms (align with server DEFAULT_* seeds). */
const CHAT_SETTINGS_DEFAULTS: ChatSettings = {
  show_thought_chain: true,
  show_raw_reasoning: false,
  show_raw_tool_io: false,
  memory_mode: 'automatic',
  session_summaries_enabled: true,
  add_datetime_to_context: true,
  markdown: true,
  num_history_runs: 5,
  max_tool_calls_from_history: null,
  default_tool_call_limit: null,
  memory_tool_content_enabled: false,
  memory_prune_enabled: true,
  memory_prune_retention_days: 90,
  memory_prune_top_k: 50,
  memory_inject_enabled: true,
  memory_inject_top_k: 12,
  memory_inject_window_days: 90,
  memory_inject_dedupe_topics: true,
}

const normalizeChatSettings = (raw: Partial<ChatSettings> | undefined): ChatSettings => {
  const base = { ...CHAT_SETTINGS_DEFAULTS, ...raw }
  const memory_mode: MemoryMode =
    raw?.memory_mode === 'off' || raw?.memory_mode === 'automatic' || raw?.memory_mode === 'agentic'
      ? raw.memory_mode
      : CHAT_SETTINGS_DEFAULTS.memory_mode
  return { ...base, memory_mode }
}

const GUARDRAIL_SETTINGS_DEFAULTS: GuardrailSettings = {
  enabled: true,
  pii_enabled: true,
  pii_mask: false,
  pii_check_email: false,
  pii_check_phone: true,
  prompt_injection_enabled: true,
}

const KNOWLEDGE_RAG_SETTINGS_DEFAULTS: KnowledgeRagSettings = {
  search_type: 'hybrid',
  top_k: 5,
  vector_score_weight: 0.55,
  similarity_threshold: 0.35,
  content_language: 'english',
  prefix_match: false,
  rerank_enabled: true,
  rerank_candidate_multiplier: 3,
  rerank_min_candidates: 10,
}

export function SettingsPage() {
  const { t } = useTranslation('settings')
  const { message } = App.useApp()
  const client = useQueryClient()
  const models = useQuery({ queryKey: ['settings', 'models'], queryFn: getModels })
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const canManageModels = hasScope(currentUser.data, 'config:write')
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
  const cveSourceSettings = useQuery({
    queryKey: ['settings', 'cve-sources'],
    queryFn: getCveSourceSettings,
    enabled: isAdmin && activeTab === 'cve-sources',
  })
  const [cveSourceEnabled, setCveSourceEnabled] = useState<Record<string, boolean>>({})
  const [cveSourceSaving, setCveSourceSaving] = useState(false)
  useEffect(() => {
    const sources = cveSourceSettings.data?.sources
    if (!sources) return
    setCveSourceEnabled(Object.fromEntries(sources.map(({ source, enabled }) => [source, enabled])))
  }, [cveSourceSettings.data])
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

  const cveSourceLabel = (source: string) => {
    const labels: Record<string, string> = {
      github: t('cveSourceGithub'),
      'exploit-db': t('cveSourceExploitDb'),
    }
    return labels[source] ?? source
  }

  const cveSourceDescription = (source: string) => {
    const descriptions: Record<string, string> = {
      github: t('cveSourceGithubDesc'),
      'exploit-db': t('cveSourceExploitDbDesc'),
    }
    return descriptions[source] ?? t('cveSourceCustomDesc')
  }

  const roleOptions = (rolePresetsQuery.data ?? []).map((preset) => ({
    value: preset.role,
    label: roleLabel(preset.role),
  }))

  const updateUserRole = async (row: AuthUser, role: UserRole) => {
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

  const saveCveSources = async () => {
    const sources = Object.fromEntries(
      (cveSourceSettings.data?.sources ?? []).map(({ source, enabled }) => [source, cveSourceEnabled[source] ?? enabled])
    )
    if (!Object.keys(sources).length) return

    setCveSourceSaving(true)
    try {
      const next = await saveCveSourceSettings(sources)
      setCveSourceEnabled(Object.fromEntries(next.sources.map(({ source, enabled }) => [source, enabled])))
      await client.invalidateQueries({ queryKey: ['settings', 'cve-sources'] })
      message.success(t('cveSourcesSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('cveSourcesSaveFailed'))
    } finally {
      setCveSourceSaving(false)
    }
  }

  const saveKnowledgeRag = async (values: KnowledgeRagSettings) => {
    setKnowledgeSaving(true)
    try {
      const payload: Partial<KnowledgeRagSettings> = {
        ...values,
        similarity_threshold:
          values.similarity_threshold == null || Number(values.similarity_threshold) <= 0 ? null : Number(values.similarity_threshold),
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

  const resetKnowledgeToDefaults = async () => {
    knowledgeForm.setFieldsValue(KNOWLEDGE_RAG_SETTINGS_DEFAULTS)
    await saveKnowledgeRag(KNOWLEDGE_RAG_SETTINGS_DEFAULTS)
  }

  const resetKnowledgeFieldToDefault = async (field: Exclude<keyof KnowledgeRagSettings, 'rerank_model'>) => {
    const value = KNOWLEDGE_RAG_SETTINGS_DEFAULTS[field]
    knowledgeForm.setFieldValue(field, value)
    await saveKnowledgeRag({
      ...knowledgeForm.getFieldsValue(true),
      [field]: value,
    } as KnowledgeRagSettings)
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

  const resetGuardrailsToDefaults = async () => {
    guardrailForm.setFieldsValue(GUARDRAIL_SETTINGS_DEFAULTS)
    await saveGuardrails(GUARDRAIL_SETTINGS_DEFAULTS)
  }

  const resetGuardrailFieldToDefault = async (field: keyof GuardrailSettings) => {
    const value = GUARDRAIL_SETTINGS_DEFAULTS[field]
    guardrailForm.setFieldValue(field, value)
    await saveGuardrails({
      ...guardrailForm.getFieldsValue(true),
      [field]: value,
    } as GuardrailSettings)
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
    const current: ModelConfigResponse = models.data ?? {
      active_model_id: model.id,
      memory_model_id: null,
      eval_judge_model_id: null,
      models: [],
    }
    const previous = current.models.find((item) => item.id === model.id)
    const normalized: ModelConfigInput = {
      ...previous,
      ...model,
      name: model.name.trim(),
      model_id: model.model_id.trim(),
      base_url: (model.base_url ?? '').trim(),
      enabled: model.enabled ?? true,
    }
    const submitted = !previous || previous.provider !== model.provider ? omitProviderManagedFields(normalized) : normalized
    const next: ModelConfigInput[] = current.models.some((item) => item.id === submitted.id)
      ? current.models.map((item) => (item.id === submitted.id ? submitted : item))
      : [...current.models, submitted]
    setSaving(true)
    try {
      await persist({
        active_model_id: current.models.some((item) => item.id === current.active_model_id)
          ? current.active_model_id
          : submitted.id,
        memory_model_id: current.memory_model_id ?? null,
        eval_judge_model_id: current.eval_judge_model_id ?? null,
        models: next,
      })
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
      id: createModelId(),
      name: '',
      model_id: '',
      provider: 'openai-compatible',
      base_url: '',
      api_key: '',
      enabled: true,
    })
  }

  const setActiveModel = async (model: ModelConfig) => {
    const current = models.data
    if (!current || current.active_model_id === model.id) return
    setUpdatingId(model.id)
    try {
      await persist({
        ...current,
        active_model_id: model.id,
        memory_model_id: current.memory_model_id ?? null,
        eval_judge_model_id: current.eval_judge_model_id ?? null,
      })
      message.success(t('modelActivated', { name: model.name }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('modelActivateFailed'))
    } finally {
      setUpdatingId(null)
    }
  }

  const setMemoryModel = async (model: ModelConfig) => {
    const current = models.data
    if (!current) return
    const already = current.memory_model_id === model.id
    setUpdatingId(model.id)
    try {
      await persist({
        ...current,
        memory_model_id: already ? null : model.id,
        eval_judge_model_id: current.eval_judge_model_id ?? null,
      })
      message.success(already ? t('memoryModelCleared', { name: model.name }) : t('memoryModelActivated', { name: model.name }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('memoryModelActivateFailed'))
    } finally {
      setUpdatingId(null)
    }
  }

  const setEvalJudgeModel = async (model: ModelConfig) => {
    const current = models.data
    if (!current) return
    const already = current.eval_judge_model_id === model.id
    setUpdatingId(model.id)
    try {
      await persist({
        ...current,
        memory_model_id: current.memory_model_id ?? null,
        eval_judge_model_id: already ? null : model.id,
      })
      message.success(already ? t('evalJudgeModelCleared', { name: model.name }) : t('evalJudgeModelActivated', { name: model.name }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('evalJudgeModelActivateFailed'))
    } finally {
      setUpdatingId(null)
    }
  }

  const setEnabled = async (model: ModelConfig, enabled: boolean) => {
    const current = models.data
    if (!current) return
    setUpdatingId(model.id)
    try {
      await persist({
        ...current,
        memory_model_id: current.memory_model_id ?? null,
        eval_judge_model_id: current.eval_judge_model_id ?? null,
        models: current.models.map((item) => (item.id === model.id ? { ...item, enabled } : item)),
      })
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
    const remaining = current.models.filter((item) => item.id !== model.id)
    const nextActive =
      remaining.find((item) => item.id === current.active_model_id) ??
      remaining.find((item) => item.enabled && item.configured !== false) ??
      remaining.find((item) => item.enabled) ??
      remaining[0]
    const active_model_id = nextActive?.id ?? ''
    let memory_model_id = current.memory_model_id ?? null
    if (memory_model_id === model.id) {
      memory_model_id = null
    }
    let eval_judge_model_id = current.eval_judge_model_id ?? null
    if (eval_judge_model_id === model.id) {
      eval_judge_model_id = null
    }
    setUpdatingId(model.id)
    try {
      await persist({ active_model_id, memory_model_id, eval_judge_model_id, models: remaining })
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

  const hasModelConnections = (models.data?.models.length ?? 0) > 0
  const modelConnections = (
    <Table<ModelConfig>
      rowKey="id"
      dataSource={models.data?.models ?? []}
      loading={models.isLoading}
      locale={{
        emptyText: (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Flex vertical align="center" gap="small">
                <span>{t('noModelsConfigured')}</span>
                {canManageModels && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={addModel}>
                    {t('addModel')}
                  </Button>
                )}
              </Flex>
            }
          />
        ),
      }}
      scroll={{ x: 960 }}
      columns={[
        {
          title: t('colName'),
          dataIndex: 'name',
          width: 220,
          ellipsis: true,
          render: (value, row) => {
            const isActive = models.data?.active_model_id === row.id
            const isMemory = models.data?.memory_model_id === row.id
            const isEvalJudge = models.data?.eval_judge_model_id === row.id
            return (
              <Space wrap size={[4, 4]}>
                <strong>{value}</strong>
                {isActive && <Tag color="blue">{t('tagActive')}</Tag>}
                {isMemory && <Tag color="blue">{t('tagMemoryManager')}</Tag>}
                {isEvalJudge && <Tag color="blue">{t('tagEvalJudge')}</Tag>}
              </Space>
            )
          },
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
          render: (value, row) =>
            canManageModels ? (
              <Switch
                checked={value}
                loading={updatingId === row.id}
                onChange={(checked) => void setEnabled(row, checked)}
                aria-label={`${row.name} enabled`}
              />
            ) : (
              <Tag color={value ? 'success' : 'default'}>{value ? t('common:enabled') : t('common:disabled')}</Tag>
            ),
        },
        ...(canManageModels
          ? [
              {
                title: t('colActions'),
                width: 260,
                render: (_: unknown, row: ModelConfig) => {
                  const isActive = models.data?.active_model_id === row.id
                  const isMemory = models.data?.memory_model_id === row.id
                  const isEvalJudge = models.data?.eval_judge_model_id === row.id
                  const isOnlyModel = (models.data?.models.length ?? 0) === 1
                  const pinDisabled = !row.enabled || row.configured === false
                  return (
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
                        <Button
                          icon={<EditOutlined />}
                          aria-label={t('editModelNamed', { name: row.name })}
                          onClick={() => openEditor(row)}
                        />
                      </Tooltip>
                      <Tooltip title={isActive ? t('currentModel') : t('setCurrentModel')}>
                        <Button
                          icon={<CheckCircleOutlined />}
                          type={isActive ? 'primary' : 'default'}
                          ghost={isActive}
                          loading={updatingId === row.id}
                          aria-label={t('setCurrentModelNamed', { name: row.name })}
                          onClick={() => void setActiveModel(row)}
                        />
                      </Tooltip>
                      <Tooltip title={isMemory ? t('memoryModelCurrent') : t('setMemoryModel')}>
                        <Button
                          icon={<DatabaseOutlined />}
                          type={isMemory ? 'primary' : 'default'}
                          ghost={isMemory}
                          loading={updatingId === row.id}
                          disabled={pinDisabled}
                          aria-label={t('setMemoryModelNamed', { name: row.name })}
                          onClick={() => void setMemoryModel(row)}
                        />
                      </Tooltip>
                      <Tooltip title={isEvalJudge ? t('evalJudgeModelCurrent') : t('setEvalJudgeModel')}>
                        <Button
                          icon={<AuditOutlined />}
                          type={isEvalJudge ? 'primary' : 'default'}
                          ghost={isEvalJudge}
                          loading={updatingId === row.id}
                          disabled={pinDisabled}
                          aria-label={t('setEvalJudgeModelNamed', { name: row.name })}
                          onClick={() => void setEvalJudgeModel(row)}
                        />
                      </Tooltip>
                      <Tooltip title={t('deleteModel')}>
                        <Popconfirm
                          title={t('deleteModelConfirm', { name: row.name })}
                          description={
                            isActive ? (isOnlyModel ? t('deleteOnlyModelHint') : t('deleteActiveModelHint')) : undefined
                          }
                          okText={t('deleteModel')}
                          cancelText={t('common:cancel')}
                          okButtonProps={{ danger: true }}
                          onConfirm={() => void deleteModel(row)}
                        >
                          <Button
                            danger
                            icon={<DeleteOutlined />}
                            loading={updatingId === row.id}
                            aria-label={t('deleteModelNamed', { name: row.name })}
                          />
                        </Popconfirm>
                      </Tooltip>
                    </Space>
                  )
                },
              },
            ]
          : []),
      ]}
    />
  )

  type SettingRow = {
    key: string
    parameter: string
    description: string
  }

  type ChatField = keyof ChatSettings
  type ChatControl = 'switch' | 'number' | 'optional_number' | 'memory_mode'
  type ChatSettingRow = SettingRow & {
    field: ChatField
    control: ChatControl
    min?: number
    max?: number
  }
  type ChatSettingGroup = {
    key: string
    label: string
    description: string
    rows: ChatSettingRow[]
  }

  /** Grouped Chat knobs so the Settings table is scannable by concern. */
  const chatSettingGroups: ChatSettingGroup[] = [
    {
      key: 'privacy',
      label: t('chatGroupPrivacy'),
      description: t('chatGroupPrivacyDesc'),
      rows: [
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
      ],
    },
    {
      key: 'context',
      label: t('chatGroupContext'),
      description: t('chatGroupContextDesc'),
      rows: [
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
      ],
    },
    {
      key: 'tools',
      label: t('chatGroupTools'),
      description: t('chatGroupToolsDesc'),
      rows: [
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
      ],
    },
  ]

  /** Memory knobs live on their own Settings tab (not under Chat). */
  const memorySettingGroups: ChatSettingGroup[] = [
    {
      key: 'mode',
      label: t('memoryGroupMode'),
      description: t('memoryGroupModeDesc'),
      rows: [
        {
          key: 'memory_mode',
          field: 'memory_mode',
          parameter: t('memoryModeLabel'),
          description: t('memoryModeDesc'),
          control: 'memory_mode',
        },
        {
          key: 'memory_tool_content_enabled',
          field: 'memory_tool_content_enabled',
          parameter: t('memoryToolContentLabel'),
          description: t('memoryToolContentDesc'),
          control: 'switch',
        },
      ],
    },
    {
      key: 'inject',
      label: t('memoryGroupInject'),
      description: t('memoryGroupInjectDesc'),
      rows: [
        {
          key: 'memory_inject_enabled',
          field: 'memory_inject_enabled',
          parameter: t('memoryInjectEnabledLabel'),
          description: t('memoryInjectEnabledDesc'),
          control: 'switch',
        },
        {
          key: 'memory_inject_top_k',
          field: 'memory_inject_top_k',
          parameter: t('memoryInjectTopKLabel'),
          description: t('memoryInjectTopKDesc'),
          control: 'number',
          min: 1,
          max: 100,
        },
        {
          key: 'memory_inject_window_days',
          field: 'memory_inject_window_days',
          parameter: t('memoryInjectWindowLabel'),
          description: t('memoryInjectWindowDesc'),
          control: 'number',
          min: 0,
          max: 3650,
        },
        {
          key: 'memory_inject_dedupe_topics',
          field: 'memory_inject_dedupe_topics',
          parameter: t('memoryInjectDedupeLabel'),
          description: t('memoryInjectDedupeDesc'),
          control: 'switch',
        },
      ],
    },
    {
      key: 'prune',
      label: t('memoryGroupPrune'),
      description: t('memoryGroupPruneDesc'),
      rows: [
        {
          key: 'memory_prune_enabled',
          field: 'memory_prune_enabled',
          parameter: t('memoryPruneEnabledLabel'),
          description: t('memoryPruneEnabledDesc'),
          control: 'switch',
        },
        {
          key: 'memory_prune_retention_days',
          field: 'memory_prune_retention_days',
          parameter: t('memoryPruneRetentionLabel'),
          description: t('memoryPruneRetentionDesc'),
          control: 'number',
          min: 1,
          max: 3650,
        },
        {
          key: 'memory_prune_top_k',
          field: 'memory_prune_top_k',
          parameter: t('memoryPruneTopKLabel'),
          description: t('memoryPruneTopKDesc'),
          control: 'number',
          min: 1,
          max: 500,
        },
      ],
    },
  ]

  const MEMORY_FIELDS = new Set<ChatField>([
    'memory_mode',
    'memory_tool_content_enabled',
    'memory_prune_enabled',
    'memory_prune_retention_days',
    'memory_prune_top_k',
    'memory_inject_enabled',
    'memory_inject_top_k',
    'memory_inject_window_days',
    'memory_inject_dedupe_topics',
  ])

  const [chatForm] = Form.useForm<ChatSettings>()
  const [memoryForm] = Form.useForm<ChatSettings>()
  const [chatSaving, setChatSaving] = useState(false)
  const [memorySaving, setMemorySaving] = useState(false)
  useEffect(() => {
    if (chatSettings.data) {
      const normalized = normalizeChatSettings(chatSettings.data)
      chatForm.setFieldsValue(normalized)
      memoryForm.setFieldsValue(normalized)
    }
  }, [chatForm, memoryForm, chatSettings.data])

  const saveChatRuntime = async (values: ChatSettings) => {
    setChatSaving(true)
    try {
      const payload: Partial<ChatSettings> = {
        show_thought_chain: values.show_thought_chain,
        show_raw_reasoning: values.show_raw_reasoning,
        show_raw_tool_io: values.show_raw_tool_io,
        session_summaries_enabled: values.session_summaries_enabled,
        add_datetime_to_context: values.add_datetime_to_context,
        markdown: values.markdown,
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
      const normalized = normalizeChatSettings(next)
      chatForm.setFieldsValue(normalized)
      memoryForm.setFieldsValue(normalized)
      await client.invalidateQueries({ queryKey: ['settings', 'chat'] })
      message.success(t('chatSettingsSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('chatSettingsSaveFailed'))
    } finally {
      setChatSaving(false)
    }
  }

  const saveMemoryRuntime = async (values: ChatSettings) => {
    setMemorySaving(true)
    try {
      const mode = (values.memory_mode ?? 'automatic') as MemoryMode
      const payload: Partial<ChatSettings> = {
        memory_mode: mode,
        memory_tool_content_enabled: Boolean(values.memory_tool_content_enabled),
        memory_prune_enabled: Boolean(values.memory_prune_enabled),
        memory_prune_retention_days: Number(values.memory_prune_retention_days ?? 90),
        memory_prune_top_k: Number(values.memory_prune_top_k ?? 50),
        memory_inject_enabled: Boolean(values.memory_inject_enabled),
        memory_inject_top_k: Number(values.memory_inject_top_k ?? 12),
        memory_inject_window_days: Number(values.memory_inject_window_days ?? 90),
        memory_inject_dedupe_topics: Boolean(values.memory_inject_dedupe_topics),
      }
      const next = await saveChatSettings(payload)
      const normalized = normalizeChatSettings(next)
      chatForm.setFieldsValue(normalized)
      memoryForm.setFieldsValue(normalized)
      await client.invalidateQueries({ queryKey: ['settings', 'chat'] })
      message.success(t('memorySettingsSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('memorySettingsSaveFailed'))
    } finally {
      setMemorySaving(false)
    }
  }

  const resetChatToDefaults = async () => {
    const chatOnly: Partial<ChatSettings> = {
      show_thought_chain: CHAT_SETTINGS_DEFAULTS.show_thought_chain,
      show_raw_reasoning: CHAT_SETTINGS_DEFAULTS.show_raw_reasoning,
      show_raw_tool_io: CHAT_SETTINGS_DEFAULTS.show_raw_tool_io,
      session_summaries_enabled: CHAT_SETTINGS_DEFAULTS.session_summaries_enabled,
      add_datetime_to_context: CHAT_SETTINGS_DEFAULTS.add_datetime_to_context,
      markdown: CHAT_SETTINGS_DEFAULTS.markdown,
      num_history_runs: CHAT_SETTINGS_DEFAULTS.num_history_runs,
      max_tool_calls_from_history: CHAT_SETTINGS_DEFAULTS.max_tool_calls_from_history,
      default_tool_call_limit: CHAT_SETTINGS_DEFAULTS.default_tool_call_limit,
    }
    chatForm.setFieldsValue({ ...chatForm.getFieldsValue(true), ...chatOnly })
    await saveChatRuntime({ ...chatForm.getFieldsValue(true), ...chatOnly } as ChatSettings)
  }

  const resetMemoryToDefaults = async () => {
    const memoryOnly: Partial<ChatSettings> = {
      memory_mode: CHAT_SETTINGS_DEFAULTS.memory_mode,
      memory_tool_content_enabled: CHAT_SETTINGS_DEFAULTS.memory_tool_content_enabled,
      memory_prune_enabled: CHAT_SETTINGS_DEFAULTS.memory_prune_enabled,
      memory_prune_retention_days: CHAT_SETTINGS_DEFAULTS.memory_prune_retention_days,
      memory_prune_top_k: CHAT_SETTINGS_DEFAULTS.memory_prune_top_k,
      memory_inject_enabled: CHAT_SETTINGS_DEFAULTS.memory_inject_enabled,
      memory_inject_top_k: CHAT_SETTINGS_DEFAULTS.memory_inject_top_k,
      memory_inject_window_days: CHAT_SETTINGS_DEFAULTS.memory_inject_window_days,
      memory_inject_dedupe_topics: CHAT_SETTINGS_DEFAULTS.memory_inject_dedupe_topics,
    }
    memoryForm.setFieldsValue({ ...memoryForm.getFieldsValue(true), ...memoryOnly })
    await saveMemoryRuntime({ ...memoryForm.getFieldsValue(true), ...memoryOnly } as ChatSettings)
  }

  const resetChatFieldToDefault = async (field: ChatField) => {
    if (MEMORY_FIELDS.has(field)) {
      const value = CHAT_SETTINGS_DEFAULTS[field]
      memoryForm.setFieldValue(field, value)
      await saveMemoryRuntime({
        ...memoryForm.getFieldsValue(true),
        [field]: value,
      } as ChatSettings)
      return
    }
    const value = CHAT_SETTINGS_DEFAULTS[field]
    chatForm.setFieldValue(field, value)
    await saveChatRuntime({
      ...chatForm.getFieldsValue(true),
      [field]: value,
    } as ChatSettings)
  }

  const renderChatSettingTable = (rows: ChatSettingRow[], options: { saving: boolean; onResetField: (field: ChatField) => void }) => {
    const { saving: isSaving, onResetField } = options
    return (
      <Table<ChatSettingRow>
        rowKey="key"
        size="middle"
        loading={chatSettings.isLoading}
        pagination={false}
        tableLayout="auto"
        style={{ width: '100%' }}
        dataSource={rows}
        columns={[
          {
            title: t('colParameter'),
            dataIndex: 'parameter',
            width: '22%',
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
            width: 260,
            render: (_field, row) => {
              if (row.control === 'memory_mode') {
                return (
                  <Form.Item name="memory_mode" noStyle>
                    <Radio.Group
                      optionType="button"
                      buttonStyle="solid"
                      size="small"
                      aria-label={String(row.field)}
                      options={[
                        { value: 'off', label: t('memoryModeOff') },
                        { value: 'automatic', label: t('memoryModeAutomatic') },
                        { value: 'agentic', label: t('memoryModeAgentic') },
                      ]}
                    />
                  </Form.Item>
                )
              }
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
          {
            title: t('colReset'),
            key: 'reset',
            width: 88,
            align: 'center',
            render: (_value, row) => (
              <div className="settings-param-row-reset">
                <Tooltip title={t('resetFieldDefault')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<UndoOutlined />}
                    aria-label={t('resetFieldDefaultNamed', { name: row.parameter })}
                    disabled={chatSettings.isLoading || isSaving}
                    onClick={() => onResetField(row.field)}
                  />
                </Tooltip>
              </div>
            ),
          },
        ]}
      />
    )
  }

  const chatControls = (
    <div className="settings-param-panel settings-chat-panel">
      <Typography.Paragraph type="secondary">{t('chatRuntimeHint')}</Typography.Paragraph>
      <Form
        form={chatForm}
        layout="vertical"
        initialValues={CHAT_SETTINGS_DEFAULTS}
        onFinish={(values) => void saveChatRuntime(values)}
        disabled={chatSettings.isLoading || chatSaving}
      >
        <Collapse
          className="settings-chat-groups"
          defaultActiveKey={['privacy', 'context']}
          items={chatSettingGroups.map((group) => ({
            key: group.key,
            label: (
              <div className="settings-chat-group-label">
                <Typography.Text strong>{group.label}</Typography.Text>
                <Typography.Text type="secondary" className="settings-chat-group-count">
                  {t('chatGroupCount', { count: group.rows.length })}
                </Typography.Text>
              </div>
            ),
            children: (
              <div className="settings-chat-group-body">
                <Typography.Paragraph type="secondary" className="settings-chat-group-desc">
                  {group.description}
                </Typography.Paragraph>
                {renderChatSettingTable(group.rows, {
                  saving: chatSaving,
                  onResetField: (field) => void resetChatFieldToDefault(field),
                })}
              </div>
            ),
          }))}
        />
        <div className="settings-param-actions">
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={chatSaving}>
              {t('chatSettingsSave')}
            </Button>
            <Popconfirm
              title={t('resetDefaultsConfirm')}
              description={t('resetDefaultsConfirmDesc')}
              okText={t('resetDefaults')}
              cancelText={t('common:cancel')}
              onConfirm={() => void resetChatToDefaults()}
              disabled={chatSettings.isLoading || chatSaving}
            >
              <Button icon={<UndoOutlined />} loading={chatSaving} disabled={chatSettings.isLoading}>
                {t('resetDefaults')}
              </Button>
            </Popconfirm>
          </Space>
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

  const memoryControls = (
    <div className="settings-param-panel settings-chat-panel settings-memory-panel">
      <Typography.Paragraph type="secondary">{t('memorySettingsHint')}</Typography.Paragraph>
      <Form
        form={memoryForm}
        layout="vertical"
        initialValues={CHAT_SETTINGS_DEFAULTS}
        onFinish={(values) => void saveMemoryRuntime({ ...memoryForm.getFieldsValue(true), ...values })}
        disabled={chatSettings.isLoading || memorySaving}
      >
        <Collapse
          className="settings-chat-groups"
          defaultActiveKey={['mode', 'inject']}
          items={memorySettingGroups.map((group) => ({
            key: group.key,
            label: (
              <div className="settings-chat-group-label">
                <Typography.Text strong>{group.label}</Typography.Text>
                <Typography.Text type="secondary" className="settings-chat-group-count">
                  {t('chatGroupCount', { count: group.rows.length })}
                </Typography.Text>
              </div>
            ),
            children: (
              <div className="settings-chat-group-body">
                <Typography.Paragraph type="secondary" className="settings-chat-group-desc">
                  {group.description}
                </Typography.Paragraph>
                {renderChatSettingTable(group.rows, {
                  saving: memorySaving,
                  onResetField: (field) => void resetChatFieldToDefault(field),
                })}
              </div>
            ),
          }))}
        />
        <div className="settings-param-actions">
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={memorySaving}>
              {t('memorySettingsSave')}
            </Button>
            <Popconfirm
              title={t('resetDefaultsConfirm')}
              description={t('resetDefaultsConfirmDesc')}
              okText={t('resetDefaults')}
              cancelText={t('common:cancel')}
              onConfirm={() => void resetMemoryToDefaults()}
              disabled={chatSettings.isLoading || memorySaving}
            >
              <Button icon={<UndoOutlined />} loading={memorySaving} disabled={chatSettings.isLoading}>
                {t('resetDefaults')}
              </Button>
            </Popconfirm>
          </Space>
        </div>
      </Form>
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
            render: (_value: string | undefined, row) => (
              <Select<UserRole>
                size="small"
                style={{ width: '100%' }}
                value={roleOf(row)}
                options={roleOptions}
                loading={rolePresetsQuery.isLoading || roleUpdatingId === row.id}
                disabled={row.id === currentUser.data?.id}
                title={row.id === currentUser.data?.id ? t('cannotChangeOwnRole') : undefined}
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

  const knowledgeSettingRows: Array<SettingRow & { field: KnowledgeField; control: 'select' | 'number' | 'switch' | 'text' | 'readonly' }> =
    [
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
        initialValues={GUARDRAIL_SETTINGS_DEFAULTS}
        onFinish={(values) => void saveGuardrails(values)}
        disabled={guardrailSettings.isLoading || guardrailSaving}
      >
        <Table<(typeof guardrailSettingRows)[number]>
          rowKey="key"
          size="middle"
          loading={guardrailSettings.isLoading}
          pagination={false}
          tableLayout="auto"
          style={{ width: '100%' }}
          dataSource={guardrailSettingRows}
          columns={[
            {
              title: t('colParameter'),
              dataIndex: 'parameter',
              width: '22%',
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
              width: 140,
              render: (_field, row) => (
                <Form.Item name={row.field} noStyle valuePropName="checked">
                  <Switch />
                </Form.Item>
              ),
            },
            {
              title: t('colReset'),
              key: 'reset',
              width: 88,
              align: 'center',
              render: (_value, row) => (
                <div className="settings-param-row-reset">
                  <Tooltip title={t('resetFieldDefault')}>
                    <Button
                      type="text"
                      size="small"
                      icon={<UndoOutlined />}
                      aria-label={t('resetFieldDefaultNamed', { name: row.parameter })}
                      disabled={guardrailSettings.isLoading || guardrailSaving}
                      onClick={() => void resetGuardrailFieldToDefault(row.field)}
                    />
                  </Tooltip>
                </div>
              ),
            },
          ]}
        />
        <div className="settings-param-actions">
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={guardrailSaving}>
              {t('guardrailsSave')}
            </Button>
            <Popconfirm
              title={t('resetDefaultsConfirm')}
              description={t('resetDefaultsConfirmDesc')}
              okText={t('resetDefaults')}
              cancelText={t('common:cancel')}
              onConfirm={() => void resetGuardrailsToDefaults()}
              disabled={guardrailSettings.isLoading || guardrailSaving}
            >
              <Button icon={<UndoOutlined />} loading={guardrailSaving} disabled={guardrailSettings.isLoading}>
                {t('resetDefaults')}
              </Button>
            </Popconfirm>
          </Space>
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
        initialValues={KNOWLEDGE_RAG_SETTINGS_DEFAULTS}
        onFinish={(values) => void saveKnowledgeRag(values)}
        disabled={knowledgeRagSettings.isLoading || knowledgeSaving}
      >
        <Table<(typeof knowledgeSettingRows)[number]>
          rowKey="key"
          size="middle"
          loading={knowledgeRagSettings.isLoading}
          pagination={false}
          tableLayout="auto"
          style={{ width: '100%' }}
          dataSource={knowledgeSettingRows}
          columns={[
            {
              title: t('colParameter'),
              dataIndex: 'parameter',
              width: '22%',
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
              width: 240,
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
                  return <Typography.Text type="secondary">{knowledgeRagSettings.data?.rerank_model || '—'}</Typography.Text>
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
            {
              title: t('colReset'),
              key: 'reset',
              width: 88,
              align: 'center',
              render: (_value, row) => {
                if (row.control === 'readonly') {
                  return null
                }
                return (
                  <div className="settings-param-row-reset">
                    <Tooltip title={t('resetFieldDefault')}>
                      <Button
                        type="text"
                        size="small"
                        icon={<UndoOutlined />}
                        aria-label={t('resetFieldDefaultNamed', { name: row.parameter })}
                        disabled={knowledgeRagSettings.isLoading || knowledgeSaving}
                        onClick={() => void resetKnowledgeFieldToDefault(row.field as Exclude<keyof KnowledgeRagSettings, 'rerank_model'>)}
                      />
                    </Tooltip>
                  </div>
                )
              },
            },
          ]}
        />
        <div className="settings-param-actions">
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={knowledgeSaving}>
              {t('knowledgeRagSave')}
            </Button>
            <Popconfirm
              title={t('resetDefaultsConfirm')}
              description={t('resetDefaultsConfirmDesc')}
              okText={t('resetDefaults')}
              cancelText={t('common:cancel')}
              onConfirm={() => void resetKnowledgeToDefaults()}
              disabled={knowledgeRagSettings.isLoading || knowledgeSaving}
            >
              <Button icon={<UndoOutlined />} loading={knowledgeSaving} disabled={knowledgeRagSettings.isLoading}>
                {t('resetDefaults')}
              </Button>
            </Popconfirm>
          </Space>
        </div>
      </Form>
    </div>
  )

  const cveSourceControls = (
    <div className="settings-param-panel settings-cve-sources-panel">
      <Typography.Paragraph type="secondary">{t('cveSourcesHint')}</Typography.Paragraph>
      <Table<CveSourceSetting>
        rowKey="source"
        size="middle"
        loading={cveSourceSettings.isLoading}
        pagination={false}
        tableLayout="auto"
        style={{ width: '100%' }}
        dataSource={cveSourceSettings.data?.sources ?? []}
        columns={[
          {
            title: t('colName'),
            dataIndex: 'source',
            width: '28%',
            render: (source: string) => (
              <Flex vertical gap={0}>
                <Typography.Text strong>{cveSourceLabel(source)}</Typography.Text>
                <Typography.Text type="secondary">{source}</Typography.Text>
              </Flex>
            ),
          },
          {
            title: t('colDescription'),
            dataIndex: 'source',
            render: (source: string) => (
              <Typography.Text type="secondary" className="settings-param-description">
                {cveSourceDescription(source)}
              </Typography.Text>
            ),
          },
          {
            title: t('colEnabled'),
            dataIndex: 'enabled',
            width: 140,
            render: (enabled: boolean, row) => (
              <Switch
                checked={cveSourceEnabled[row.source] ?? enabled}
                disabled={cveSourceSettings.isLoading || cveSourceSaving}
                aria-label={t('cveSourceEnabledNamed', { name: cveSourceLabel(row.source) })}
                onChange={(checked) => setCveSourceEnabled((current) => ({ ...current, [row.source]: checked }))}
              />
            ),
          },
        ]}
      />
      <div className="settings-param-actions">
        <Button
          type="primary"
          loading={cveSourceSaving}
          disabled={cveSourceSettings.isLoading || !cveSourceSettings.data?.sources.length}
          onClick={() => void saveCveSources()}
        >
          {t('cveSourcesSave')}
        </Button>
      </div>
    </div>
  )

  const notificationControls = (
    <div className="settings-param-block">
      <Typography.Paragraph type="secondary">{t('notificationIntro')}</Typography.Paragraph>
      <Typography.Paragraph type="secondary">
        {notificationSettings.data?.feishu_webhook_configured
          ? t('feishuConfigured', { hint: notificationSettings.data.feishu_webhook_hint || '…' })
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
            <Button danger loading={notificationSaving} disabled={!notificationSettings.data?.feishu_webhook_configured}>
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
            activeTab === 'models' && canManageModels && hasModelConnections ? (
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
                  { key: 'memory', label: t('memorySettingsTab'), children: memoryControls },
                  { key: 'guardrails', label: t('guardrailsTab'), children: guardrailControls },
                  { key: 'knowledge', label: t('knowledgeRagTab'), children: knowledgeControls },
                  { key: 'cve-sources', label: t('cveSourcesTab'), children: cveSourceControls },
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
