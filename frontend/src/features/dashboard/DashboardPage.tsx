import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { type Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Flex,
  Row,
  Segmented,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/shared/ui/PageHeader'
import { compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { getRuntimeOverview, dashboardKeys } from './api'
import type { OverviewQuery, OverviewRange, OverviewTrace } from './types'
import { buildTraceSearch, emptyTraceFilters } from '@/features/trace/utils'
import { runtimeRanges, timelineChartData } from './utils'

const duration = (value: number | null | undefined) => (value == null ? '—' : `${value.toFixed(0)} ms`)
const percent = (value: number | null | undefined) => (value == null ? '—' : `${(value * 100).toFixed(1)}%`)
const integer = (value: number | null | undefined) => (value == null ? '—' : Intl.NumberFormat().format(value))
const { RangePicker } = DatePicker
const DashboardCharts = lazy(() => import('./DashboardCharts'))

export function DashboardPage() {
  const { t } = useTranslation('dashboard')
  const formatDate = useFormatDate()
  const router = useRouter()
  const { token } = theme.useToken()
  const [range, setRange] = useState<OverviewRange>('24h')
  const [customRange, setCustomRange] = useState<[Dayjs, Dayjs] | null>(null)
  const overviewQuery = useMemo<OverviewQuery>(
    () => (customRange ? { startTime: customRange[0].toISOString(), endTime: customRange[1].toISOString() } : { range }),
    [customRange, range]
  )
  const query = useQuery({
    queryKey: dashboardKeys.detail(overviewQuery),
    queryFn: () => getRuntimeOverview(overviewQuery),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  })
  const data = query.data
  const hasReceivedData = useRef(false)
  const refreshFeedbackTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [dataMotion, setDataMotion] = useState<'pending' | 'ready' | 'updated'>('pending')

  useEffect(() => {
    if (!data) return

    if (!hasReceivedData.current) {
      hasReceivedData.current = true
      setDataMotion('ready')
      return
    }

    setDataMotion('updated')
    window.clearTimeout(refreshFeedbackTimeout.current)
    refreshFeedbackTimeout.current = window.setTimeout(() => setDataMotion('ready'), 700)
  }, [data])

  useEffect(() => () => window.clearTimeout(refreshFeedbackTimeout.current), [])

  const timeline = useMemo(() => timelineChartData(data?.series ?? []), [data?.series])
  const distribution = useMemo(() => {
    const source = data?.distributions ?? {}
    const [dimension, items] = Object.entries(source).find(([, values]) => values.length > 0) ?? ['agent', []]
    return { dimension, items }
  }, [data?.distributions])
  const openTrace = (trace: OverviewTrace) => {
    const filters = {
      ...emptyTraceFilters(),
      session_id: trace.session_id?.trim() || '',
      run_id: trace.run_id?.trim() || '',
    }
    const selectedSession = filters.session_id
    const search = buildTraceSearch(filters, selectedSession, trace.trace_id?.trim() || '')
    void router.history.push(`/trace${search ? `?${search}` : ''}`)
  }
  const hasTimeline = timeline.some((item) => item.runs > 0)
  const hasVisualizationData = hasTimeline || distribution.items.length > 0
  const healthStatus = data?.health.status ?? 'checking'
  const isHealthy = healthStatus === 'ok' || healthStatus === 'ready'
  const healthClassName = `dashboard-health-indicator ${isHealthy ? 'healthy' : 'degraded'} ${isHealthy ? '' : 'is-pulsing'}`
  const failedRuns = data?.metrics.failed_runs ?? 0
  const pendingApprovals = data?.snapshots?.approvals?.pending ?? 0
  const focusState: 'attention' | 'checking' | 'stable' = !data
    ? 'checking'
    : !isHealthy || failedRuns > 0 || pendingApprovals > 0
      ? 'attention'
      : 'stable'
  const dataCoverage = data
    ? data.metrics.truncated
      ? t('sampleOfWindow', {
          sample: data.metrics.sample_size ?? data.metrics.total_runs,
          total: data.metrics.window_total ?? data.metrics.total_runs,
        })
      : t('fullWindow')
    : '—'
  const focusLabel = {
    attention: t('focusAttention'),
    checking: t('focusChecking'),
    stable: t('focusStable'),
  }[focusState]

  return (
    <main className={`page dashboard-page dashboard-data-${dataMotion}`}>
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Space wrap>
            <Segmented
              value={customRange ? undefined : range}
              options={[...runtimeRanges]}
              onChange={(value) => {
                setCustomRange(null)
                setRange(value as OverviewRange)
              }}
            />
            <RangePicker
              aria-label={t('customRange')}
              showTime
              value={customRange}
              onChange={(value) => setCustomRange(value as [Dayjs, Dayjs] | null)}
            />
            <Tooltip title={t('common:refresh')}>
              <Button
                aria-label={t('refreshOverview')}
                icon={<ReloadOutlined />}
                loading={query.isFetching}
                onClick={() => void query.refetch()}
              />
            </Tooltip>
          </Space>
        }
      />
      {query.isError && (
        <Alert className="dashboard-error" type="error" showIcon title={t('loadFailed')} description={t('loadFailedHint')} />
      )}
      <section className="dashboard-signal-rail" aria-label={t('runtimeStatus')}>
        <span>
          <i className={healthClassName} />
          {t('runtime')} <b>{healthStatus}</b>
        </span>
        <span>
          {t('observationWindow')}{' '}
          <b>{customRange ? `${formatDate(customRange[0].toISOString())} — ${formatDate(customRange[1].toISOString())}` : range}</b>
        </span>
        <span>
          {t('updatedAt')} <b>{data?.generated_at ? formatDate(data.generated_at) : '—'}</b>
        </span>
      </section>
      <section className={`dashboard-focus-strip is-${focusState} dashboard-motion-item`} aria-label={t('operationalFocus')}>
        <div className="dashboard-focus-heading">
          <span className="dashboard-focus-eyebrow">{t('operationalFocus')}</span>
          <strong>{focusLabel}</strong>
          <span className="dashboard-focus-hint">{t('operationalFocusHint')}</span>
        </div>
        <div className="dashboard-focus-metrics">
          <div>
            <span>{t('failedRuns')}</span>
            <strong>{integer(failedRuns)}</strong>
          </div>
          <div>
            <span>{t('pendingReviews')}</span>
            <strong>{integer(pendingApprovals)}</strong>
          </div>
          <div>
            <span>{t('dataCoverage')}</span>
            <strong>{dataCoverage}</strong>
          </div>
        </div>
      </section>
      <Row align="stretch" gutter={[12, 12]} className="dashboard-kpis dashboard-motion-group">
        <Col xs={24} sm={12} lg={6} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic
              title={t('totalRuns')}
              value={data?.metrics.total_runs ?? 0}
              prefix={<CheckCircleOutlined />}
              suffix={
                data?.metrics.truncated
                  ? t('sampleOfWindow', {
                      sample: data.metrics.sample_size ?? data.metrics.total_runs,
                      total: data.metrics.window_total ?? data.metrics.total_runs,
                    })
                  : undefined
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic
              title={
                <Tooltip title={t('failedRunsNativeHint')}>
                  <span>{t('failureRate')}</span>
                </Tooltip>
              }
              value={data?.metrics.failure_rate == null ? 0 : data.metrics.failure_rate * 100}
              precision={1}
              suffix="%"
              styles={{ content: { color: data?.metrics.failure_rate ? token.colorError : undefined } }}
              prefix={<WarningOutlined />}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
              {t('failedRunsCount', { count: data?.metrics.failed_runs ?? 0 })}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic title={t('p95Latency')} value={data?.metrics.p95_duration_ms ?? 0} suffix="ms" prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi dashboard-token-kpi" loading={query.isLoading}>
            <Statistic
              title={
                <Tooltip title={t('tokenSampleHint')}>
                  <span>{t('tokenBreakdown')}</span>
                </Tooltip>
              }
              value={data?.metrics.total_tokens ?? 0}
              prefix={<DatabaseOutlined />}
            />
            <div className="dashboard-token-breakdown">
              <span>
                <small>{t('inputTokens')}</small>
                <b>{integer(data?.metrics.input_tokens)}</b>
              </span>
              <span>
                <small>{t('outputTokens')}</small>
                <b>{integer(data?.metrics.output_tokens)}</b>
              </span>
            </div>
          </Card>
        </Col>
      </Row>
      {hasVisualizationData ? (
        <Suspense fallback={<DashboardChartsLoading />}>
          <DashboardCharts timeline={timeline} distribution={distribution} formatDate={formatDate} />
        </Suspense>
      ) : (
        <Card className="workbench-card dashboard-observability-empty dashboard-motion-item" loading={query.isLoading}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div className="dashboard-observability-empty-copy">
                <Typography.Text strong>{t('observability')}</Typography.Text>
                <Typography.Text type="secondary">{t('noObservabilityDataHint')}</Typography.Text>
              </div>
            }
          />
        </Card>
      )}
      <section className="dashboard-grid dashboard-governance-grid dashboard-motion-group">
        <Card
          className="workbench-card dashboard-summary-card dashboard-motion-item"
          title={t('qualityGovernance')}
          loading={query.isLoading}
        >
          <div className="dashboard-summary-list">
            <SummaryMetric
              icon={<ExperimentOutlined />}
              label={t('evalPassRate')}
              value={percent(data?.snapshots?.evaluation?.pass_rate)}
              note={
                data?.snapshots?.evaluation
                  ? t('evalSampleNote', {
                      passed: data.snapshots.evaluation.passed,
                      failed: data.snapshots.evaluation.failed,
                      sample: data.snapshots.evaluation.sample_size ?? data.snapshots.evaluation.passed + data.snapshots.evaluation.failed,
                      total: data.snapshots.evaluation.total,
                    })
                  : t('noEvalData')
              }
            />
            <SummaryMetric
              icon={<SafetyCertificateOutlined />}
              label={t('approvalsSummary')}
              value={`${integer(data?.snapshots?.approvals?.pending)} / ${integer(data?.snapshots?.approvals?.approved)}`}
              note={t('approvalsSummaryHint', {
                pending: integer(data?.snapshots?.approvals?.pending),
                approved: integer(data?.snapshots?.approvals?.approved),
                rejected: integer(data?.snapshots?.approvals?.rejected),
              })}
            />
            <SummaryMetric
              icon={<DatabaseOutlined />}
              label={t('knowledgeMemory')}
              value={`${integer(data?.snapshots?.knowledge_documents)} / ${integer(data?.snapshots?.memories)}`}
              note={t('knowledgeMemoryHint')}
            />
          </div>
        </Card>
      </section>
      <section className="dashboard-grid dashboard-detail-grid">
        <Card
          className="workbench-card"
          title={t('recentFailures')}
          extra={
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('recentFailuresHint')}
            </Typography.Text>
          }
          loading={query.isLoading}
        >
          <Table<OverviewTrace>
            size="small"
            rowKey="trace_id"
            dataSource={data?.recent_failures ?? []}
            pagination={false}
            scroll={{ x: 640 }}
            locale={{ emptyText: t('noFailures') }}
            onRow={(record) => ({
              onClick: () => openTrace(record),
              onKeyDown: (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  openTrace(record)
                }
              },
              tabIndex: 0,
              role: 'link',
              className: 'dashboard-trace-row',
            })}
            columns={[
              { title: t('run'), dataIndex: 'name', ellipsis: true, render: (value) => value || t('unnamedRun') },
              {
                title: t('subject'),
                ellipsis: true,
                render: (_, item) => {
                  const workflowId = item.workflow_id?.trim()
                  if (workflowId) {
                    return (
                      <Button
                        type="link"
                        size="small"
                        style={{ paddingInline: 0, height: 'auto' }}
                        onClick={(event) => {
                          event.stopPropagation()
                          void router.history.push(`/workflow?workflow_id=${encodeURIComponent(workflowId)}`)
                        }}
                      >
                        {workflowId}
                      </Button>
                    )
                  }
                  return item.agent_id || '—'
                },
              },
              {
                title: t('latency'),
                dataIndex: 'duration_ms',
                width: 106,
                sorter: (a, b) => (a.duration_ms ?? 0) - (b.duration_ms ?? 0),
                render: duration,
              },
              {
                title: t('startTime'),
                dataIndex: 'start_time',
                width: 164,
                defaultSortOrder: 'descend' as const,
                sorter: (a, b) => compareTimestamp(a.start_time, b.start_time),
                render: formatDate,
              },
              { title: t('common:status'), dataIndex: 'status', width: 92, render: (value) => <Tag color="error">{value}</Tag> },
            ]}
          />
        </Card>
        {data?.audit && (
          <Card className="workbench-card" title={t('recentAudit')} loading={query.isLoading}>
            <div className="dashboard-audit-list">
              {data.audit.recent.length ? (
                data.audit.recent.map((event) => (
                  <Flex key={String(event.id)} className="dashboard-audit-row" justify="space-between" gap={12}>
                    <div>
                      <Typography.Text strong>{event.action}</Typography.Text>
                      <br />
                      <Typography.Text type="secondary">{event.actor_email || event.resource_type}</Typography.Text>
                    </div>
                    <div>
                      <Tag color={event.status === 'error' ? 'error' : 'success'}>{event.status}</Tag>
                      <Typography.Text type="secondary" className="dashboard-audit-time">
                        {formatDate(event.created_at)}
                      </Typography.Text>
                    </div>
                  </Flex>
                ))
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noAudit')} />
              )}
            </div>
          </Card>
        )}
      </section>
    </main>
  )
}

function DashboardChartsLoading() {
  const { t } = useTranslation('dashboard')

  return (
    <section className="dashboard-grid dashboard-primary-grid dashboard-motion-group" aria-live="polite" aria-label={t('observability')}>
      <Card className="workbench-card dashboard-chart-card dashboard-motion-item" title={t('observability')} loading>
        <span className="dashboard-chart-loading">{t('chartLoading')}</span>
      </Card>
    </section>
  )
}

function SummaryMetric({ icon, label, value, note }: { icon: ReactNode; label: string; value: string; note: string }) {
  return (
    <div className="dashboard-summary-metric">
      <span className="dashboard-summary-icon">{icon}</span>
      <div>
        <Typography.Text type="secondary">{label}</Typography.Text>
        <Typography.Title level={4}>{value}</Typography.Title>
        <Typography.Text type="secondary">{note}</Typography.Text>
      </div>
    </div>
  )
}
