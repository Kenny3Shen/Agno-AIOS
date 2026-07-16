import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
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
  const common = useMemo(
    () => ({ textStyle: { color: token.colorTextSecondary }, backgroundColor: 'transparent' }),
    [token.colorTextSecondary]
  )

  const volumeOption = useMemo<EChartsOption>(
    () => ({
      ...common,
      animation: true,
      animationDuration: 260,
      animationDurationUpdate: 260,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      color: [token.colorPrimary, token.colorError, token.colorInfo, token.colorWarning],
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      grid: { top: 24, right: 112, bottom: 26, left: 40 },
      xAxis: { type: 'category', data: timeline.map((item) => item.time), axisLabel: { formatter: (value: string) => formatDate(value) } },
      yAxis: [
        { type: 'value', name: 'Runs', minInterval: 1 },
        { type: 'value', name: 'Error %', axisLabel: { formatter: '{value}%' } },
        { type: 'value', name: 'Tokens', position: 'right', offset: 56, axisLabel: { formatter: (value: number) => integer(value) } },
      ],
      series: [
        { name: 'Runs', type: 'line', data: timeline.map((item) => item.runs), symbol: 'circle', symbolSize: 6, lineStyle: { width: 2 } },
        { name: 'Error rate', type: 'line', yAxisIndex: 1, data: timeline.map((item) => item.errorRate), smooth: true, symbol: 'none' },
        {
          name: t('seriesInputTokens'),
          type: 'bar',
          yAxisIndex: 2,
          stack: 'tokens',
          data: timeline.map((item) => item.inputTokens),
          barMaxWidth: 22,
        },
        {
          name: t('seriesOutputTokens'),
          type: 'bar',
          yAxisIndex: 2,
          stack: 'tokens',
          data: timeline.map((item) => item.outputTokens),
          barMaxWidth: 22,
          itemStyle: { borderRadius: [3, 3, 0, 0] },
        },
      ],
    }),
    [common, formatDate, t, timeline, token.colorError, token.colorInfo, token.colorPrimary, token.colorWarning]
  )

  const latencyOption = useMemo<EChartsOption>(
    () => ({
      ...common,
      animation: true,
      animationDuration: 260,
      animationDurationUpdate: 260,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      color: [token.colorInfo, token.colorWarning],
      tooltip: { trigger: 'axis' },
      grid: { top: 24, right: 24, bottom: 26, left: 52 },
      xAxis: { type: 'category', data: timeline.map((item) => item.time), axisLabel: { formatter: (value: string) => formatDate(value) } },
      yAxis: { type: 'value', name: 'ms' },
      series: [
        { name: 'P50', type: 'line', data: timeline.map((item) => item.p50), smooth: true, symbol: 'none' },
        { name: 'P95', type: 'line', data: timeline.map((item) => item.p95), smooth: true, symbol: 'none', lineStyle: { width: 3 } },
      ],
    }),
    [common, formatDate, timeline, token.colorInfo, token.colorWarning]
  )

  const distributionOption = useMemo<EChartsOption>(
    () => ({
      ...common,
      animation: true,
      animationDuration: 260,
      animationDurationUpdate: 260,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      color: [token.colorPrimary, token.colorSuccess, token.colorWarning, token.colorError, token.colorInfo],
      tooltip: { trigger: 'item' },
      series: [
        {
          name: distribution.dimension,
          type: 'pie',
          radius: ['46%', '76%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: token.colorBgContainer, borderWidth: 2 },
          label: { formatter: '{b}  {d}%' },
          data: distribution.items.map((item) => ({ name: item.name, value: item.value })),
        },
      ],
    }),
    [
      common,
      distribution.dimension,
      distribution.items,
      token.colorBgContainer,
      token.colorError,
      token.colorInfo,
      token.colorPrimary,
      token.colorSuccess,
      token.colorWarning,
    ]
  )

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
  const healthStatus = data?.health.status ?? 'checking'
  const isHealthy = healthStatus === 'ok' || healthStatus === 'ready'
  const healthClassName = `dashboard-health-indicator ${isHealthy ? 'healthy' : 'degraded'} ${isHealthy ? '' : 'is-pulsing'}`

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
              <Button aria-label={t('refreshOverview')} icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => void query.refetch()} />
            </Tooltip>
          </Space>
        }
      />
      {query.isError && (
        <Alert
          className="dashboard-error"
          type="error"
          showIcon
          title={t('loadFailed')}
          description={t('loadFailedHint')}
        />
      )}
      <section className="dashboard-signal-rail" aria-label={t('runtimeStatus')}>
        <span>
          <i className={healthClassName} />
          Runtime <b>{healthStatus}</b>
        </span>
        <span>
          {t('observationWindow')}{' '}
          <b>{customRange ? `${formatDate(customRange[0].toISOString())} — ${formatDate(customRange[1].toISOString())}` : range}</b>
        </span>
        <span>
          {t('updatedAt')} <b>{data?.generated_at ? formatDate(data.generated_at) : '—'}</b>
        </span>
      </section>
      <Row gutter={[12, 12]} className="dashboard-kpis dashboard-motion-group">
        <Col xs={12} md={8} className="dashboard-motion-item dashboard-motion-kpi">
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
        <Col xs={12} md={8} className="dashboard-motion-item dashboard-motion-kpi">
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
        <Col xs={12} md={8} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic title={t('p95Latency')} value={data?.metrics.p95_duration_ms ?? 0} suffix="ms" prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={8} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic
              title={
                <Tooltip title={t('tokenSampleHint')}>
                  <span>{t('inputTokens')}</span>
                </Tooltip>
              }
              value={data?.metrics.input_tokens ?? 0}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={8} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic
              title={
                <Tooltip title={t('tokenSampleHint')}>
                  <span>{t('outputTokens')}</span>
                </Tooltip>
              }
              value={data?.metrics.output_tokens ?? 0}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={8} className="dashboard-motion-item dashboard-motion-kpi">
          <Card className="workbench-card dashboard-kpi" loading={query.isLoading}>
            <Statistic
              title={
                <Tooltip title={t('tokenSampleHint')}>
                  <span>{t('reportedTokens')}</span>
                </Tooltip>
              }
              value={data?.metrics.total_tokens ?? 0}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
      </Row>
      <section className="dashboard-grid dashboard-primary-grid dashboard-motion-group">
        <Card
          className="workbench-card dashboard-chart-card dashboard-motion-item"
          title={t('timelineTitle')}
          loading={query.isLoading}
        >
          {hasTimeline ? (
            <ReactECharts option={volumeOption} style={{ height: 300 }} opts={{ renderer: 'canvas' }} />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noRunsInWindow')} />
          )}
        </Card>
        <Card
          className="workbench-card dashboard-chart-card dashboard-motion-item"
          title={t('distributionTitle', { dimension: distribution.dimension })}
          loading={query.isLoading}
        >
          {distribution.items.length > 0 ? (
            <ReactECharts option={distributionOption} style={{ height: 300 }} opts={{ renderer: 'canvas' }} />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noSubjects')} />
          )}
        </Card>
      </section>
      <section className="dashboard-grid dashboard-secondary-grid dashboard-motion-group">
        <Card className="workbench-card dashboard-chart-card dashboard-motion-item" title={t('latencyTrend')} loading={query.isLoading}>
          {hasTimeline ? (
            <ReactECharts option={latencyOption} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noLatency')} />
          )}
        </Card>
        <Card className="workbench-card dashboard-summary-card dashboard-motion-item" title={t('qualityGovernance')} loading={query.isLoading}>
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
            locale={{ emptyText: t('noFailures') }}
            onRow={(record) => ({ onClick: () => openTrace(record), className: 'dashboard-trace-row' })}
            columns={[
              { title: t('run'), dataIndex: 'name', ellipsis: true, render: (value) => value || 'Unnamed run' },
              { title: t('subject'), render: (_, item) => item.agent_id || item.workflow_id || '—', ellipsis: true },
              { title: t('latency'), dataIndex: 'duration_ms', width: 106, sorter: (a, b) => (a.duration_ms ?? 0) - (b.duration_ms ?? 0), render: duration },
              { title: t('startTime'), dataIndex: 'start_time', width: 164, defaultSortOrder: 'descend' as const, sorter: (a, b) => compareTimestamp(a.start_time, b.start_time), render: formatDate },
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
