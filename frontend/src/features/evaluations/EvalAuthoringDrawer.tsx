import { useMemo } from 'react'
import { Alert, Button, Divider, Drawer, Form, Input, InputNumber, Select, Space, Switch, Typography } from 'antd'

import {
  DEFAULT_EVAL_PERFORMANCE_CONFIG,
  normalizeExpectedToolCallArguments,
  type EvalCase,
  type EvalCaseWrite,
  type EvalTarget,
  type EvalTargetOption,
  type EvalSuiteWrite,
  type EvalType,
  type Suite,
} from './api'

type TFn = (key: string, options?: Record<string, unknown>) => string

type SuiteFormValues = Omit<EvalSuiteWrite, 'target'> & { target_key: string }

type CaseFormValues = Omit<EvalCaseWrite, 'expected_tool_call_arguments' | 'metadata' | 'performance_config'> & {
  expected_tool_call_arguments_json: string
  profile: 'full' | 'tools_off'
  performance_warmup_runs: number
  performance_num_iterations: number
  performance_measure_runtime: boolean
  performance_measure_memory: boolean
}

const CASE_TYPE_OPTIONS: Array<{ value: EvalType; labelKey: string }> = [
  { value: 'agent_as_judge', labelKey: 'checkJudge' },
  { value: 'accuracy', labelKey: 'checkAccuracy' },
  { value: 'reliability', labelKey: 'checkReliability' },
  { value: 'performance', labelKey: 'checkPerformance' },
]

const targetKey = (target: EvalTarget): string => `${target.kind}:${target.id}`

const suiteValues = (suite?: Suite): SuiteFormValues => ({
  name: suite?.name ?? '',
  description: suite?.description ?? '',
  target_key: suite ? targetKey(suite.target) : '',
  enabled: suite?.enabled ?? true,
  tags: suite?.tags ?? [],
})

const asIntegerAtLeast = (value: unknown, minimum: number, fallback: number): number => {
  if (typeof value === 'number' && Number.isInteger(value) && value >= minimum) {
    return value
  }
  return fallback
}

const formatToolArgumentContract = (value: Record<string, unknown> | undefined): string => {
  if (!value || !Object.keys(value).length) return ''
  return JSON.stringify(value, null, 2)
}

const parseToolArgumentContract = (value: unknown): Record<string, unknown> => {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) return {}
  return normalizeExpectedToolCallArguments(JSON.parse(text), 'expected_tool_call_arguments')
}

const caseValues = (item: EvalCase | undefined): CaseFormValues => {
  const metadata = item?.metadata ?? {}
  const performance = item?.performance_config ?? DEFAULT_EVAL_PERFORMANCE_CONFIG
  const profile = metadata.profile === 'tools_off' ? 'tools_off' : 'full'
  return {
    suite_id: item?.suite_id ?? '',
    name: item?.name ?? '',
    description: item?.description ?? '',
    input: item?.input ?? '',
    expected_output: item?.expected_output ?? '',
    criteria: item?.criteria ?? '',
    judge_mode: item?.judge_mode ?? 'binary',
    additional_guidelines: item?.additional_guidelines ?? [],
    threshold: item?.threshold ?? 7,
    eval_types: item?.eval_types?.length ? item.eval_types : ['agent_as_judge'],
    expected_tool_calls: item?.expected_tool_calls ?? [],
    expected_tool_call_arguments_json: formatToolArgumentContract(item?.expected_tool_call_arguments),
    // Match Agno Case's default. A safety Pack's serialized Case can still
    // opt into strict no-additional-tool behavior explicitly.
    allow_additional_tool_calls: item?.allow_additional_tool_calls ?? true,
    timeout_seconds: item?.timeout_seconds ?? null,
    tags: item?.tags ?? [],
    enabled: item?.enabled ?? true,
    profile,
    performance_warmup_runs: asIntegerAtLeast(performance.warmup_runs, 0, 1),
    performance_num_iterations: asIntegerAtLeast(performance.num_iterations, 1, 3),
    performance_measure_runtime: performance.measure_runtime !== false,
    performance_measure_memory: performance.measure_memory === true,
  }
}

export const EvalSuiteAuthoringDrawer = ({
  open,
  suite,
  targets,
  targetsLoading,
  saving,
  t,
  onClose,
  onSubmit,
}: {
  open: boolean
  suite?: Suite
  targets: EvalTargetOption[]
  targetsLoading?: boolean
  saving: boolean
  t: TFn
  onClose: () => void
  onSubmit: (value: EvalSuiteWrite) => Promise<void>
}) => {
  const [form] = Form.useForm<SuiteFormValues>()
  const initialValues = useMemo(() => suiteValues(suite), [suite])
  const isEdit = Boolean(suite)

  return (
    <Drawer
      destroyOnHidden
      title={isEdit ? t('editSuite') : t('newSuite')}
      size={520}
      open={open}
      loading={saving}
      mask={{ closable: !saving }}
      keyboard={!saving}
      onClose={() => {
        if (!saving) onClose()
      }}
      footer={
        <Space>
          <Button disabled={saving} onClick={onClose}>
            {t('common:cancel')}
          </Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            {isEdit ? t('saveSuite') : t('createSuite')}
          </Button>
        </Space>
      }
    >
      <Alert showIcon type="info" style={{ marginBottom: 20 }} title={t('suiteAuthoringHint')} />
      <Form<SuiteFormValues>
        key={suite?.id ?? 'new'}
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={async (values) => {
          const selected = targets.find((target) => targetKey(target) === values.target_key)
          if (!selected) {
            form.setFields([{ name: 'target_key', errors: [t('targetRequired')] }])
            return
          }
          await onSubmit({
            name: values.name,
            description: values.description,
            target: { kind: selected.kind, id: selected.id },
            enabled: values.enabled,
            tags: values.tags,
          })
        }}
      >
        <Form.Item name="name" label={t('suiteName')} rules={[{ required: true, whitespace: true, message: t('nameRequired') }]}>
          <Input maxLength={160} />
        </Form.Item>
        <Form.Item name="description" label={t('suiteDescription')}>
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} maxLength={2000} />
        </Form.Item>
        <Form.Item
          name="target_key"
          label={t('target')}
          extra={isEdit ? t('targetImmutableHint') : t('targetHint')}
          rules={[{ required: true, message: t('targetRequired') }]}
        >
          <Select
            showSearch={{ optionFilterProp: 'label' }}
            loading={targetsLoading}
            disabled={isEdit || targetsLoading}
            options={targets.map((target) => ({
              value: targetKey(target),
              label: `${target.name} · ${target.kind === 'team' ? t('targetTeam') : t('targetAgent')}`,
              disabled: !target.available,
              title: target.unavailable_reason || target.description,
            }))}
          />
        </Form.Item>
        <Form.Item name="tags" label={t('suiteTags')}>
          <Select mode="tags" tokenSeparators={[',']} placeholder={t('tagsPlaceholder')} />
        </Form.Item>
        <Form.Item name="enabled" label={t('enabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Drawer>
  )
}

export const EvalCaseAuthoringDrawer = ({
  open,
  suiteId,
  suiteTarget,
  caseItem,
  saving,
  t,
  onClose,
  onSubmit,
}: {
  open: boolean
  suiteId: string
  suiteTarget?: EvalTarget
  caseItem?: EvalCase
  saving: boolean
  t: TFn
  onClose: () => void
  onSubmit: (value: EvalCaseWrite) => Promise<void>
}) => {
  const [form] = Form.useForm<CaseFormValues>()
  const initialValues = useMemo(() => ({ ...caseValues(caseItem), suite_id: caseItem?.suite_id ?? suiteId }), [caseItem, suiteId])
  const isEdit = Boolean(caseItem)

  const submit = async (values: CaseFormValues) => {
    const evalTypes = values.eval_types ?? []
    if (evalTypes.includes('agent_as_judge') && !values.criteria.trim()) {
      form.setFields([{ name: 'criteria', errors: [t('judgeCriteriaRequired')] }])
      return
    }
    if (evalTypes.includes('accuracy') && !values.expected_output.trim()) {
      form.setFields([{ name: 'expected_output', errors: [t('expectedOutputRequired')] }])
      return
    }
    const expectedToolCalls = values.expected_tool_calls ?? []
    if (evalTypes.includes('reliability') && !expectedToolCalls.length) {
      form.setFields([{ name: 'expected_tool_calls', errors: [t('reliabilityToolCallsRequired')] }])
      return
    }
    let expectedToolCallArguments: Record<string, unknown>
    try {
      expectedToolCallArguments = parseToolArgumentContract(values.expected_tool_call_arguments_json)
    } catch {
      form.setFields([{ name: 'expected_tool_call_arguments_json', errors: [t('expectedToolCallArgumentsInvalid')] }])
      return
    }
    const expectedTools = new Set(expectedToolCalls.map((name) => name.trim()).filter(Boolean))
    if (Object.keys(expectedToolCallArguments).some((toolName) => !expectedTools.has(toolName))) {
      form.setFields([{ name: 'expected_tool_call_arguments_json', errors: [t('toolArgumentsMustMatchCalls')] }])
      return
    }
    const metadata = {
      ...caseItem?.metadata,
      profile: values.profile,
    }
    const performanceConfig = {
      warmup_runs: values.performance_warmup_runs,
      num_iterations: values.performance_num_iterations,
      measure_runtime: values.performance_measure_runtime,
      measure_memory: values.performance_measure_memory,
    }
    await onSubmit({
      suite_id: values.suite_id,
      name: values.name,
      description: values.description,
      input: values.input,
      expected_output: values.expected_output,
      criteria: values.criteria,
      judge_mode: values.judge_mode,
      additional_guidelines: values.additional_guidelines,
      threshold: values.threshold,
      eval_types: values.eval_types,
      expected_tool_calls: expectedToolCalls,
      expected_tool_call_arguments: expectedToolCallArguments,
      allow_additional_tool_calls: values.allow_additional_tool_calls,
      performance_config: performanceConfig,
      timeout_seconds: values.timeout_seconds,
      metadata,
      tags: values.tags,
      enabled: values.enabled,
    })
  }

  return (
    <Drawer
      destroyOnHidden
      title={isEdit ? t('editCase') : t('newCase')}
      size={640}
      open={open}
      loading={saving}
      mask={{ closable: !saving }}
      keyboard={!saving}
      onClose={() => {
        if (!saving) onClose()
      }}
      footer={
        <Space>
          <Button disabled={saving} onClick={onClose}>
            {t('common:cancel')}
          </Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            {isEdit ? t('saveCase') : t('createCase')}
          </Button>
        </Space>
      }
    >
      <Alert showIcon type="info" style={{ marginBottom: 20 }} title={t('caseAuthoringHint')} />
      <Form<CaseFormValues>
        key={caseItem?.id ?? `new-${suiteId}`}
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={submit}
      >
        <Form.Item name="suite_id" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="name" label={t('caseName')} rules={[{ required: true, whitespace: true, message: t('nameRequired') }]}>
          <Input maxLength={160} />
        </Form.Item>
        <Form.Item name="description" label={t('caseDescription')}>
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} maxLength={2000} />
        </Form.Item>
        <Form.Item name="input" label={t('caseInput')} rules={[{ required: true, whitespace: true, message: t('inputRequired') }]}>
          <Input.TextArea autoSize={{ minRows: 4, maxRows: 10 }} />
        </Form.Item>
        <Divider plain titlePlacement="start">
          {t('caseChecks')}
        </Divider>
        <Form.Item name="eval_types" label={t('evalTypes')} rules={[{ required: true, message: t('evalTypeRequired') }]}>
          <Select mode="multiple" options={CASE_TYPE_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }))} />
        </Form.Item>
        <Form.Item name="criteria" label={t('criteria')} extra={t('criteriaHint')}>
          <Input.TextArea autoSize={{ minRows: 3, maxRows: 7 }} />
        </Form.Item>
        <Form.Item name="additional_guidelines" label={t('additionalGuidelines')} extra={t('additionalGuidelinesHint')}>
          <Select mode="tags" tokenSeparators={[',']} maxCount={20} placeholder={t('additionalGuidelinesPlaceholder')} />
        </Form.Item>
        <Form.Item name="expected_output" label={t('expectedOutput')} extra={t('expectedOutputHint')}>
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} />
        </Form.Item>
        <Space size={16} wrap align="start">
          <Form.Item name="judge_mode" label={t('judgeMode')}>
            <Select
              style={{ width: 180 }}
              options={[
                { value: 'binary', label: t('judgeModeBinary') },
                { value: 'numeric', label: t('judgeModeNumeric') },
              ]}
            />
          </Form.Item>
          <Form.Item name="threshold" label={t('threshold')} extra={t('thresholdHint')}>
            <InputNumber min={1} max={10} precision={0} style={{ width: 110 }} />
          </Form.Item>
          <Form.Item name="timeout_seconds" label={t('caseTimeout')} extra={t('caseTimeoutHint')}>
            <InputNumber min={1} max={3600} precision={0} placeholder={t('useSuiteDefault')} style={{ width: 150 }} />
          </Form.Item>
        </Space>
        <Divider plain titlePlacement="start">
          {t('toolContract')}
        </Divider>
        <Form.Item name="expected_tool_calls" label={t('expectedToolCalls')} extra={t('expectedToolCallsHint')}>
          <Select mode="tags" tokenSeparators={[',']} placeholder={t('tagsPlaceholder')} />
        </Form.Item>
        <Form.Item
          name="expected_tool_call_arguments_json"
          label={t('expectedToolCallArguments')}
          extra={t('expectedToolCallArgumentsHint')}
          rules={[
            {
              validator: (_, value) => {
                try {
                  parseToolArgumentContract(value)
                  return Promise.resolve()
                } catch {
                  return Promise.reject(new Error(t('expectedToolCallArgumentsInvalid')))
                }
              },
            },
          ]}
        >
          <Input.TextArea
            autoSize={{ minRows: 4, maxRows: 10 }}
            maxLength={32000}
            placeholder={t('expectedToolCallArgumentsPlaceholder')}
          />
        </Form.Item>
        <Form.Item name="allow_additional_tool_calls" label={t('allowAdditionalToolCalls')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Divider plain titlePlacement="start">
          {t('performanceOptions')}
        </Divider>
        <Space size={16} wrap align="start">
          <Form.Item name="performance_warmup_runs" label={t('performanceWarmup')}>
            <InputNumber min={0} max={100} precision={0} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="performance_num_iterations" label={t('performanceIterations')}>
            <InputNumber min={1} max={100} precision={0} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="performance_measure_runtime" label={t('performanceRuntime')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="performance_measure_memory" label={t('performanceMemory')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Space>
        <Divider plain titlePlacement="start">
          {t('caseExecution')}
        </Divider>
        {suiteTarget ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
            {t('caseTargetInherited', {
              target: `${suiteTarget.kind === 'team' ? t('targetTeam') : t('targetAgent')}: ${suiteTarget.id}`,
            })}
          </Typography.Paragraph>
        ) : null}
        <Form.Item name="profile" label={t('runProfile')}>
          <Select
            options={[
              { value: 'full', label: t('profileFull') },
              { value: 'tools_off', label: t('profileToolsOff') },
            ]}
          />
        </Form.Item>
        <Form.Item name="tags" label={t('caseTags')}>
          <Select mode="tags" tokenSeparators={[',']} placeholder={t('tagsPlaceholder')} />
        </Form.Item>
        <Form.Item name="enabled" label={t('enabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          {t('caseAuthoringPrivacyHint')}
        </Typography.Paragraph>
      </Form>
    </Drawer>
  )
}
