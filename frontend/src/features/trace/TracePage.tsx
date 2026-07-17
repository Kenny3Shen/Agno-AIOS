import { useEffect, useMemo, useState } from 'react'
import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
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
import { DeploymentUnitOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { currentUserQuery } from '@/features/auth'
import { listSessions, sessionsQuery } from '@/features/chat'
import { roleOf } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { FormattedContentCard } from '@/shared/ui/FormattedContentCard'
import { useFormatDate } from '@/shared/lib/format'
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
import { useTranslation } from 'react-i18next'

interface RunSpanTreeNode extends TreeDataNode {
  kind: 'span'
  traceId: string
  runId: string
  spanId?: string
  children?: RunSpanTreeNode[]
}

const SESSION_PAGE_SIZE = 8
/** When archive filter is on, fetch a bounded window then filter client-side. */
const ARCHIVE_SESSION_FETCH_LIMIT = 200
/** Cap background chat-session walk (chat sessionsQuery pages) for archive/preview merge. */
const MAX_CHAT_SESSION_PAGES = 3
const RUN_PAGE_SIZE = 6
const { RangePicker } = DatePicker

function initialRange(start: string, end: string): [Dayjs, Dayjs] | null {
  const startValue = dayjs(start)
  const endValue = dayjs(end)
  return startValue.isValid() && endValue.isValid() ? [startValue, endValue] : null
}

function spanNodes(
  nodes: SpanTreeNode[],
  traceId: string,
  runId: string,
  t: (key: string, options?: Record<string, unknown>) => string
): RunSpanTreeNode[] {
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
            <strong>{t('spanLabel', { name: node.span.name || t('unnamed') })}</strong>
            {input && <small>{input}</small>}
          </div>
          <span>
            <Tag color={node.span.status_code === 'ERROR' ? 'error' : 'success'}>{node.span.status_code}</Tag>
            {node.span.duration}
          </span>
        </div>
      ),
      children: spanNodes(node.children ?? [], traceId, runId, t),
    }
  })
}

function runSpanTree(
  runs: TraceRun[],
  detailsByTraceId: Map<string, SpanTreeNode[]>,
  formatDate: (value?: string | number | null) => string,
  t: (key: string, options?: Record<string, unknown>) => string
): RunSpanTreeNode[] {
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
              <strong>
                {t('runRootLabel', { name: root.span.name || run.name || t('unnamed') })}
              </strong>
              <small>{formatDate(run.startTime)}</small>
            </div>
            <span>
              <Tag color={run.status === 'ERROR' ? 'error' : 'success'}>{run.status}</Tag>
              {run.duration}
            </span>
          </div>
        ),
        children: spanNodes(root.children ?? [], run.traceId, run.runId, t),
        isLeaf: false,
      },
    ]
  })
}

export function TracePage() {
  const { t } = useTranslation('trace')
  const formatDate = useFormatDate()
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
  const archiveScoped = archiveFilter !== 'all'
  // "all": infinite chat walk for titles (existing). Archive tabs: one SQL page of
  // active-or-archived chat rows (archived_only / default exclude) so filter flags
  // are accurate without multi-page client walks.
  const chatSessions = useInfiniteQuery({
    ...sessionsQuery({ includeArchived: true, userId: effectiveUserId || undefined }),
    enabled: !archiveScoped,
  })
  const chatArchiveWindow = useQuery({
    queryKey: [
      'chat',
      'sessions',
      'trace-archive-window',
      archiveFilter,
      effectiveUserId,
      ARCHIVE_SESSION_FETCH_LIMIT,
    ],
    enabled: archiveScoped,
    queryFn: () =>
      listSessions({
        includeArchived: archiveFilter === 'archived',
        archivedOnly: archiveFilter === 'archived',
        userId: effectiveUserId || undefined,
        page: 1,
        limit: ARCHIVE_SESSION_FETCH_LIMIT,
      }),
  })
  const chatSessionPageCount = chatSessions.data?.pages.length ?? 0
  const {
    hasNextPage: chatSessionsHasNextPage,
    isFetchingNextPage: chatSessionsFetchingNext,
    fetchNextPage: fetchNextChatSessionPage,
  } = chatSessions
  useEffect(() => {
    if (archiveScoped) return
    if (
      chatSessionPageCount < MAX_CHAT_SESSION_PAGES &&
      chatSessionsHasNextPage &&
      !chatSessionsFetchingNext
    ) {
      void fetchNextChatSessionPage()
    }
  }, [
    archiveScoped,
    chatSessionPageCount,
    chatSessionsHasNextPage,
    chatSessionsFetchingNext,
    fetchNextChatSessionPage,
  ])
  // Default: true server page/limit. Archive tabs: bounded summaries + chat archive window.
  const summaries = useQuery(
    traceSessionsQuery({
      session_id: filters.session_id,
      run_id: filters.run_id,
      user_id: effectiveUserId,
      status: filters.status,
      start_time: filters.start_time,
      end_time: filters.end_time,
      page: archiveScoped ? 1 : sessionPage,
      limit: archiveScoped ? ARCHIVE_SESSION_FETCH_LIMIT : SESSION_PAGE_SIZE,
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
  const chatSessionItems = useMemo(() => {
    if (archiveScoped) return chatArchiveWindow.data?.data ?? []
    return chatSessions.data?.pages.flatMap((page) => page.data) ?? []
  }, [archiveScoped, chatArchiveWindow.data, chatSessions.data])
  const sessions = useMemo(
    () => filterSessionsByArchive(mergeTraceSessions(chatSessionItems, summaries.data?.data ?? []), archiveFilter),
    [archiveFilter, chatSessionItems, summaries.data?.data]
  )
  const visibleSessions = useMemo(() => {
    if (!archiveScoped) return sessions
    return sessions.slice((sessionPage - 1) * SESSION_PAGE_SIZE, sessionPage * SESSION_PAGE_SIZE)
  }, [archiveScoped, sessionPage, sessions])
  const chatArchiveTruncated = Boolean(
    archiveScoped &&
      chatArchiveWindow.data &&
      chatArchiveWindow.data.meta.total_count > chatArchiveWindow.data.data.length
  )
  const summariesTruncated = Boolean(
    archiveScoped &&
      summaries.data &&
      (summaries.data.meta.total_count ?? 0) > (summaries.data.data?.length ?? 0)
  )
  const archiveWindowTruncated = chatArchiveTruncated || summariesTruncated
  const sessionTotal = archiveScoped
    ? sessions.length
    : (summaries.data?.meta.total_count ?? sessions.length)
  const runs = useMemo(
    () => groupRuns(selectedTraceList.data?.data ?? [], selectedSession),
    [selectedSession, selectedTraceList.data?.data]
  )
  const visibleRuns = runs
  const statusFilterTruncated = Boolean(
    filters.status && (selectedTraceList.data?.meta.truncated || summaries.data?.meta.truncated)
  )
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
  const runTreeData = useMemo(() => runSpanTree(visibleRuns, treeData, formatDate, t), [formatDate, t, treeData, visibleRuns])
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
  const selectedSessionMeta = useMemo(
    () => sessions.find((session) => session.sessionId === selectedSession) ?? null,
    [selectedSession, sessions],
  )
  const openSelectedWorkflow = () => {
    const workflowId = String(selectedSessionMeta?.workflowId || '').trim()
    if (!workflowId) return
    void router.history.push(`/workflow?workflow_id=${encodeURIComponent(workflowId)}`)
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
        title={t('title')}
        description={t('description')}
        actions={
          <Space size={8} wrap>
            {selectedSessionMeta?.workflowId ? (
              <Button icon={<DeploymentUnitOutlined />} onClick={openSelectedWorkflow}>
                {t('openWorkflow')}
              </Button>
            ) : null}
            <Button
              icon={<ReloadOutlined />}
              loading={chatSessions.isFetching || summaries.isFetching || selectedTraceList.isFetching}
              onClick={refresh}
            >
              {t('common:refresh')}
            </Button>
          </Space>
        }
      />
      <Card className="workbench-card trace-toolbar">
        <div className="trace-filter-layout">
          <div className="trace-filter-identifiers">
            <Input value={sessionInput} onChange={(event) => setSessionInput(event.target.value)} placeholder={t('sessionIdPlaceholder')} allowClear />
            <Input value={runInput} onChange={(event) => setRunInput(event.target.value)} placeholder={t('runIdPlaceholder')} allowClear />
            <Input
              aria-label="User ID"
              value={isAdmin ? userInput : (currentUser.data?.id ?? '')}
              onChange={(event) => setUserInput(event.target.value)}
              placeholder={t('userIdPlaceholder')}
              disabled={!isAdmin}
              allowClear={isAdmin}
            />
            <Select
              value={status}
              onChange={setStatus}
              options={[{ value: '', label: t('allStatus') }, { value: 'OK', label: t('statusOk') }, { value: 'ERROR', label: t('statusError') }, { value: 'UNSET', label: t('statusUnset') }]}
            />
          </div>
          <div className="trace-filter-actions">
            <Select<SessionArchiveFilter>
              aria-label="Session archive filter"
              value={archiveFilter}
              onChange={(value) => {
                setArchiveFilter(value)
                setSessionPage(1)
              }}
              options={[
                { value: 'all', label: t('allSessions') },
                { value: 'active', label: t('activeSessions') },
                { value: 'archived', label: t('archivedSessions') },
              ]}
            />
            <RangePicker
              aria-label="Time range"
              showTime
              value={timeRange}
              onChange={(value) => setTimeRange(value as [Dayjs, Dayjs] | null)}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={apply}>
              {t('common:query')}
            </Button>
            <Button onClick={reset}>{t('common:reset')}</Button>
          </div>
          {!isAdmin && (
            <Typography.Text className="trace-filter-hint" type="secondary">
              {t('ownOnly')}
            </Typography.Text>
          )}
        </div>
      </Card>
      {statusFilterTruncated ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('statusFilterTruncated')}
        />
      ) : null}
      {archiveWindowTruncated ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('archiveWindowTruncated')}
        />
      ) : null}
      <Splitter className="trace-workbench-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
        <Splitter.Panel defaultSize={vertical ? '28%' : '24%'} min={vertical ? 180 : 220}>
          <Card className="workbench-card splitter-panel-card" title={t('sessions')} extra={<Tag>{sessions.length}</Tag>}>
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
                      <strong>
                        {session.workflowId ? '[WF] ' : ''}
                        {session.name}
                      </strong>
                      <span>
                        {session.archived && <Tag>{t('archivedTag')}</Tag>}
                        {session.workflowId ? <Tag color="blue">{t('workflowTag')}</Tag> : null}
                        {t('runsCount', { count: session.runCount })}
                        {session.context ? ` · ${session.context}` : ''}
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
                total={sessionTotal}
                showSizeChanger={false}
                onChange={changeSessionPage}
              />
            </div>
          </Card>
        </Splitter.Panel>
        <Splitter.Panel defaultSize={vertical ? '34%' : '32%'} min={vertical ? 240 : 340}>
          <Card
            className="workbench-card splitter-panel-card"
            title={t('runsAndSpans')}
            extra={<Tag>{selectedTraceList.data?.meta.total_count ?? 0}</Tag>}
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
                total={selectedTraceList.data?.meta.total_count ?? 0}
                showSizeChanger={false}
                onChange={changeRunPage}
              />
            </div>
          </Card>
        </Splitter.Panel>
        <Splitter.Panel defaultSize={vertical ? '38%' : '44%'} min={vertical ? 300 : 420}>
          <Card
            className="workbench-card splitter-panel-card"
            title={t('detail')}
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
  const { t } = useTranslation('trace')
  const formatDate = useFormatDate()
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
          label: t('info'),
          children: (
            <Splitter className="trace-info-splitter" orientation="vertical">
              <Splitter.Panel defaultSize="50%" min="20%">
                <FormattedContentCard title={t('input')} value={span.parsed?.input} />
              </Splitter.Panel>
              <Splitter.Panel defaultSize="50%" min="30%">
                <FormattedContentCard title={t('output')} value={span.parsed?.output} />
              </Splitter.Panel>
            </Splitter>
          ),
        },
        {
          key: 'metadata',
          label: t('metadata'),
          children: (
            <MetadataDescriptions
              items={[
                { key: 'session-id', label: t('sessionId'), children: <CopyableValue value={span.session_id} /> },
                { key: 'run-id', label: t('runId'), children: <CopyableValue value={span.run_id} /> },
                { key: 'span-id', label: t('spanId'), children: <CopyableValue value={span.span_id} /> },
                { key: 'parent-span-id', label: t('parentSpanId'), children: <CopyableValue value={span.parent_span_id} /> },
                { key: 'operation', label: t('operation'), children: span.name || '-' },
                {
                  key: 'status',
                  label: t('status'),
                  children: <Tag color={span.status_code === 'ERROR' ? 'error' : 'success'}>{span.status_code}</Tag>,
                },
                { key: 'duration', label: t('duration'), children: span.duration || '-' },
                { key: 'started', label: t('started'), children: formatDate(span.start_time) },
              ]}
              value={metadata}
            />
          ),
        },
      ]}
    />
  )
}
