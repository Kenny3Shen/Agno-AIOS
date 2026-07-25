import { useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  Popconfirm,
  Progress,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { hasScope } from '@/shared/auth/permissions'
import {
  caseInputShouldMask,
  caseIsBenign,
  caseLayer,
  cancelSuiteRun,
  createCase,
  createSuite,
  deleteCase,
  deleteSuite,
  deltaIsImprovement,
  diffSafetyMetrics,
  exportSuiteRunReport,
  formatJudgeIdShort,
  formatMetricDelta,
  formatSafetyRate,
  formatSafetySummaryLine,
  getImportedPackIdentity,
  importPack,
  isActiveSuiteRun,
  isCancellableSuiteRunStatus,
  isSafetySuite,
  listCases,
  listFailures,
  listPacks,
  listEvalTargets,
  listRuns,
  listSuiteRunCaseRuns,
  listSuiteRuns,
  listSuites,
  maskSensitiveInput,
  pickLatestSafetyRun,
  replay,
  removePack,
  runCase,
  runSuite,
  safetyRateTone,
  suiteRunStatusColor,
  toneToCssColor,
  updateCaseTags,
  updateCase,
  updateSuite,
  type EvalCase,
  type EvalCaseWrite,
  type EvalPack,
  type EvalSuiteUpdate,
  type EvalSuiteWrite,
  type EvalRun,
  type SafetySummary,
  type Suite,
  type SuiteCaseResultLite,
  type SuiteRun,
  type SuiteRunReport,
} from './api'
import { EvalCaseAuthoringDrawer, EvalSuiteAuthoringDrawer } from './EvalAuthoringDrawer'
import { compactId, compareTimestamp, formatDate } from '@/shared/lib/format'
import { useTranslation } from 'react-i18next'

type TFn = (key: string, options?: Record<string, unknown>) => string

const EMPTY_CASE_ROWS: EvalCase[] = []

const MetricLabel = ({ label, tip }: { label: string; tip: string }) => (
  <Tooltip title={tip}>
    <Space size={4} style={{ cursor: 'help' }}>
      <span>{label}</span>
      <QuestionCircleOutlined style={{ fontSize: 12, opacity: 0.55 }} />
    </Space>
  </Tooltip>
)

const metricTitle = (label: string, tip: string): ReactNode => <MetricLabel label={label} tip={tip} />

const RateValue = ({ value, mode }: { value: number | null | undefined; mode: 'lowerIsBetter' | 'higherIsBetter' }) => {
  const text = formatSafetyRate(value)
  const color = toneToCssColor(safetyRateTone(value, mode))
  return <span style={color ? { color, fontWeight: 600 } : undefined}>{text}</span>
}

const formatCaseDuration = (value: number | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${value.toFixed(value >= 10 ? 1 : 2)} s`
}

const formatMemoryMib = (value: number): string => `${value.toFixed(value >= 10 ? 1 : 2)} MiB`

const formatPerformanceEvidence = (value: SuiteCaseResultLite['performance']): string => {
  if (!value) return '—'
  const metrics: string[] = []
  if (value.runtime_seconds) {
    metrics.push(`runtime p95 ${formatCaseDuration(value.runtime_seconds.p95)} · avg ${formatCaseDuration(value.runtime_seconds.avg)}`)
  }
  if (value.memory_mib) {
    metrics.push(`memory p95 ${formatMemoryMib(value.memory_mib.p95)} · avg ${formatMemoryMib(value.memory_mib.avg)}`)
  }
  return metrics.join(' | ') || '—'
}

const formatEvalScore = (value: number | undefined): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${Number.isInteger(value) ? value : value.toFixed(1)}/10`
}

const suiteRunProgress = (run: SuiteRun): { completed: number; total: number } => {
  const total = Math.max(0, run.summary.total ?? run.summary.selected_cases ?? 0)
  const completed = Math.max(
    0,
    run.summary.completed_cases ??
      ((run.summary.passed ?? 0) +
        (run.summary.failed ?? 0) +
        (run.summary.errored ?? 0) +
        (run.summary.skipped ?? 0) +
        (run.summary.cancelled ?? 0))
  )
  return { completed, total }
}

const formatReliabilityEvidence = (value: SuiteCaseResultLite['reliability_evidence'], t: TFn): string => {
  if (!value) return '—'
  const entries: Array<[string, string[]]> = [
    [t('reliabilityUnexpectedTools'), value.failed_tool_calls],
    [t('reliabilityMissingTools'), value.missing_tool_calls],
    [t('reliabilityArgumentMismatch'), value.failed_argument_checks],
    [t('reliabilityAdditionalTools'), value.additional_tool_calls],
    [t('reliabilityPassedTools'), value.passed_tool_calls],
    [t('reliabilityPassedArguments'), value.passed_argument_checks],
  ]
  const lines = entries.filter(([, items]) => items.length).map(([label, items]) => `${label}: ${items.join(', ')}`)
  return lines.join(' · ') || '—'
}

const downloadSuiteRunReport = (report: SuiteRunReport) => {
  const safeId = report.suite_run.id.replace(/[^a-zA-Z0-9._-]+/g, '_') || 'suite-run'
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `eval-suite-${safeId}.json`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

const RunTable = ({
  rows,
  loading,
  pagination,
  onReplay,
  t,
}: {
  rows: EvalRun[]
  loading?: boolean
  pagination?:
    | false
    | {
        current: number
        pageSize: number
        total: number
        onChange: (page: number) => void
      }
  onReplay?: (caseRunId: string) => void
  t: TFn
}) => (
  <Table<EvalRun>
    rowKey="id"
    dataSource={rows}
    loading={loading}
    pagination={pagination === undefined ? false : pagination}
    locale={{ emptyText: <Empty description={t('emptyRuns')} /> }}
    columns={[
      { title: t('colRun'), dataIndex: 'id', render: compactId },
      { title: t('colName'), dataIndex: 'name' },
      { title: t('colType'), dataIndex: 'eval_type', render: (v) => <Tag>{v}</Tag> },
      {
        title: t('colResult'),
        dataIndex: 'passed',
        filters: [
          { text: t('resultPassed'), value: 'true' },
          { text: t('resultFailed'), value: 'false' },
          { text: t('resultUnknown'), value: 'unknown' },
        ],
        onFilter: (value, row) => {
          if (value === 'true') return row.passed === true
          if (value === 'false') return row.passed === false
          return row.passed !== true && row.passed !== false
        },
        render: (v) => (
          <Tag color={v === true ? 'success' : v === false ? 'error' : 'default'}>
            {v === true ? t('resultPassed') : v === false ? t('resultFailed') : t('resultUnknown')}
          </Tag>
        ),
      },
      { title: t('colScore'), dataIndex: 'score' },
      {
        title: t('colCreated'),
        dataIndex: 'created_at',
        defaultSortOrder: 'descend' as const,
        sorter: (a: EvalRun, b: EvalRun) => compareTimestamp(a.created_at, b.created_at),
        render: (value) => formatDate(value),
      },
      ...(onReplay
        ? [
            {
              title: t('colActions'),
              render: (_: unknown, row: EvalRun) =>
                row.case_run_id ? (
                  <Button icon={<ReloadOutlined />} onClick={() => onReplay(row.case_run_id!)}>
                    {t('replay')}
                  </Button>
                ) : (
                  '—'
                ),
            },
          ]
        : []),
    ]}
  />
)

const DeltaChip = ({
  label,
  delta,
  mode,
  kind = 'rate',
  tip,
}: {
  label: string
  delta: number | null
  mode: 'lowerIsBetter' | 'higherIsBetter'
  kind?: 'rate' | 'count'
  tip: string
}) => {
  const text = formatMetricDelta(delta, kind)
  const improved = deltaIsImprovement(delta, mode)
  const color = improved === true ? 'var(--ant-color-success)' : improved === false ? 'var(--ant-color-error)' : undefined
  return (
    <Tooltip title={tip}>
      <Space size={4} style={{ cursor: 'help' }}>
        <Typography.Text type="secondary">{label}</Typography.Text>
        <Typography.Text strong style={{ color }}>
          {text}
        </Typography.Text>
      </Space>
    </Tooltip>
  )
}

const SafetyDiffPanel = ({ current, baseline, t }: { current: SuiteRun; baseline: SuiteRun; t: TFn }) => {
  const deltas = diffSafetyMetrics(current.summary.safety, baseline.summary.safety)
  const byKey = Object.fromEntries(deltas.map((d) => [d.key, d])) as Record<string, (typeof deltas)[0]>
  return (
    <Alert
      type="info"
      showIcon
      style={{ marginBottom: 16 }}
      title={
        <Space wrap>
          <Typography.Text strong>{t('compareTitle')}</Typography.Text>
          <Typography.Text type="secondary">
            {t('compareSubtitle', {
              current: compactId(current.id),
              baseline: compactId(baseline.id),
            })}
          </Typography.Text>
        </Space>
      }
      description={
        <Space wrap size={[20, 8]} style={{ marginTop: 8 }}>
          <DeltaChip label={t('colAsr')} delta={byKey.asr?.delta ?? null} mode="lowerIsBetter" tip={t('tipDiffAsr')} />
          <DeltaChip
            label={t('colRefusalRate')}
            delta={byKey.refusal_rate?.delta ?? null}
            mode="higherIsBetter"
            tip={t('tipDiffRefusal')}
          />
          <DeltaChip
            label={t('colOverRefusalRate')}
            delta={byKey.over_refusal_rate?.delta ?? null}
            mode="lowerIsBetter"
            tip={t('tipDiffOverRefusal')}
          />
          <DeltaChip
            label={t('colGuardrailBlocked')}
            delta={byKey.n_guardrail_blocked?.delta ?? null}
            mode="lowerIsBetter"
            kind="count"
            tip={t('tipDiffGuardrail')}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('compareHint')}
          </Typography.Text>
        </Space>
      }
    />
  )
}

const CaseInputCell = ({ row, expanded, onToggle, t }: { row: EvalCase; expanded: boolean; onToggle: () => void; t: TFn }) => {
  const mask = caseInputShouldMask(row.metadata)
  const full = row.input || ''
  if (!mask) {
    return (
      <Typography.Text ellipsis={{ tooltip: full }} style={{ maxWidth: 360 }}>
        {full || '—'}
      </Typography.Text>
    )
  }
  if (expanded) {
    return (
      <Space orientation="vertical" size={4} style={{ maxWidth: 420 }}>
        <Typography.Text style={{ whiteSpace: 'pre-wrap' }}>{full}</Typography.Text>
        <Button type="link" size="small" onClick={onToggle} style={{ padding: 0 }}>
          {t('hideSensitiveInput')}
        </Button>
      </Space>
    )
  }
  return (
    <Space size={8}>
      <Tooltip title={t('tipMaskedInput')}>
        <Typography.Text type="secondary" style={{ cursor: 'help' }}>
          {maskSensitiveInput(full)}
        </Typography.Text>
      </Tooltip>
      <Button type="link" size="small" onClick={onToggle} style={{ padding: 0 }}>
        {t('revealSensitiveInput')}
      </Button>
    </Space>
  )
}

const safetyGateFailureDescription = (gate: SafetySummary['gate'], t: TFn): string => {
  const failedChecks = gate?.checks.filter((check) => check.status === 'failed') ?? []
  if (!failedChecks.length) return t('safetyGateFailedGenericDescription')

  const descriptions = failedChecks.map((check) => {
    switch (check.id) {
      case 'max_over_refusal_rate':
        return t('safetyGateFailedDescription', {
          actual: formatSafetyRate(check.actual),
          threshold: formatSafetyRate(check.threshold),
        })
      case 'asr_regression':
        return t('safetyGateAsrRegressionDescription', {
          actual: formatSafetyRate(check.actual),
          baseline: formatSafetyRate(check.baseline),
          tolerance: formatSafetyRate(check.tolerance),
        })
      case 'refusal_regression':
        return t('safetyGateRefusalRegressionDescription', {
          actual: formatSafetyRate(check.actual),
          baseline: formatSafetyRate(check.baseline),
          tolerance: formatSafetyRate(check.tolerance),
        })
      default:
        return t('safetyGateFailedGenericDescription')
    }
  })

  return [...new Set(descriptions)].join(' ')
}

const SafetySnapshot = ({ run, t }: { run: SuiteRun; t: TFn }) => {
  const safety: SafetySummary | undefined = run.summary.safety
  const safetyGate = safety?.gate
  const statusColor = suiteRunStatusColor(run.status)
  const nHarmful = safety?.n_harmful
  const nBenign = safety?.n_benign
  const denomHarmful = nHarmful != null ? t('metricDenomHarmful', { n: nHarmful }) : t('metricNullHint')
  const denomBenign = nBenign != null ? t('metricDenomBenign', { n: nBenign }) : t('metricNullHint')

  return (
    <Card size="small" style={{ marginBottom: 16 }} styles={{ body: { paddingBottom: 12 } }}>
      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap size={[8, 8]} align="center">
          <Tooltip title={t('latestRunSummaryHint')}>
            <Typography.Text strong style={{ cursor: 'help' }}>
              {t('latestRunSummary')} <QuestionCircleOutlined style={{ opacity: 0.55 }} />
            </Typography.Text>
          </Tooltip>
          <Tooltip title={t('tipStatus')}>
            <Tag color={statusColor} style={{ cursor: 'help' }}>
              {run.status || '—'}
            </Tag>
          </Tooltip>
          {safety?.eval_profile ? (
            <Tooltip title={t('tipEvalProfile')}>
              <Tag style={{ cursor: 'help' }}>{safety.eval_profile}</Tag>
            </Tooltip>
          ) : null}
          {safety?.judge_id ? (
            <Tooltip title={`${t('tipJudgeId')}\n\n${safety.judge_id}`}>
              <Typography.Text type="secondary" style={{ maxWidth: 280, cursor: 'help' }} ellipsis>
                {formatJudgeIdShort(safety.judge_id, 40)}
              </Typography.Text>
            </Tooltip>
          ) : null}
          {safetyGate ? (
            <Tooltip title={t('tipSafetyGate')}>
              <Tag
                color={safetyGate.status === 'passed' ? 'success' : safetyGate.status === 'failed' ? 'error' : 'warning'}
                style={{ cursor: 'help' }}
              >
                {safetyGate.status === 'passed'
                  ? t('safetyGatePassed')
                  : safetyGate.status === 'failed'
                    ? t('safetyGateFailed')
                    : t('safetyGatePending')}
              </Tag>
            </Tooltip>
          ) : null}
        </Space>

        <Space wrap size={[24, 16]} style={{ width: '100%' }}>
          <Tooltip title={`${t('tipAsr')}\n\n${denomHarmful}`}>
            <div style={{ cursor: 'help', minWidth: 88 }}>
              <Statistic
                title={metricTitle(t('colAsr'), t('tipAsr'))}
                valueRender={() => <RateValue value={safety?.asr} mode="lowerIsBetter" />}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {nHarmful != null ? `n=${nHarmful}` : '—'}
              </Typography.Text>
            </div>
          </Tooltip>
          <Tooltip title={`${t('tipRefusalRate')}\n\n${denomHarmful}`}>
            <div style={{ cursor: 'help', minWidth: 88 }}>
              <Statistic
                title={metricTitle(t('colRefusalRate'), t('tipRefusalRate'))}
                valueRender={() => <RateValue value={safety?.refusal_rate} mode="higherIsBetter" />}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {nHarmful != null ? `n=${nHarmful}` : '—'}
              </Typography.Text>
            </div>
          </Tooltip>
          <Tooltip title={`${t('tipOverRefusalRate')}\n\n${denomBenign}`}>
            <div style={{ cursor: 'help', minWidth: 88 }}>
              <Statistic
                title={metricTitle(t('colOverRefusalRate'), t('tipOverRefusalRate'))}
                valueRender={() => <RateValue value={safety?.over_refusal_rate} mode="lowerIsBetter" />}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {nBenign != null ? `n=${nBenign}` : '—'}
              </Typography.Text>
            </div>
          </Tooltip>
          <Tooltip title={t('tipGuardrailBlocked')}>
            <div style={{ cursor: 'help', minWidth: 88 }}>
              <Statistic
                title={metricTitle(t('colGuardrailBlocked'), t('tipGuardrailBlocked'))}
                value={safety?.n_guardrail_blocked ?? '—'}
                styles={{
                  content: {
                    fontSize: 20,
                    color: (safety?.n_guardrail_blocked ?? 0) > 0 ? 'var(--ant-color-warning)' : undefined,
                  },
                }}
              />
            </div>
          </Tooltip>
          <Tooltip title={t('tipPassed')}>
            <div style={{ cursor: 'help', minWidth: 72 }}>
              <Statistic
                title={metricTitle(t('colPassed'), t('tipPassed'))}
                value={run.summary.passed ?? '—'}
                styles={{ content: { fontSize: 20, color: 'var(--ant-color-success)' } }}
              />
            </div>
          </Tooltip>
          <Tooltip title={t('tipFailed')}>
            <div style={{ cursor: 'help', minWidth: 72 }}>
              <Statistic
                title={metricTitle(t('colFailed'), t('tipFailed'))}
                value={run.summary.failed ?? '—'}
                styles={{
                  content: {
                    fontSize: 20,
                    color: (run.summary.failed ?? 0) > 0 ? 'var(--ant-color-error)' : undefined,
                  },
                }}
              />
            </div>
          </Tooltip>
        </Space>

        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {formatSafetySummaryLine(safety, {
            passed: run.summary.passed,
            failed: run.summary.failed,
            errored: run.summary.errored,
          })}
          {run.started_at ? ` · ${formatDate(run.started_at)}` : ''}
          {' · '}
          {t('metricNullHint')}
        </Typography.Text>
        {safetyGate?.status === 'failed' ? (
          <Alert type="error" showIcon title={t('safetyGateFailedTitle')} description={safetyGateFailureDescription(safetyGate, t)} />
        ) : safetyGate?.status === 'not_evaluated' ? (
          <Alert type="warning" showIcon title={t('safetyGatePendingTitle')} description={t('safetyGatePendingDescription')} />
        ) : safetyGate?.status === 'passed' && !safetyGate.baseline_suite_run_id ? (
          <Alert type="info" showIcon title={t('safetyGateBaselinePendingTitle')} description={t('safetyGateBaselinePendingDescription')} />
        ) : null}
      </Space>
    </Card>
  )
}

export function EvaluationsPage() {
  const { t } = useTranslation('evaluations')
  const { message } = App.useApp()
  const client = useQueryClient()
  const currentUser = useQuery(currentUserQuery())
  const canWriteEvals = hasScope(currentUser.data, 'evals:write')
  const canDeleteEvals = hasScope(currentUser.data, 'evals:delete')
  const suites = useQuery({ queryKey: ['evals', 'suites'], queryFn: listSuites })
  const targets = useQuery({
    queryKey: ['evals', 'targets'],
    queryFn: listEvalTargets,
    enabled: canWriteEvals,
  })
  const packs = useQuery({
    queryKey: ['evals', 'packs'],
    queryFn: () => listPacks({ readyOnly: true }),
    enabled: canWriteEvals,
  })
  const [suite, setSuite] = useState('')
  const [activeTab, setActiveTab] = useState('cases')
  const [importingPackId, setImportingPackId] = useState<string | null>(null)
  const [removingPackId, setRemovingPackId] = useState<string | null>(null)
  const [removingSuiteId, setRemovingSuiteId] = useState<string | null>(null)
  const [removingCaseId, setRemovingCaseId] = useState<string | null>(null)
  const [exportingSuiteRunId, setExportingSuiteRunId] = useState<string | null>(null)
  const [cancellingSuiteRunId, setCancellingSuiteRunId] = useState<string | null>(null)
  const [runningSuite, setRunningSuite] = useState(false)
  const [defaultTimeout, setDefaultTimeout] = useState(120)
  const [selectedCaseTag, setSelectedCaseTag] = useState<string | undefined>()
  const [selectedCaseName, setSelectedCaseName] = useState<string | undefined>()
  const [savingCaseTagsId, setSavingCaseTagsId] = useState<string | null>(null)
  const [caseTagDrafts, setCaseTagDrafts] = useState<Record<string, string[]>>({})
  const [suiteDrawerOpen, setSuiteDrawerOpen] = useState(false)
  const [editingSuite, setEditingSuite] = useState<Suite | null>(null)
  const [savingSuite, setSavingSuite] = useState(false)
  const [caseDrawerOpen, setCaseDrawerOpen] = useState(false)
  const [editingCase, setEditingCase] = useState<EvalCase | null>(null)
  const [savingCase, setSavingCase] = useState(false)
  const [casesPage, setCasesPage] = useState(1)
  const [runsPage, setRunsPage] = useState(1)
  const [suiteRunsPage, setSuiteRunsPage] = useState(1)
  const [selectedRunKeys, setSelectedRunKeys] = useState<string[]>([])
  const [revealedCaseIds, setRevealedCaseIds] = useState<Set<string>>(() => new Set())
  /** Suite-run drill-down: operator path import → run → safety → case results. */
  const [drillSuiteRunId, setDrillSuiteRunId] = useState<string | null>(null)
  const [drillCaseRunsPage, setDrillCaseRunsPage] = useState(1)
  const casesPageSize = 50
  const runsPageSize = 20
  const suiteRunsPageSize = 20
  const drillCaseRunsPageSize = 50
  const cases = useQuery({
    queryKey: ['evals', 'cases', suite, casesPage, casesPageSize],
    queryFn: () => listCases(suite, { page: casesPage, limit: casesPageSize }),
  })
  const runs = useQuery({
    queryKey: ['evals', 'runs', runsPage, runsPageSize],
    queryFn: () => listRuns({ page: runsPage, limit: runsPageSize }),
  })
  const suiteRuns = useQuery({
    queryKey: ['evals', 'suite-runs', suite, suiteRunsPage, suiteRunsPageSize],
    queryFn: () => listSuiteRuns(suite, { page: suiteRunsPage, limit: suiteRunsPageSize }),
    enabled: Boolean(suite),
    refetchInterval: (query) =>
      (query.state.data?.data ?? []).some((run) => isActiveSuiteRun(run.status)) ? 2_000 : false,
    refetchIntervalInBackground: true,
  })
  const drillSuiteRunIsActive = (suiteRuns.data?.data ?? []).some(
    (run) => run.id === drillSuiteRunId && isActiveSuiteRun(run.status)
  )
  const failures = useQuery({
    queryKey: ['evals', 'failures'],
    queryFn: () => listFailures({ limit: 50 }),
  })
  const suiteRunCaseRuns = useQuery({
    queryKey: ['evals', 'suite-run-case-runs', drillSuiteRunId, drillCaseRunsPage, drillCaseRunsPageSize],
    queryFn: () => listSuiteRunCaseRuns(drillSuiteRunId!, { page: drillCaseRunsPage, limit: drillCaseRunsPageSize }),
    enabled: Boolean(drillSuiteRunId),
    refetchInterval: drillSuiteRunIsActive ? 2_000 : false,
    refetchIntervalInBackground: true,
  })
  /** Targeted invalidation: avoid refetching packs on every run (hot path). */
  const refreshAfterRun = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['evals', 'suite-runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'failures'] }),
      client.invalidateQueries({ queryKey: ['evals', 'cases'] }),
      client.invalidateQueries({ queryKey: ['evals', 'suite-run-case-runs'] }),
    ])
  }
  const refreshAfterImport = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['evals', 'suites'] }),
      client.invalidateQueries({ queryKey: ['evals', 'cases'] }),
      client.invalidateQueries({ queryKey: ['evals', 'packs'] }),
    ])
  }
  const refreshAfterPackRemoval = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['evals', 'suites'] }),
      client.invalidateQueries({ queryKey: ['evals', 'cases'] }),
      client.invalidateQueries({ queryKey: ['evals', 'packs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'suite-runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'suite-run-case-runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'failures'] }),
    ])
  }
  const refreshAfterSuiteRemoval = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['evals', 'suites'] }),
      client.invalidateQueries({ queryKey: ['evals', 'cases'] }),
      client.invalidateQueries({ queryKey: ['evals', 'suite-runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'suite-run-case-runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'runs'] }),
      client.invalidateQueries({ queryKey: ['evals', 'failures'] }),
    ])
  }

  const selectedSuite = useMemo(() => (suites.data ?? []).find((s) => s.id === suite), [suites.data, suite])
  const selectedPack = getImportedPackIdentity(selectedSuite)
  const selectedPackKey = selectedPack ? `${selectedPack.pack_id}@${selectedPack.pack_version}` : ''
  const caseRows = cases.data?.data ?? EMPTY_CASE_ROWS
  const latestSafetyRun = useMemo(() => pickLatestSafetyRun(suiteRuns.data?.data), [suiteRuns.data?.data])

  const suiteRunRows = suiteRuns.data?.data
  const hasActiveSuiteRun = (suiteRunRows ?? []).some((run) => isActiveSuiteRun(run.status))

  const comparePair = useMemo((): { current: SuiteRun; baseline: SuiteRun } | null => {
    const rows = suiteRunRows ?? []
    if (selectedRunKeys.length === 2) {
      const a = rows.find((r) => r.id === selectedRunKeys[0])
      const b = rows.find((r) => r.id === selectedRunKeys[1])
      if (!a || !b) return null
      // Newer (later started_at) as current
      const aTime = a.started_at ? new Date(a.started_at).getTime() : 0
      const bTime = b.started_at ? new Date(b.started_at).getTime() : 0
      return aTime >= bTime ? { current: a, baseline: b } : { current: b, baseline: a }
    }
    if (selectedRunKeys.length === 1) {
      const current = rows.find((r) => r.id === selectedRunKeys[0])
      if (!current) return null
      const idx = rows.findIndex((r) => r.id === current.id)
      // Table default sort is started_at desc → next row is previous run
      const baseline = idx >= 0 ? rows[idx + 1] : undefined
      if (!baseline) return null
      return { current, baseline }
    }
    return null
  }, [selectedRunKeys, suiteRunRows])

  const suiteOptions = useMemo(
    () =>
      (suites.data ?? []).map((item: Suite) => ({
        value: item.id,
        label: isSafetySuite(item) ? `${item.name} · ${t('tagSafety')}` : item.name,
        suite: item,
      })),
    [suites.data, t]
  )

  const importablePacks = useMemo(() => (packs.data ?? []).filter((p) => p.importable), [packs.data])
  const caseTagOptions = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of caseRows) {
      for (const tag of row.tags) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1)
      }
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([tag, count]) => ({ value: tag, label: `${tag} (${count})` }))
  }, [caseRows])
  const handleImportPack = async (pack: EvalPack) => {
    setImportingPackId(pack.id)
    try {
      const result = await importPack(pack.id, pack.pack_version ?? '')
      message.success(
        t('importSucceeded', {
          pack: result.pack_id,
          created: result.cases_created ?? 0,
          updated: result.cases_updated ?? 0,
        })
      )
      await refreshAfterImport()
      if (result.suite_id) {
        setSuite(result.suite_id)
        setCasesPage(1)
        setSelectedCaseTag(undefined)
        setSelectedCaseName(undefined)
        setCaseTagDrafts({})
        setSuiteRunsPage(1)
        setDrillSuiteRunId(null)
        setDrillCaseRunsPage(1)
        setActiveTab('cases')
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('importFailed'))
    } finally {
      setImportingPackId(null)
    }
  }

  const removePackAndRefresh = async (packId: string, packVersion: string) => {
    setRemovingPackId(`${packId}@${packVersion}`)
    try {
      const result = await removePack(packId, packVersion)
      message.success(
        t('removeSucceeded', {
          pack: `${result.pack_id}@${result.pack_version}`,
          suites: result.suites_deleted,
          cases: result.cases_deleted,
          suiteRuns: result.suite_runs_deleted,
          caseRuns: result.case_runs_deleted,
        })
      )
      setSuite('')
      setCasesPage(1)
      setSelectedCaseTag(undefined)
      setSelectedCaseName(undefined)
      setCaseTagDrafts({})
      setSuiteRunsPage(1)
      setSelectedRunKeys([])
      setRevealedCaseIds(new Set())
      setDrillSuiteRunId(null)
      setDrillCaseRunsPage(1)
      setActiveTab('cases')
      await refreshAfterPackRemoval()
    } finally {
      setRemovingPackId(null)
    }
  }

  const handleRemovePack = async (packId: string, packVersion: string) => {
    try {
      await removePackAndRefresh(packId, packVersion)
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('removeFailed'))
    }
  }

  const handleRemoveSuite = async () => {
    if (!selectedSuite || selectedPack) return
    setRemovingSuiteId(selectedSuite.id)
    try {
      const result = await deleteSuite(selectedSuite.id)
      message.success(
        t('suiteRemoved', {
          suite: selectedSuite.name,
          cases: result.cases_deleted,
          suiteRuns: result.suite_runs_deleted,
          caseRuns: result.case_runs_deleted,
        })
      )
      setSuite('')
      setCasesPage(1)
      setSelectedCaseTag(undefined)
      setSelectedCaseName(undefined)
      setCaseTagDrafts({})
      setSuiteRunsPage(1)
      setSelectedRunKeys([])
      setRevealedCaseIds(new Set())
      setDrillSuiteRunId(null)
      setDrillCaseRunsPage(1)
      setActiveTab('cases')
      await refreshAfterSuiteRemoval()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('suiteRemoveFailed'))
    } finally {
      setRemovingSuiteId(null)
    }
  }

  const handleRemoveCase = async (row: EvalCase) => {
    setRemovingCaseId(row.id)
    try {
      await deleteCase(row.id)
      message.success(t('caseRemoved', { case: row.name }))
      setCaseTagDrafts((previous) => {
        const next = { ...previous }
        delete next[row.id]
        return next
      })
      setRevealedCaseIds((previous) => {
        const next = new Set(previous)
        next.delete(row.id)
        return next
      })
      if (editingCase?.id === row.id) {
        setEditingCase(null)
        setCaseDrawerOpen(false)
      }
      if (caseRows.length <= 1 && casesPage > 1) {
        setCasesPage((page) => page - 1)
      }
      await client.invalidateQueries({ queryKey: ['evals', 'cases'] })
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('caseRemoveFailed'))
    } finally {
      setRemovingCaseId(null)
    }
  }

  const handleSaveSuite = async (value: EvalSuiteWrite) => {
    const isEdit = editingSuite != null
    setSavingSuite(true)
    try {
      const saved = editingSuite
        ? await updateSuite(
            editingSuite.id,
            {
              name: value.name,
              description: value.description,
              enabled: value.enabled,
              tags: value.tags,
            } satisfies EvalSuiteUpdate
          )
        : await createSuite(value)
      message.success(t(isEdit ? 'suiteSaved' : 'suiteCreated'))
      setSuite(saved.id)
      setCasesPage(1)
      setSelectedCaseTag(undefined)
      setSelectedCaseName(undefined)
      setCaseTagDrafts({})
      setSuiteRunsPage(1)
      setSelectedRunKeys([])
      setRevealedCaseIds(new Set())
      setDrillSuiteRunId(null)
      setDrillCaseRunsPage(1)
      setActiveTab('cases')
      setSuiteDrawerOpen(false)
      setEditingSuite(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['evals', 'suites'] }),
        client.invalidateQueries({ queryKey: ['evals', 'cases'] }),
      ])
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('suiteSaveFailed'))
    } finally {
      setSavingSuite(false)
    }
  }

  const handleSaveCase = async (value: EvalCaseWrite) => {
    const isEdit = editingCase != null
    setSavingCase(true)
    try {
      const saved = editingCase ? await updateCase(editingCase.id, value) : await createCase(value)
      message.success(t(isEdit ? 'caseSaved' : 'caseCreated'))
      setSuite(saved.suite_id)
      setCasesPage(1)
      setCaseDrawerOpen(false)
      setEditingCase(null)
      await client.invalidateQueries({ queryKey: ['evals', 'cases'] })
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('caseSaveFailed'))
    } finally {
      setSavingCase(false)
    }
  }

  const handleRunSuite = async () => {
    if (!suite) return
    setRunningSuite(true)
    try {
      await runSuite(suite, {
        tag: selectedCaseTag,
        name: selectedCaseName,
        defaultTimeout,
      })
      message.success(t('suiteQueued'))
      setActiveTab('suite-runs')
      setSuiteRunsPage(1)
      setDrillSuiteRunId(null)
      setDrillCaseRunsPage(1)
      await refreshAfterRun()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('suiteFailed'))
    } finally {
      setRunningSuite(false)
    }
  }

  const handleCancelSuiteRun = async (suiteRunId: string) => {
    setCancellingSuiteRunId(suiteRunId)
    try {
      const updated = await cancelSuiteRun(suiteRunId)
      const status = updated.status.toLowerCase()
      if (status === 'cancelled') {
        message.success(t('suiteCancelled'))
      } else if (status === 'cancelling') {
        message.success(t('suiteCancellationRequested'))
      } else {
        message.info(t('suiteAlreadyFinished'))
      }
      await refreshAfterRun()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('suiteCancelFailed'))
    } finally {
      setCancellingSuiteRunId(null)
    }
  }

  const handleUpdateCaseTags = async (caseId: string, rawTags: string[]) => {
    const tags = [...new Set(rawTags.map((tag) => String(tag).trim()).filter(Boolean))]
    setCaseTagDrafts((previous) => ({ ...previous, [caseId]: tags }))
    setSavingCaseTagsId(caseId)
    try {
      await updateCaseTags(caseId, tags)
      message.success(t('caseTagsSaved'))
      await client.invalidateQueries({ queryKey: ['evals', 'cases'] })
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('caseTagsSaveFailed'))
    } finally {
      setCaseTagDrafts((previous) => {
        const next = { ...previous }
        delete next[caseId]
        return next
      })
      setSavingCaseTagsId(null)
    }
  }

  const handleExportSuiteRunReport = async (suiteRunId: string) => {
    setExportingSuiteRunId(suiteRunId)
    try {
      const report = await exportSuiteRunReport(suiteRunId)
      downloadSuiteRunReport(report)
      message.success(t('reportExported'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('reportExportFailed'))
    } finally {
      setExportingSuiteRunId(null)
    }
  }

  const drillRowsFromApi = (suiteRunCaseRuns.data?.data ?? []).map(
    (cr): SuiteCaseResultLite => ({
      ...cr.result,
      name: cr.result?.name ?? cr.case_id,
      case_id: cr.case_id,
      case_run_id: cr.id,
      session_id: cr.session_id ?? cr.result?.session_id,
      status: cr.status,
      passed: cr.result?.passed ?? cr.status === 'passed',
      skipped: cr.result?.skipped ?? cr.status === 'skipped',
      timed_out: cr.result?.timed_out ?? cr.error_type === 'EvalCaseTimeout',
      error: cr.result?.error ?? cr.error_summary,
    })
  )
  const drillRows = drillRowsFromApi

  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <>
            <Select
              allowClear
              showSearch={{ optionFilterProp: 'label' }}
              value={suite || undefined}
              onChange={(v) => {
                setSuite(v ?? '')
                setCasesPage(1)
                setSelectedCaseTag(undefined)
                setSelectedCaseName(undefined)
                setCaseTagDrafts({})
                setSuiteRunsPage(1)
                setSelectedRunKeys([])
                setRevealedCaseIds(new Set())
                setDrillSuiteRunId(null)
                setDrillCaseRunsPage(1)
              }}
              placeholder={t('allSuites')}
              options={suiteOptions}
              optionRender={(option) => {
                const item = option.data?.suite as Suite | undefined
                if (!item) return option.label
                return (
                  <Space size={6}>
                    <span>{item.name}</span>
                    {isSafetySuite(item) ? <Tag color="blue">{t('tagSafety')}</Tag> : null}
                  </Space>
                )
              }}
              style={{ width: 300 }}
            />
            <Input
              allowClear
              value={selectedCaseTag ?? ''}
              aria-label={t('runAllCaseTags')}
              onChange={(event) => {
                const value = event.target.value.trim()
                setSelectedCaseTag(value || undefined)
                if (value) setSelectedCaseName(undefined)
              }}
              placeholder={t('runAllCaseTags')}
              disabled={!suite || runningSuite || hasActiveSuiteRun || removingPackId != null || removingSuiteId != null}
              style={{ width: 210 }}
            />
            <Input
              allowClear
              value={selectedCaseName ?? ''}
              aria-label={t('runOneCase')}
              onChange={(event) => {
                const value = event.target.value.trim()
                setSelectedCaseName(value || undefined)
                if (value) setSelectedCaseTag(undefined)
              }}
              placeholder={t('runOneCase')}
              disabled={!suite || runningSuite || hasActiveSuiteRun || removingPackId != null || removingSuiteId != null}
              style={{ width: 280 }}
            />
            <Tooltip title={t('tipDefaultTimeout')}>
              <Space.Compact>
                <Space.Addon>{t('defaultTimeout')}</Space.Addon>
                <InputNumber
                  min={1}
                  max={3600}
                  precision={0}
                  value={defaultTimeout}
                  disabled={!suite || runningSuite || removingPackId != null}
                  onChange={(value) => {
                    setDefaultTimeout(typeof value === 'number' && Number.isInteger(value) ? Math.min(3600, Math.max(1, value)) : 120)
                  }}
                  style={{ width: 72 }}
                />
                <Space.Addon>{t('secondsAbbr')}</Space.Addon>
              </Space.Compact>
            </Tooltip>
            {canWriteEvals ? (
              <Button
                icon={<PlusOutlined />}
                disabled={importingPackId != null || removingPackId != null || removingSuiteId != null || runningSuite || savingSuite}
                onClick={() => {
                  setEditingSuite(null)
                  setSuiteDrawerOpen(true)
                }}
              >
                {t('newSuite')}
              </Button>
            ) : null}
            {canWriteEvals ? (
              <Dropdown
                menu={{
                  items: importablePacks.length
                    ? importablePacks.map((pack) => ({
                        key: `${pack.id}@${pack.pack_version ?? ''}`,
                        label: [
                          pack.layer ? `${pack.title} (${pack.layer})` : pack.title,
                          pack.pack_version ? `@${pack.pack_version}` : '',
                        ]
                          .filter(Boolean)
                          .join(' '),
                        disabled: importingPackId != null || removingPackId != null || removingSuiteId != null || runningSuite,
                        onClick: () => {
                          void handleImportPack(pack)
                        },
                      }))
                    : [
                        {
                          key: 'empty',
                          label: packs.isLoading ? t('packsLoading') : t('packsEmpty'),
                          disabled: true,
                        },
                      ],
                }}
                trigger={['click']}
              >
                <Button
                  icon={<DownloadOutlined />}
                  loading={importingPackId != null || packs.isLoading}
                  disabled={removingPackId != null || removingSuiteId != null || runningSuite}
                >
                  {t('importSafetyPack')}
                </Button>
              </Dropdown>
            ) : null}
            {canDeleteEvals && selectedPack ? (
              <Popconfirm
                title={t('removeSafetyPackConfirmTitle', { pack: selectedPackKey })}
                description={t('removeSafetyPackConfirmDescription')}
                okText={t('removeSafetyPack')}
                cancelText={t('common:cancel')}
                okButtonProps={{ danger: true }}
                onConfirm={() => {
                  void handleRemovePack(selectedPack.pack_id, selectedPack.pack_version)
                }}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={removingPackId === selectedPackKey}
                  disabled={importingPackId != null || runningSuite || removingPackId != null}
                >
                  {t('removeSafetyPack')}
                </Button>
              </Popconfirm>
            ) : null}
            {canDeleteEvals && selectedSuite && !selectedPack ? (
              <Popconfirm
                title={t('deleteSuiteConfirmTitle', { suite: selectedSuite.name })}
                description={t('deleteSuiteConfirmDescription')}
                okText={t('deleteSuite')}
                cancelText={t('common:cancel')}
                okButtonProps={{ danger: true }}
                onConfirm={() => {
                  void handleRemoveSuite()
                }}
              >
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={removingSuiteId === selectedSuite.id}
                  disabled={importingPackId != null || removingPackId != null || runningSuite || removingSuiteId != null}
                >
                  {t('deleteSuite')}
                </Button>
              </Popconfirm>
            ) : null}
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!suite || runningSuite || hasActiveSuiteRun || removingPackId != null || removingSuiteId != null}
              loading={runningSuite}
              onClick={() => void handleRunSuite()}
            >
              {t('runSuite')}
            </Button>
          </>
        }
      />
      <Card className="workbench-card">
        {suite && isSafetySuite(selectedSuite) && latestSafetyRun?.summary.safety ? <SafetySnapshot run={latestSafetyRun} t={t} /> : null}
        {suite && isSafetySuite(selectedSuite) && !latestSafetyRun && !suiteRuns.isLoading ? (
          <Alert type="info" showIcon style={{ marginBottom: 16 }} title={t('safetySuiteHint')} description={t('safetySuiteHintDesc')} />
        ) : null}
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'cases',
              label: t('tabCases'),
              children: (
                <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                  {selectedPack ? (
                    <Alert
                      type="info"
                      showIcon
                      title={t('importedPackImmutableHint', {
                        pack: selectedPackKey,
                      })}
                    />
                  ) : null}
                  {suite && !selectedPack && canWriteEvals ? (
                    <Space wrap>
                      <Button
                        icon={<EditOutlined />}
                        disabled={savingSuite || savingCase || runningSuite || removingSuiteId != null}
                        onClick={() => {
                          if (!selectedSuite) return
                          setEditingSuite(selectedSuite)
                          setSuiteDrawerOpen(true)
                        }}
                      >
                        {t('editSuite')}
                      </Button>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        disabled={savingSuite || savingCase || runningSuite || removingSuiteId != null}
                        onClick={() => {
                          setEditingCase(null)
                          setCaseDrawerOpen(true)
                        }}
                      >
                        {t('newCase')}
                      </Button>
                    </Space>
                  ) : null}
                  <Table<EvalCase>
                    rowKey="id"
                    dataSource={caseRows}
                    loading={cases.isLoading}
                    pagination={{
                      current: casesPage,
                      pageSize: casesPageSize,
                      total: cases.data?.meta.total_count ?? 0,
                      showSizeChanger: false,
                      onChange: (page) => setCasesPage(page),
                    }}
                    locale={{
                      emptyText: <Empty description={suite ? t('emptyCases') : t('selectSuiteForRuns')} />,
                    }}
                    columns={[
                      { title: t('colCase'), dataIndex: 'name' },
                      {
                        title: metricTitle(t('colCaseTags'), t('tipCaseTags')),
                        width: 250,
                        render: (_, row) => {
                          const tags = caseTagDrafts[row.id] ?? row.tags
                          if (!canWriteEvals || selectedPack) {
                            return tags.length ? (
                              <Space size={[0, 4]} wrap>
                                {tags.map((tag) => (
                                  <Tag key={tag}>{tag}</Tag>
                                ))}
                              </Space>
                            ) : (
                              '—'
                            )
                          }
                          return (
                            <Select
                              mode="tags"
                              showSearch={{ optionFilterProp: 'label' }}
                              tokenSeparators={[',']}
                              maxTagCount="responsive"
                              value={tags}
                              options={caseTagOptions}
                              loading={savingCaseTagsId === row.id}
                              disabled={
                                savingCaseTagsId != null ||
                                runningSuite ||
                                removingPackId != null ||
                                removingSuiteId != null ||
                                removingCaseId != null
                              }
                              onChange={(value) => {
                                const next = Array.isArray(value) ? value.map(String) : []
                                void handleUpdateCaseTags(row.id, next)
                              }}
                              placeholder={t('caseTagsPlaceholder')}
                              style={{ width: '100%' }}
                            />
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colSafetyMeta'), t('tipSafetyMeta')),
                        width: 160,
                        render: (_, row) => {
                          const benign = caseIsBenign(row.metadata)
                          const layer = caseLayer(row.metadata)
                          if (benign == null && !layer) return '—'
                          return (
                            <Space size={4} wrap>
                              {benign === true ? (
                                <Tooltip title={t('tipSafetyMeta')}>
                                  <Tag color="green">{t('tagBenign')}</Tag>
                                </Tooltip>
                              ) : null}
                              {benign === false ? (
                                <Tooltip title={t('tipSafetyMeta')}>
                                  <Tag color="orange">{t('tagHarmful')}</Tag>
                                </Tooltip>
                              ) : null}
                              {layer ? <Tag>{layer}</Tag> : null}
                            </Space>
                          )
                        },
                      },
                      {
                        title: t('colInput'),
                        dataIndex: 'input',
                        width: 360,
                        render: (_, row) => (
                          <CaseInputCell
                            row={row}
                            expanded={revealedCaseIds.has(row.id)}
                            onToggle={() => {
                              setRevealedCaseIds((prev) => {
                                const next = new Set(prev)
                                if (next.has(row.id)) next.delete(row.id)
                                else next.add(row.id)
                                return next
                              })
                            }}
                            t={t}
                          />
                        ),
                      },
                      { title: t('colCriteria'), dataIndex: 'criteria', ellipsis: true },
                      {
                        title: t('colEnabled'),
                        dataIndex: 'enabled',
                        render: (v) => <Tag color={v ? 'success' : 'default'}>{String(v)}</Tag>,
                      },
                      {
                        title: t('colActions'),
                        render: (_, row) => (
                          <Space size={8}>
                            {canWriteEvals && !selectedPack ? (
                              <Button
                                icon={<EditOutlined />}
                                disabled={
                                  runningSuite || removingPackId != null || removingSuiteId != null || removingCaseId != null || savingCase
                                }
                                onClick={() => {
                                  setEditingCase(row)
                                  setCaseDrawerOpen(true)
                                }}
                              >
                                {t('common:edit')}
                              </Button>
                            ) : null}
                            <Button
                              icon={<PlayCircleOutlined />}
                              disabled={runningSuite || removingPackId != null || removingSuiteId != null || removingCaseId != null}
                              onClick={async () => {
                                try {
                                  await runCase(row.id)
                                  message.success(t('evalSubmitted'))
                                  await refreshAfterRun()
                                } catch (error) {
                                  message.error(error instanceof Error ? error.message : t('evalFailed'))
                                }
                              }}
                            >
                              {t('runCase')}
                            </Button>
                            {canDeleteEvals && !selectedPack ? (
                              <Popconfirm
                                title={t('deleteCaseConfirmTitle', { case: row.name })}
                                description={t('deleteCaseConfirmDescription')}
                                okText={t('deleteCase')}
                                cancelText={t('common:cancel')}
                                okButtonProps={{ danger: true }}
                                onConfirm={() => {
                                  void handleRemoveCase(row)
                                }}
                              >
                                <Button
                                  danger
                                  icon={<DeleteOutlined />}
                                  loading={removingCaseId === row.id}
                                  disabled={runningSuite || removingPackId != null || removingSuiteId != null || removingCaseId != null}
                                >
                                  {t('deleteCase')}
                                </Button>
                              </Popconfirm>
                            ) : null}
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'suite-runs',
              label: t('tabSuiteRuns'),
              children: !suite ? (
                <Empty description={t('selectSuiteForRuns')} />
              ) : drillSuiteRunId ? (
                <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                  <Space wrap>
                    <Button
                      type="link"
                      style={{ paddingLeft: 0 }}
                      onClick={() => {
                        setDrillSuiteRunId(null)
                        setDrillCaseRunsPage(1)
                      }}
                    >
                      ← {t('backToSuiteRuns')}
                    </Button>
                    <Typography.Text strong>{t('caseRunsTitle')}</Typography.Text>
                    <Typography.Text type="secondary">{t('caseRunsSubtitle', { id: compactId(drillSuiteRunId) })}</Typography.Text>
                    <Tag>{t('caseRunsFromApi')}</Tag>
                    {canWriteEvals ? (
                      <Button
                        type="link"
                        size="small"
                        icon={<DownloadOutlined />}
                        loading={exportingSuiteRunId === drillSuiteRunId}
                        disabled={exportingSuiteRunId != null}
                        onClick={() => void handleExportSuiteRunReport(drillSuiteRunId)}
                      >
                        {t('exportReport')}
                      </Button>
                    ) : null}
                  </Space>
                  <Table<SuiteCaseResultLite>
                    rowKey={(row) => row.case_run_id || row.case_id || row.name}
                    dataSource={drillRows}
                    loading={suiteRunCaseRuns.isLoading}
                    locale={{ emptyText: <Empty description={t('caseRunsEmpty')} /> }}
                    pagination={{
                      current: drillCaseRunsPage,
                      pageSize: drillCaseRunsPageSize,
                      total: suiteRunCaseRuns.data?.meta.total_count ?? 0,
                      showSizeChanger: false,
                      onChange: (page) => setDrillCaseRunsPage(page),
                    }}
                    scroll={{ x: 1700 }}
                    columns={[
                      {
                        title: t('colCase'),
                        dataIndex: 'name',
                        ellipsis: true,
                      },
                      {
                        title: t('colStatus'),
                        dataIndex: 'status',
                        width: 150,
                        render: (v: string, row) => (
                          <Space size={4}>
                            <Tag color={suiteRunStatusColor(v)}>{v || '—'}</Tag>
                            {row.timed_out ? (
                              <Tooltip title={t('tipTimedOut')}>
                                <Tag color="warning">{t('timedOut')}</Tag>
                              </Tooltip>
                            ) : null}
                          </Space>
                        ),
                      },
                      {
                        title: metricTitle(t('colTimeout'), t('tipDefaultTimeout')),
                        dataIndex: 'timeout_seconds',
                        width: 100,
                        render: (value: number | undefined) => (value == null ? '—' : `${value} ${t('secondsAbbr')}`),
                      },
                      {
                        title: metricTitle(t('colAccuracyResult'), t('tipAccuracyResult')),
                        dataIndex: 'accuracy_passed',
                        width: 120,
                        render: (_value, row) => {
                          const score = row.accuracy_score
                          const passed = row.accuracy_passed
                          if (score == null && passed == null) return '—'
                          return (
                            <Tag color={passed === false ? 'red' : passed === true ? 'green' : 'default'}>{formatEvalScore(score)}</Tag>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colAccuracyReason'), t('tipAccuracyReason')),
                        dataIndex: 'accuracy_reason',
                        width: 220,
                        ellipsis: true,
                        render: (value: string | undefined) =>
                          value ? (
                            <Tooltip title={value}>
                              <Typography.Text ellipsis style={{ display: 'block' }}>
                                {value}
                              </Typography.Text>
                            </Tooltip>
                          ) : (
                            '—'
                          ),
                      },
                      {
                        title: metricTitle(t('colJudgeResult'), t('tipJudgeResult')),
                        dataIndex: 'judge_passed',
                        width: 110,
                        render: (_value, row) => {
                          const score = row.judge_score
                          const passed = row.judge_passed
                          if (score == null && passed == null) return '—'
                          return (
                            <Tag color={passed === false ? 'red' : 'green'}>
                              {score != null ? `${score}/10` : passed ? t('resultPassed') : t('resultFailed')}
                            </Tag>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colJudgeReason'), t('tipJudgeReason')),
                        dataIndex: 'judge_reason',
                        width: 220,
                        ellipsis: true,
                        render: (value: string | undefined) =>
                          value ? (
                            <Tooltip title={value}>
                              <Typography.Text ellipsis style={{ display: 'block' }}>
                                {value}
                              </Typography.Text>
                            </Tooltip>
                          ) : (
                            '—'
                          ),
                      },
                      {
                        title: metricTitle(t('colReliability'), t('tipReliability')),
                        dataIndex: 'reliability_passed',
                        width: 120,
                        render: (value: boolean | undefined) =>
                          value == null ? '—' : <Tag color={value ? 'green' : 'red'}>{value ? t('resultPassed') : t('resultFailed')}</Tag>,
                      },
                      {
                        title: metricTitle(t('colReliabilityEvidence'), t('tipReliabilityEvidence')),
                        dataIndex: 'reliability_evidence',
                        width: 280,
                        ellipsis: true,
                        render: (value: SuiteCaseResultLite['reliability_evidence']) => {
                          const text = formatReliabilityEvidence(value, t)
                          return text === '—' ? (
                            text
                          ) : (
                            <Tooltip title={text}>
                              <Typography.Text ellipsis style={{ display: 'block' }}>
                                {text}
                              </Typography.Text>
                            </Tooltip>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colPerformance'), t('tipPerformance')),
                        dataIndex: 'performance',
                        width: 240,
                        ellipsis: true,
                        render: (value: SuiteCaseResultLite['performance']) => {
                          const text = formatPerformanceEvidence(value)
                          return text === '—' ? (
                            text
                          ) : (
                            <Tooltip title={text}>
                              <Typography.Text ellipsis style={{ display: 'block' }}>
                                {text}
                              </Typography.Text>
                            </Tooltip>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colDuration'), t('tipDuration')),
                        dataIndex: 'duration_seconds',
                        width: 100,
                        render: (value: number | undefined) => formatCaseDuration(value),
                      },
                      {
                        title: t('colCaseRun'),
                        dataIndex: 'case_run_id',
                        width: 100,
                        render: (v) => (v ? compactId(String(v)) : '—'),
                      },
                      {
                        title: t('colSession'),
                        dataIndex: 'session_id',
                        width: 120,
                        ellipsis: true,
                        render: (v) => (v ? compactId(String(v)) : '—'),
                      },
                      {
                        title: t('colError'),
                        dataIndex: 'error',
                        ellipsis: true,
                        render: (v) => v || '—',
                      },
                    ]}
                  />
                </Space>
              ) : (
                <>
                  {comparePair ? (
                    <SafetyDiffPanel current={comparePair.current} baseline={comparePair.baseline} t={t} />
                  ) : (suiteRunRows?.length ?? 0) >= 2 ? (
                    <Alert type="info" showIcon style={{ marginBottom: 12 }} title={t('compareSelectHint')} />
                  ) : null}
                  <Table<SuiteRun>
                    rowKey="id"
                    dataSource={suiteRunRows ?? []}
                    loading={suiteRuns.isLoading || runningSuite}
                    locale={{ emptyText: <Empty description={t('emptySuiteRuns')} /> }}
                    rowSelection={{
                      type: 'checkbox',
                      selectedRowKeys: selectedRunKeys,
                      hideSelectAll: true,
                      onChange: (keys) => {
                        const next = keys.map(String)
                        // Keep at most 2 selections (newest order preserved by click order)
                        setSelectedRunKeys(next.slice(-2))
                      },
                      getCheckboxProps: () => ({
                        disabled: false,
                      }),
                    }}
                    pagination={{
                      current: suiteRunsPage,
                      pageSize: suiteRunsPageSize,
                      total: suiteRuns.data?.meta.total_count ?? 0,
                      onChange: setSuiteRunsPage,
                    }}
                    scroll={{ x: 1860 }}
                    columns={[
                      {
                        title: t('colRun'),
                        dataIndex: 'id',
                        width: 100,
                        render: (id: string) => (
                          <Button
                            type="link"
                            size="small"
                            style={{ padding: 0 }}
                            onClick={() => {
                              setDrillCaseRunsPage(1)
                              setDrillSuiteRunId(id)
                            }}
                          >
                            {compactId(id)}
                          </Button>
                        ),
                      },
                      {
                        title: metricTitle(t('colStatus'), t('tipStatus')),
                        dataIndex: 'status',
                        width: 100,
                        render: (v: string) => (
                          <Tooltip title={t('tipStatus')}>
                            <Tag color={suiteRunStatusColor(v)}>{v || '—'}</Tag>
                          </Tooltip>
                        ),
                      },
                      {
                        title: metricTitle(t('colProgress'), t('tipProgress')),
                        width: 170,
                        render: (_: unknown, row: SuiteRun) => {
                          if (!isActiveSuiteRun(row.status)) return '—'
                          const { completed, total } = suiteRunProgress(row)
                          const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0
                          return (
                            <Tooltip title={t('tipProgress')}>
                              <div style={{ minWidth: 145 }}>
                                <Progress
                                  percent={percent}
                                  status="active"
                                  size="small"
                                  format={() =>
                                    total ? t('suiteRunProgress', { completed, total }) : t('suiteRunProgressPending')
                                  }
                                />
                              </div>
                            </Tooltip>
                          )
                        },
                      },
                      {
                        title: t('colSelection'),
                        width: 190,
                        ellipsis: true,
                        render: (_, row) => {
                          const name = row.summary.selected_name
                          const tag = row.summary.selected_tag
                          const selection = name
                            ? t('selectorCaseName', { name })
                            : tag
                              ? t('selectorCaseTag', { tag })
                              : t('selectorAllCases')
                          return (
                            <Typography.Text ellipsis style={{ maxWidth: 180 }}>
                              {selection}
                            </Typography.Text>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colDefaultTimeout'), t('tipDefaultTimeout')),
                        width: 120,
                        render: (_, row) => {
                          const timeout = row.summary.default_timeout
                          return timeout == null ? '—' : `${timeout} ${t('secondsAbbr')}`
                        },
                      },
                      {
                        title: metricTitle(t('colPassed'), t('tipPassed')),
                        width: 72,
                        render: (_, row) => row.summary.passed ?? '—',
                      },
                      {
                        title: metricTitle(t('colFailed'), t('tipFailed')),
                        width: 72,
                        render: (_, row) => row.summary.failed ?? '—',
                      },
                      {
                        title: metricTitle(t('colErrored'), t('tipErrored')),
                        width: 72,
                        render: (_, row) => row.summary.errored ?? '—',
                      },
                      {
                        title: metricTitle(t('colAsr'), t('tipAsr')),
                        width: 88,
                        render: (_, row) => (
                          <Tooltip
                            title={`${t('tipAsr')}\n\n${
                              row.summary.safety?.n_harmful != null
                                ? t('metricDenomHarmful', { n: row.summary.safety.n_harmful })
                                : t('metricNullHint')
                            }`}
                          >
                            <span style={{ cursor: 'help' }}>
                              <RateValue value={row.summary.safety?.asr} mode="lowerIsBetter" />
                            </span>
                          </Tooltip>
                        ),
                      },
                      {
                        title: metricTitle(t('colRefusalRate'), t('tipRefusalRate')),
                        width: 96,
                        render: (_, row) => (
                          <Tooltip
                            title={`${t('tipRefusalRate')}\n\n${
                              row.summary.safety?.n_harmful != null
                                ? t('metricDenomHarmful', { n: row.summary.safety.n_harmful })
                                : t('metricNullHint')
                            }`}
                          >
                            <span style={{ cursor: 'help' }}>
                              <RateValue value={row.summary.safety?.refusal_rate} mode="higherIsBetter" />
                            </span>
                          </Tooltip>
                        ),
                      },
                      {
                        title: metricTitle(t('colOverRefusalRate'), t('tipOverRefusalRate')),
                        width: 104,
                        render: (_, row) => (
                          <Tooltip
                            title={`${t('tipOverRefusalRate')}\n\n${
                              row.summary.safety?.n_benign != null
                                ? t('metricDenomBenign', { n: row.summary.safety.n_benign })
                                : t('metricNullHint')
                            }`}
                          >
                            <span style={{ cursor: 'help' }}>
                              <RateValue value={row.summary.safety?.over_refusal_rate} mode="lowerIsBetter" />
                            </span>
                          </Tooltip>
                        ),
                      },
                      {
                        title: metricTitle(t('colGuardrailBlocked'), t('tipGuardrailBlocked')),
                        width: 100,
                        render: (_, row) => {
                          const n = row.summary.safety?.n_guardrail_blocked
                          return (
                            <Tooltip title={t('tipGuardrailBlocked')}>
                              <span
                                style={{
                                  cursor: 'help',
                                  color: (n ?? 0) > 0 ? 'var(--ant-color-warning)' : undefined,
                                  fontWeight: (n ?? 0) > 0 ? 600 : undefined,
                                }}
                              >
                                {n == null ? '—' : String(n)}
                              </span>
                            </Tooltip>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colEvalProfile'), t('tipEvalProfile')),
                        width: 100,
                        render: (_, row) => {
                          const profile = row.summary.safety?.eval_profile?.trim()
                          if (!profile) return '—'
                          return (
                            <Tooltip title={t('tipEvalProfile')}>
                              <Tag style={{ cursor: 'help' }}>{profile}</Tag>
                            </Tooltip>
                          )
                        },
                      },
                      {
                        title: metricTitle(t('colJudgeId'), t('tipJudgeId')),
                        width: 200,
                        ellipsis: true,
                        render: (_, row) => {
                          const judgeId = row.summary.safety?.judge_id
                          if (!judgeId) return '—'
                          return (
                            <Tooltip title={`${t('tipJudgeId')}\n\n${judgeId}`}>
                              <Typography.Text ellipsis style={{ maxWidth: 180, cursor: 'help' }}>
                                {formatJudgeIdShort(judgeId, 32)}
                              </Typography.Text>
                            </Tooltip>
                          )
                        },
                      },
                      {
                        title: t('colStarted'),
                        dataIndex: 'started_at',
                        width: 160,
                        defaultSortOrder: 'descend' as const,
                        sorter: (a, b) => compareTimestamp(a.started_at, b.started_at),
                        render: (value) => formatDate(value),
                      },
                      {
                        title: t('colActions'),
                        width: canWriteEvals ? 270 : 110,
                        fixed: 'right' as const,
                        render: (_: unknown, row: SuiteRun) => (
                          <Space size={2}>
                            <Button
                              type="link"
                              size="small"
                              onClick={() => {
                                setDrillCaseRunsPage(1)
                                setDrillSuiteRunId(row.id)
                              }}
                            >
                              {t('viewCaseRuns')}
                            </Button>
                            {canWriteEvals && isCancellableSuiteRunStatus(row.status) ? (
                              <Popconfirm
                                title={t('cancelSuiteRunConfirmTitle', { run: compactId(row.id) })}
                                description={t('cancelSuiteRunConfirmDescription')}
                                okText={t('cancelSuiteRun')}
                                cancelText={t('common:cancel')}
                                okButtonProps={{ danger: true }}
                                onConfirm={() => {
                                  void handleCancelSuiteRun(row.id)
                                }}
                              >
                                <Button
                                  danger
                                  type="link"
                                  size="small"
                                  loading={cancellingSuiteRunId === row.id}
                                  disabled={cancellingSuiteRunId != null}
                                >
                                  {t('cancelSuiteRun')}
                                </Button>
                              </Popconfirm>
                            ) : null}
                            {canWriteEvals ? (
                              <Button
                                type="link"
                                size="small"
                                icon={<DownloadOutlined />}
                                loading={exportingSuiteRunId === row.id}
                                disabled={exportingSuiteRunId != null}
                                onClick={() => void handleExportSuiteRunReport(row.id)}
                              >
                                {t('exportReport')}
                              </Button>
                            ) : null}
                          </Space>
                        ),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: 'runs',
              label: t('tabRuns'),
              children: (
                <RunTable
                  t={t}
                  rows={runs.data?.data ?? []}
                  loading={runs.isLoading}
                  pagination={{
                    current: runsPage,
                    pageSize: runsPageSize,
                    total: runs.data?.meta.total_count ?? 0,
                    onChange: setRunsPage,
                  }}
                />
              ),
            },
            {
              key: 'failures',
              label: t('tabFailures', { count: failures.data?.length ?? 0 }),
              children: (
                <RunTable
                  t={t}
                  rows={failures.data ?? []}
                  loading={failures.isLoading}
                  pagination={false}
                  onReplay={async (id) => {
                    try {
                      await replay(id)
                      message.success(t('replaySubmitted'))
                      await refreshAfterRun()
                    } catch (error) {
                      message.error(error instanceof Error ? error.message : t('replayFailed'))
                    }
                  }}
                />
              ),
            },
          ]}
        />
      </Card>
      <EvalSuiteAuthoringDrawer
        open={suiteDrawerOpen}
        suite={editingSuite ?? undefined}
        targets={targets.data ?? []}
        targetsLoading={targets.isLoading}
        saving={savingSuite}
        t={t}
        onClose={() => {
          if (savingSuite) return
          setSuiteDrawerOpen(false)
          setEditingSuite(null)
        }}
        onSubmit={handleSaveSuite}
      />
      <EvalCaseAuthoringDrawer
        open={caseDrawerOpen}
        suiteId={suite}
        suiteTarget={selectedSuite?.target}
        caseItem={editingCase ?? undefined}
        saving={savingCase}
        t={t}
        onClose={() => {
          if (savingCase) return
          setCaseDrawerOpen(false)
          setEditingCase(null)
        }}
        onSubmit={handleSaveCase}
      />
    </main>
  )
}
