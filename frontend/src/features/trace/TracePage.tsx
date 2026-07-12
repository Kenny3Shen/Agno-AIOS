import { useEffect, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Grid,
  Input,
  Pagination,
  Select,
  Space,
  Splitter,
  Tabs,
  Tag,
  Tree,
  Typography,
  type TreeDataNode,
  type TreeProps,
} from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { currentUserQuery } from '@/features/auth'
import { sessionsQuery } from '@/features/chat'
import { roleOf } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { FormattedContentCard } from '@/shared/ui/FormattedContentCard'
import { formatDate } from '@/shared/lib/format'
import { traceQuery, tracesQuery, traceSessionsQuery } from './queries'
import {
  buildTraceSearch,
  emptyTraceFilters,
  filterSessionsByArchive,
  groupRuns,
  mergeTraceSessions,
  parseTraceSearch,
  previewSpanValue,
  type SessionArchiveFilter,
} from './utils'
import type { Span, SpanTreeNode, TraceFilters, TraceRun } from './types'

interface RunSpanTreeNode extends TreeDataNode {
  kind: 'span'
  traceId: string
  runId: string
  spanId?: string
  children?: RunSpanTreeNode[]
}

const SESSION_PAGE_SIZE = 8
const RUN_PAGE_SIZE = 6
const { RangePicker } = DatePicker
const seconds = (milliseconds: number) => `${(Number(milliseconds) / 1_000).toFixed(2)} s`

function initialRange(start: string, end: string): [Dayjs, Dayjs] | null {
  const startValue = dayjs(start)
  const endValue = dayjs(end)
  return startValue.isValid() && endValue.isValid() ? [startValue, endValue] : null
}

function spanNodes(nodes: SpanTreeNode[], traceId: string, runId: string): RunSpanTreeNode[] {
  return nodes.map((node) => {
    const input = previewSpanValue(node.span.parsed?.input)
    return {
      key: `span:${traceId}:${node.span.span_id}`,
      kind: 'span',
      traceId,
      runId,
      spanId: node.span.span_id,
      title: (
        <div className="span-tree-node">
          <div className="span-tree-copy">
            <strong>Span · {node.span.name || 'Unnamed'}</strong>
            {input && <small>{input}</small>}
          </div>
          <span>
            <Tag color={node.span.status_code === 'ERROR' ? 'error' : 'success'}>{node.span.status_code}</Tag>
            {seconds(node.span.duration_ms)}
          </span>
        </div>
      ),
      children: spanNodes(node.children ?? [], traceId, runId),
    }
  })
}

function runSpanTree(runs: TraceRun[], detailsByTraceId: Map<string, SpanTreeNode[]>): RunSpanTreeNode[] {
  return runs.flatMap((run) => {
    const root = detailsByTraceId.get(run.traceId)?.[0]
    if (!root) return []
    return [
      {
        key: `span:${run.traceId}:${root.span.span_id}`,
        kind: 'span',
        traceId: run.traceId,
        runId: run.runId,
        spanId: root.span.span_id,
        title: (
          <div className="run-tree-node">
            <div>
              <strong>Run root · {root.span.name || run.name || 'Unnamed'}</strong>
              <small>
                {formatDate(run.startTime)} · {seconds(run.durationMs)} · {run.status}
              </small>
            </div>
            <span>
              <Tag color={run.status === 'ERROR' ? 'error' : 'success'}>{run.status}</Tag>
            </span>
          </div>
        ),
        children: spanNodes(root.children ?? [], run.traceId, run.runId),
        isLeaf: false,
      },
    ]
  })
}

export function TracePage() {
  const router = useRouter()
  const screens = Grid.useBreakpoint()
  const vertical = screens.lg === false
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const urlState = useMemo(() => parseTraceSearch(searchStr), [searchStr])
  const urlFilters = urlState.filters
  const {
    session_id: urlSessionId,
    run_id: urlRunId,
    user_id: urlUserId,
    status: urlStatus,
    start_time: urlStartTime,
    end_time: urlEndTime,
  } = urlFilters
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const [sessionInput, setSessionInput] = useState(urlFilters.session_id)
  const [runInput, setRunInput] = useState(urlFilters.run_id)
  const [userInput, setUserInput] = useState(urlFilters.user_id)
  const [status, setStatus] = useState(urlFilters.status)
  const [timeRange, setTimeRange] = useState<[Dayjs, Dayjs] | null>(() => initialRange(urlFilters.start_time, urlFilters.end_time))
  const [archiveFilter, setArchiveFilter] = useState<SessionArchiveFilter>('all')
  const [filters, setFilters] = useState<TraceFilters>(urlFilters)
  const [selectedSession, setSelectedSession] = useState(urlState.selectedSession)
  const [activeTraceId, setActiveTraceId] = useState(urlState.traceId)
  const [selectedSpanId, setSelectedSpanId] = useState('')
  const [expandedSpanKeys, setExpandedSpanKeys] = useState<string[]>([])
  const [sessionPage, setSessionPage] = useState(1)
  const [runPage, setRunPage] = useState(1)
  const effectiveUserId = isAdmin ? filters.user_id : (currentUser.data?.id ?? '')
  const chatSessions = useQuery(sessionsQuery(true, effectiveUserId || undefined))
  const summaries = useQuery(
    traceSessionsQuery({
      session_id: filters.session_id,
      run_id: filters.run_id,
      user_id: effectiveUserId,
      status: filters.status,
      start_time: filters.start_time,
      end_time: filters.end_time,
    })
  )
  // A selected run is a UI detail state, not a trace-list filter.  Filtering
  // this request by selectedRun collapsed the whole session to one run after
  // a user clicked the tree.
  const hasRunSelection = Boolean(selectedSession || filters.run_id)
  const selectedTraceList = useQuery({
    ...tracesQuery({ ...filters, user_id: effectiveUserId, session_id: selectedSession, page: runPage, limit: RUN_PAGE_SIZE }),
    enabled: hasRunSelection,
  })
  const sessions = useMemo(
    () => filterSessionsByArchive(mergeTraceSessions(chatSessions.data ?? [], summaries.data?.items ?? []), archiveFilter),
    [archiveFilter, chatSessions.data, summaries.data?.items]
  )
  const visibleSessions = useMemo(
    () => sessions.slice((sessionPage - 1) * SESSION_PAGE_SIZE, sessionPage * SESSION_PAGE_SIZE),
    [sessionPage, sessions]
  )
  const runs = useMemo(
    () => groupRuns(selectedTraceList.data?.items ?? [], selectedSession),
    [selectedSession, selectedTraceList.data?.items]
  )
  const visibleRuns = runs
  const detailTraceIds = useMemo(
    () => [...new Set([...visibleRuns.map((run) => run.traceId), activeTraceId].filter(Boolean))],
    [activeTraceId, visibleRuns]
  )
  const detailQueries = useQueries({ queries: detailTraceIds.map((traceId) => traceQuery(traceId)) })
  const detailsByTraceId = useMemo(
    () => new Map(detailTraceIds.map((traceId, index) => [traceId, detailQueries[index]?.data])),
    [detailQueries, detailTraceIds]
  )
  const treeData = useMemo(
    () => new Map(detailTraceIds.map((traceId, index) => [traceId, detailQueries[index]?.data?.tree ?? []])),
    [detailQueries, detailTraceIds]
  )
  const runTreeData = useMemo(() => runSpanTree(visibleRuns, treeData), [treeData, visibleRuns])
  const activeDetail = detailsByTraceId.get(activeTraceId)
  const selectedSpan = activeDetail?.spans.find((span) => span.span_id === selectedSpanId) ?? null

  useEffect(() => {
    setSessionInput(urlSessionId)
    setRunInput(urlRunId)
    setUserInput(urlUserId)
    setStatus(urlStatus)
    setTimeRange(initialRange(urlStartTime, urlEndTime))
    setFilters({
      session_id: urlSessionId,
      run_id: urlRunId,
      user_id: urlUserId,
      status: urlStatus,
      start_time: urlStartTime,
      end_time: urlEndTime,
    })
    setSessionPage(1)
  }, [urlSessionId, urlRunId, urlUserId, urlStatus, urlStartTime, urlEndTime])

  useEffect(() => {
    setSelectedSession(urlState.selectedSession)
    setActiveTraceId(urlState.traceId)
    setSelectedSpanId('')
    setExpandedSpanKeys([])
    setRunPage(1)
  }, [urlState.selectedSession, urlState.traceId])

  useEffect(() => {
    if (!activeTraceId || selectedSpanId || !activeDetail) return
    const rootSpanId = activeDetail.tree[0]?.span.span_id
    if (rootSpanId) setSelectedSpanId(rootSpanId)
  }, [activeDetail, activeTraceId, selectedSpanId])

  const navigate = (next: TraceFilters, nextSelectedSession = '', traceId = '') => {
    const query = buildTraceSearch(next, nextSelectedSession, traceId)
    void router.history.push(`/trace${query ? `?${query}` : ''}`)
  }
  const selectSession = (sessionId: string) => {
    setSelectedSession(sessionId)
    setActiveTraceId('')
    setSelectedSpanId('')
    setExpandedSpanKeys([])
    setRunPage(1)
    navigate(filters, sessionId)
  }
  const apply = () => {
    const next = {
      session_id: sessionInput.trim(),
      run_id: runInput.trim(),
      user_id: isAdmin ? userInput.trim() : (currentUser.data?.id ?? ''),
      status,
      start_time: timeRange?.[0].toISOString() ?? '',
      end_time: timeRange?.[1].toISOString() ?? '',
    }
    setFilters(next)
    setSelectedSession(next.session_id)
    setActiveTraceId('')
    setSelectedSpanId('')
    setExpandedSpanKeys([])
    setSessionPage(1)
    setRunPage(1)
    navigate(next)
  }
  const reset = () => {
    const next = { ...emptyTraceFilters(), user_id: isAdmin ? '' : (currentUser.data?.id ?? '') }
    setSessionInput('')
    setRunInput('')
    setUserInput(next.user_id)
    setStatus('')
    setTimeRange(null)
    setFilters(next)
    setSelectedSession('')
    setActiveTraceId('')
    setSelectedSpanId('')
    setExpandedSpanKeys([])
    setSessionPage(1)
    setRunPage(1)
    navigate(next)
  }
  const refresh = () => {
    void Promise.all([chatSessions.refetch(), summaries.refetch(), selectedTraceList.refetch()])
  }
  const changeSessionPage = (page: number) => {
    setSessionPage(page)
  }
  const changeRunPage = (page: number) => {
    setRunPage(page)
    setActiveTraceId('')
    setSelectedSpanId('')
  }
  const selectTreeNode: TreeProps<RunSpanTreeNode>['onSelect'] = (_, info) => {
    if (info.node.kind === 'span' && info.node.spanId) {
      if (info.node.traceId !== activeTraceId) {
        setActiveTraceId(info.node.traceId)
        navigate(filters, selectedSession, info.node.traceId)
      }
      setSelectedSpanId(info.node.spanId)
    }
  }
  const expandTreeNode: TreeProps<RunSpanTreeNode>['onExpand'] = (keys) => {
    const expandedKeys = keys.map(String)
    setExpandedSpanKeys(expandedKeys.filter((key) => key.startsWith('span:')))
  }

  return (
    <main className="page trace-page">
      <PageHeader
        title="Trace Observability"
        description="从 Session、Run 到 Span 的端到端观测与调试"
        actions={
          <Button
            icon={<ReloadOutlined />}
            loading={chatSessions.isFetching || summaries.isFetching || selectedTraceList.isFetching}
            onClick={refresh}
          >
            刷新
          </Button>
        }
      />
      <Card className="workbench-card trace-toolbar">
        <div className="trace-filter-layout">
          <div className="trace-filter-identifiers">
            <Input value={sessionInput} onChange={(event) => setSessionInput(event.target.value)} placeholder="Session ID" allowClear />
            <Input value={runInput} onChange={(event) => setRunInput(event.target.value)} placeholder="Run ID" allowClear />
            <Input
              aria-label="User ID"
              value={isAdmin ? userInput : (currentUser.data?.id ?? '')}
              onChange={(event) => setUserInput(event.target.value)}
              placeholder="User ID"
              disabled={!isAdmin}
              allowClear={isAdmin}
            />
            <Select
              value={status}
              onChange={setStatus}
              options={[{ value: '', label: 'All status' }, { value: 'OK' }, { value: 'ERROR' }, { value: 'UNSET' }]}
            />
          </div>
          <div className="trace-filter-actions">
            <Select<SessionArchiveFilter>
              aria-label="Session archive filter"
              value={archiveFilter}
              onChange={setArchiveFilter}
              options={[
                { value: 'all', label: '全部 Session' },
                { value: 'active', label: '活跃 Session' },
                { value: 'archived', label: '已归档 Session' },
              ]}
            />
            <RangePicker
              aria-label="Time range"
              showTime
              value={timeRange}
              onChange={(value) => setTimeRange(value as [Dayjs, Dayjs] | null)}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={apply}>
              查询
            </Button>
            <Button onClick={reset}>重置</Button>
          </div>
          {!isAdmin && (
            <Typography.Text className="trace-filter-hint" type="secondary">
              仅可查看自己的 Trace
            </Typography.Text>
          )}
        </div>
      </Card>
      <Splitter className="trace-workbench-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
        <Splitter.Panel defaultSize={vertical ? '28%' : '24%'} min={vertical ? 180 : 220}>
          <Card className="workbench-card splitter-panel-card" title="Sessions" extra={<Tag>{sessions.length}</Tag>}>
            <div className="trace-paginated-list">
              <div className="trace-choice-list">
                {visibleSessions.length > 0 ? (
                  visibleSessions.map((session) => (
                    <button
                      key={session.sessionId}
                      type="button"
                      className={`trace-choice ${session.sessionId === selectedSession ? 'selected' : ''}`}
                      aria-pressed={session.sessionId === selectedSession}
                      onClick={() => selectSession(session.sessionId)}
                    >
                      <strong>{session.name}</strong>
                      <span>
                        {session.archived && <Tag>Archived</Tag>}
                        {session.runCount} runs{session.context ? ` · ${session.context}` : ''}
                      </span>
                      <small>{formatDate(session.latestAt)}</small>
                    </button>
                  ))
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />
                )}
              </div>
              <Pagination
                size="small"
                align="center"
                current={sessionPage}
                pageSize={SESSION_PAGE_SIZE}
                total={sessions.length}
                showSizeChanger={false}
                onChange={changeSessionPage}
              />
            </div>
          </Card>
        </Splitter.Panel>
        <Splitter.Panel defaultSize={vertical ? '34%' : '32%'} min={vertical ? 240 : 340}>
          <Card
            className="workbench-card splitter-panel-card"
            title="Runs & Spans"
            extra={<Tag>{selectedTraceList.data?.total_count ?? 0}</Tag>}
          >
            <div className="trace-paginated-list">
              <Tree<RunSpanTreeNode>
                className="run-span-tree"
                blockNode
                showLine
                treeData={runTreeData}
                expandedKeys={expandedSpanKeys}
                selectedKeys={selectedSpanId ? [`span:${activeTraceId}:${selectedSpanId}`] : []}
                onSelect={selectTreeNode}
                onExpand={expandTreeNode}
              />
              <Pagination
                size="small"
                align="center"
                current={runPage}
                pageSize={RUN_PAGE_SIZE}
                total={selectedTraceList.data?.total_count ?? 0}
                showSizeChanger={false}
                onChange={changeRunPage}
              />
            </div>
          </Card>
        </Splitter.Panel>
        <Splitter.Panel defaultSize={vertical ? '38%' : '44%'} min={vertical ? 300 : 420}>
          <Card
            className="workbench-card splitter-panel-card"
            title="Detail"
            extra={
              selectedSpan && (
                <Space>
                  <Typography.Text type="secondary">{selectedSpan.name}</Typography.Text>
                  <Tag color={selectedSpan.status_code === 'ERROR' ? 'error' : 'success'}>{selectedSpan.status_code}</Tag>
                </Space>
              )
            }
          >
            {selectedSpan ? <SpanDetailTabs span={selectedSpan} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />}
          </Card>
        </Splitter.Panel>
      </Splitter>
    </main>
  )
}

function SpanDetailTabs({ span }: { span: Span }) {
  const metadata = Object.fromEntries(
    Object.entries({ metadata: span.parsed?.metadata, attributes: span.attributes, events: span.events }).filter(
      ([, value]) => value != null && (!Array.isArray(value) || value.length > 0)
    )
  )
  return (
    <Tabs
      className="trace-detail-tabs"
      size="small"
      destroyOnHidden
      items={[
        {
          key: 'info',
          label: 'Info',
          children: (
            <Splitter className="trace-info-splitter" orientation="vertical">
              <Splitter.Panel defaultSize="50%" min="20%">
                <FormattedContentCard title="Input" value={span.parsed?.input} />
              </Splitter.Panel>
              <Splitter.Panel defaultSize="50%" min="30%">
                <FormattedContentCard title="Output" value={span.parsed?.output} />
              </Splitter.Panel>
            </Splitter>
          ),
        },
        {
          key: 'metadata',
          label: 'Metadata',
          children: (
            <MetadataDescriptions
              items={[
                { key: 'session-id', label: 'Session ID', children: <CopyableValue value={span.session_id} /> },
                { key: 'run-id', label: 'Run ID', children: <CopyableValue value={span.run_id} /> },
                { key: 'span-id', label: 'Span ID', children: <CopyableValue value={span.span_id} /> },
                { key: 'parent-span-id', label: 'Parent Span ID', children: <CopyableValue value={span.parent_span_id} /> },
                { key: 'operation', label: 'Operation', children: span.name || '-' },
                {
                  key: 'status',
                  label: 'Status',
                  children: <Tag color={span.status_code === 'ERROR' ? 'error' : 'success'}>{span.status_code}</Tag>,
                },
                { key: 'duration', label: 'Duration', children: `${Number(span.duration_ms).toFixed(1)} ms` },
                { key: 'started', label: 'Started', children: formatDate(span.start_time) },
              ]}
              value={metadata}
            />
          ),
        },
      ]}
    />
  )
}
