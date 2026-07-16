import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Collapse, Descriptions, Drawer, Input, Modal, Segmented, Select, Space, Table, Tag, Typography, type DescriptionsProps, type TableProps } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import { Markdown } from '@/shared/ui/Markdown'
import { currentUserQuery } from '@/features/auth'
import { hasScope } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue } from '@/shared/ui/MetadataDescriptions'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import {
  getApproval,
  getApprovals,
  getSkillSubmissionPreview,
  isSubmissionApproval,
  isWorkflowHitlApproval,
  resolveApproval,
  resumeApproval,
  resolveSubmissionApproval,
  type Approval,
  type ApprovalKind,
} from './api'
import { compactId, compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { useTranslation } from 'react-i18next'

const uploadPayload = (approval: Approval) => approval.payload ?? {}

const approvalTitle = (approval: Approval) => {
  const name = uploadPayload(approval).name
  if (typeof name === 'string' && name.trim()) return name
  if (approval.resource_type === 'skill') return 'Skill upload'
  if (approval.resource_type === 'mcp') return 'MCP server upload'
  if (approval.source_type === 'workflow') return approval.tool_name ?? approval.source_name ?? 'Workflow step'
  return approval.tool_name ?? approval.source_name ?? '-'
}

const workflowPauseType = (approval: Approval): string => {
  const fromField = approval.pause_type || approval.approval_type
  if (fromField) return String(fromField)
  const args = approval.tool_args
  if (args && typeof args.pause_type === 'string') return args.pause_type
  return 'confirmation'
}

const workflowPrompt = (approval: Approval): string => {
  const args = approval.tool_args
  if (args && typeof args.message === 'string' && args.message.trim()) return args.message
  return ''
}


type UserInputField = {
  name: string
  field_type?: string
  description?: string
  required?: boolean
}

const parseUserInputSchema = (approval: Approval): UserInputField[] => {
  const raw = approval.tool_args?.user_input_schema
  if (!Array.isArray(raw)) return []
  return raw.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const row = item as Record<string, unknown>
    const name = String(row.name ?? row.key ?? '').trim()
    if (!name) return []
    return [
      {
        name,
        field_type: row.field_type != null ? String(row.field_type) : row.type != null ? String(row.type) : 'str',
        description: row.description != null ? String(row.description) : '',
        required: Boolean(row.required ?? true),
      },
    ]
  })
}

const workflowOutputSeed = (approval: Approval): string => {
  const args = approval.tool_args
  if (!args) return ''
  for (const key of ['output', 'content', 'message', 'step_output']) {
    const value = args[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return ''
}


const approvalType = (approval: Approval) => {
  if (approval.resource_type === 'skill') return 'Skill upload'
  if (approval.resource_type === 'mcp') return 'MCP upload'
  if (approval.source_type === 'workflow') {
    const pause = workflowPauseType(approval)
    if (pause === 'user_input') return 'Workflow user input'
    if (pause === 'output_review') return 'Workflow output review'
    return 'Workflow confirmation'
  }
  return approval.approval_type ?? approval.source_type ?? '-'
}

const approvalPayload = (approval: Approval) => approval.payload ?? approval.tool_args

interface ApprovalIdentity {
  email: string
  id: string
}

const actorIdentity = (
  actor: Approval['submitted_by'] | Approval['resolved_by'],
  fallbackId?: string
): ApprovalIdentity => {
  if (typeof actor === 'object' && actor !== null) {
    return { email: actor.email || '', id: actor.id || fallbackId || '' }
  }
  if (typeof actor === 'string') {
    return { email: actor.includes('@') ? actor : '', id: actor || fallbackId || '' }
  }
  return { email: '', id: fallbackId || '' }
}

const submitter = (approval: Approval) => actorIdentity(approval.submitted_by, approval.user_id)
const approver = (approval: Approval) => actorIdentity(approval.resolved_by)

const statusLabel = (status: string) => status ? `${status.slice(0, 1).toUpperCase()}${status.slice(1)}` : '-'

/** HITL: resolution_data.note (Agno). Submissions: top-level rejection_reason. */
const rejectionReason = (approval: Approval) => {
  const note = approval.resolution_data?.note
  if (typeof note === 'string' && note.trim()) return note
  return approval.rejection_reason?.trim() || ''
}

const runStatus = (approval: Approval) => approval.run_status?.toUpperCase() ?? null

const optionalCopyable = (value?: string | null, empty = '-') => (value?.trim() ? <CopyableValue value={value} /> : empty)

function IdentityCell({ identity }: { identity: ApprovalIdentity }) {
  const label = identity.email || identity.id
  return <Typography.Text ellipsis={{ tooltip: label || undefined }}>{label || '—'}</Typography.Text>
}

const statusTag = (status: string) => (
  <Tag color={status === 'pending' ? 'warning' : status === 'approved' ? 'success' : 'error'}>{statusLabel(status)}</Tag>
)

function detailItems(approval: Approval, formatDate: (value?: string | number | null) => string, t: (key: string, options?: Record<string, unknown>) => string): { decision: DescriptionsProps['items']; people: DescriptionsProps['items']; request: DescriptionsProps['items'] } {
  const submitted = submitter(approval)
  const resolved = approver(approval)
  const payload = uploadPayload(approval)
  const isUpload = isSubmissionApproval(approval)
  const request: DescriptionsProps['items'] = [
    { key: 'approval-id', label: 'Approval ID', children: <CopyableValue value={approval.id} /> },
    { key: 'request-name', label: 'Request', children: approvalTitle(approval) },
    { key: 'request-type', label: 'Type', children: approvalType(approval) },
  ]
  if (isUpload) {
    request.push(
      { key: 'resource-type', label: 'Resource', children: approval.resource_type?.toUpperCase() || '-' },
      { key: 'visibility', label: 'Visibility', children: typeof payload.visibility === 'string' ? payload.visibility : '-' },
      { key: 'archive', label: 'Package', children: typeof payload.filename === 'string' ? payload.filename : '-' }
    )
  } else {
    request.push(
      { key: 'source', label: 'Source', children: approval.source_name ?? approval.source_type ?? '-' },
      { key: 'run', label: 'Run ID', children: optionalCopyable(approval.run_id) },
      { key: 'session', label: 'Session ID', children: optionalCopyable(approval.session_id) },
      { key: 'agent', label: 'Agent ID', children: optionalCopyable(approval.agent_id) },
      { key: 'team', label: 'Team ID', children: optionalCopyable(approval.team_id) },
      { key: 'workflow', label: 'Workflow ID', children: optionalCopyable(approval.workflow_id) },
      { key: 'schedule', label: 'Schedule ID', children: optionalCopyable(approval.schedule_id) }
    )
  }
  return {
    decision: [
      { key: 'status', label: 'Status', children: statusTag(approval.status) },
      { key: 'submitted-at', label: t('submittedAt'), children: formatDate(approval.created_at) },
      { key: 'resolved-at', label: t('resolvedAt'), children: formatDate(approval.resolved_at) },
      ...(approval.status === 'rejected' ? [{ key: 'rejection-reason', label: 'Rejection reason', children: rejectionReason(approval) || '-' }] : []),
      ...(runStatus(approval) ? [{ key: 'run-status', label: t('runStatus'), children: statusLabel(runStatus(approval) ?? '') }] : []),
    ],
    people: [
      { key: 'submitter-email', label: 'Submitter email', children: optionalCopyable(submitted.email) },
      { key: 'submitter-id', label: 'Submitter ID', children: optionalCopyable(submitted.id) },
      { key: 'approver-email', label: 'Approver email', children: optionalCopyable(resolved.email, 'Not assigned') },
      { key: 'approver-id', label: 'Approver ID', children: optionalCopyable(resolved.id, 'Not assigned') },
    ],
    request,
  }
}

const locationSearch = () => {
  const hashQueryIndex = window.location.hash.indexOf('?')
  return hashQueryIndex >= 0 ? window.location.hash.slice(hashQueryIndex) : window.location.search
}

export function ApprovalsPage() {
  const { t } = useTranslation('approvals')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const client = useQueryClient()
  const [searchStr, setSearchStr] = useState(locationSearch)
  const openedNotificationApprovalId = useRef<string | null>(null)
  const currentUser = useQuery(currentUserQuery())
  const canResolve = hasScope(currentUser.data, 'approvals:write')
  const [status, setStatus] = useState('pending')
  const [kind, setKind] = useState<ApprovalKind>('workflow')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selected, setSelected] = useState<Approval | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [approveOpen, setApproveOpen] = useState(false)
  const [userInputText, setUserInputText] = useState('')
  const [userInputValues, setUserInputValues] = useState<Record<string, string>>({})
  const [editedOutput, setEditedOutput] = useState('')
  const [markdownPreviewModes, setMarkdownPreviewModes] = useState<Record<string, 'raw' | 'markdown'>>({})
  const query = useQuery({
    queryKey: ['approvals', 'list', kind, status, page, pageSize],
    queryFn: () => getApprovals({ status, kind, page, limit: pageSize }),
    placeholderData: (previous) => previous,
  })
  const rows = useMemo(() => query.data?.data ?? [], [query.data?.data])
  const total = query.data?.meta.total_count ?? 0
  const notificationApprovalId = new URLSearchParams(searchStr).get('approval_id')
  useEffect(() => {
    const updateSearch = () => setSearchStr(locationSearch())
    window.addEventListener('hashchange', updateSearch)
    window.addEventListener('popstate', updateSearch)
    return () => {
      window.removeEventListener('hashchange', updateSearch)
      window.removeEventListener('popstate', updateSearch)
    }
  }, [])
  useEffect(() => {
    setPage(1)
  }, [status, kind])
  useEffect(() => {
    if (!notificationApprovalId || openedNotificationApprovalId.current === notificationApprovalId) return
    const approval = rows.find((item) => item.id === notificationApprovalId)
    if (approval) {
      openedNotificationApprovalId.current = notificationApprovalId
      if (isWorkflowHitlApproval(approval)) setKind('workflow')
      else if (isSubmissionApproval(approval)) setKind('upload')
      setSelected(approval)
      return
    }
    let cancelled = false
    void getApproval(notificationApprovalId)
      .then((row) => {
        if (cancelled || !row) return
        openedNotificationApprovalId.current = notificationApprovalId
        if (isWorkflowHitlApproval(row)) setKind('workflow')
        else if (isSubmissionApproval(row)) setKind('upload')
        else setKind('all')
        setSelected(row)
      })
      .catch(() => {
        // Missing or unauthorized approval — leave selection unchanged.
      })
    return () => {
      cancelled = true
    }
  }, [notificationApprovalId, rows])
  const skillPreview = useQuery({
    queryKey: ['approvals', 'skill-preview', selected?.id],
    queryFn: () => getSkillSubmissionPreview(selected?.id ?? ''),
    enabled: selected?.resource_type === 'skill' && selected.status === 'pending',
  })
  const refresh = () => client.invalidateQueries({ queryKey: ['approvals'] })
  const resolve = useMutation({
    mutationFn: ({
      approval,
      decision,
      rejectionReason: reason,
      resolutionData,
    }: {
      approval: Approval
      decision: 'approved' | 'rejected'
      rejectionReason?: string
      resolutionData?: Record<string, unknown>
    }) =>
      isSubmissionApproval(approval)
        ? resolveSubmissionApproval(approval.id, decision, reason)
        : resolveApproval(approval.id, decision, {
            rejectionReason: reason,
            resolutionData,
          }),
    onSuccess: async (row) => {
      setSelected(row)
      setRejectOpen(false)
      setRejectReason('')
      setApproveOpen(false)
      setUserInputText('')
      setUserInputValues({})
      setEditedOutput('')
      message.success(t('resolved', { status: row.status }))
      await refresh()
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : t('resolveFailed')),
  })
  const retryResume = useMutation({
    mutationFn: (approval: Approval) => resumeApproval(approval.id),
    onSuccess: async (row) => {
      setSelected(row)
      message.success(t('resumeRetryStarted'))
      await refresh()
    },
    onError: (error) => message.error(error instanceof Error ? error.message : t('resumeRetryFailed')),
  })
  const typeFilters = useMemo(() => {
    const values = new Set(rows.map((row) => approvalType(row)).filter((value) => value && value !== '-'))
    return [...values].sort().map((value) => ({ text: value, value }))
  }, [rows])

  const columns = useMemo<TableProps<Approval>['columns']>(
    () => [
      {
        title: 'Request',
        width: 240,
        sorter: (a, b) => approvalTitle(a).localeCompare(approvalTitle(b)),
        render: (_, row) => (
          <Space orientation="vertical" size={0}>
            <Typography.Text strong ellipsis>
              {approvalTitle(row)}
            </Typography.Text>
            <Typography.Text type="secondary" ellipsis>
              {compactId(row.id)}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: 'Type',
        width: 150,
        filters: typeFilters,
        onFilter: (value, row) => approvalType(row) === value,
        render: (_, row) => approvalType(row),
      },
      {
        title: 'Submitter',
        width: 210,
        ellipsis: true,
        sorter: (a, b) => {
          const left = submitter(a).email || submitter(a).id
          const right = submitter(b).email || submitter(b).id
          return left.localeCompare(right)
        },
        render: (_, row) => <IdentityCell identity={submitter(row)} />,
      },
      {
        title: 'Approver',
        width: 210,
        ellipsis: true,
        sorter: (a, b) => {
          const left = approver(a).email || approver(a).id
          const right = approver(b).email || approver(b).id
          return left.localeCompare(right)
        },
        render: (_, row) => <IdentityCell identity={approver(row)} />,
      },
      {
        title: 'Status',
        dataIndex: 'status',
        width: 120,
        filters: [
          { text: statusLabel('pending'), value: 'pending' },
          { text: statusLabel('approved'), value: 'approved' },
          { text: statusLabel('rejected'), value: 'rejected' },
        ],
        onFilter: (value, row) => row.status === value,
        render: statusTag,
      },
      {
        title: t('submittedAt'),
        dataIndex: 'created_at',
        width: 180,
        defaultSortOrder: 'descend',
        sorter: (a, b) => compareTimestamp(a.created_at, b.created_at),
        render: formatDate,
      },
      {
        title: t('resolvedAt'),
        dataIndex: 'resolved_at',
        width: 180,
        sorter: (a, b) => compareTimestamp(a.resolved_at, b.resolved_at),
        render: formatDate,
      },
    ],
    [formatDate, t, typeFilters]
  )

  const approvalActions = selected ? (
    <Space size={4}>
      {canResolve ? (
        <>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            disabled={selected.status !== 'pending'}
            loading={resolve.isPending}
            style={{ minWidth: 84 }}
            onClick={() => {
              if (isSubmissionApproval(selected)) {
                resolve.mutate({ approval: selected, decision: 'approved' })
                return
              }
              const pause = workflowPauseType(selected)
              if (pause === 'user_input' || pause === 'output_review') {
                setUserInputText('')
                const schema = parseUserInputSchema(selected)
                const seed: Record<string, string> = {}
                for (const field of schema) seed[field.name] = ''
                setUserInputValues(seed)
                setEditedOutput(workflowOutputSeed(selected))
                setApproveOpen(true)
                return
              }
              resolve.mutate({ approval: selected, decision: 'approved' })
            }}
          >
            {t('common:approve')}
          </Button>
          <Button
            danger
            icon={<CloseOutlined />}
            disabled={selected.status !== 'pending'}
            loading={resolve.isPending}
            style={{ minWidth: 84 }}
            onClick={() => setRejectOpen(true)}
          >
            {t('common:reject')}
          </Button>
          {!isSubmissionApproval(selected) && runStatus(selected) === 'ERROR' && (
            <Button loading={retryResume.isPending} onClick={() => retryResume.mutate(selected)}>
              {t('retryResume')}
            </Button>
          )}
        </>
      ) : null}
      {selected.source_type === 'workflow' && selected.workflow_id ? (
        <Button
          onClick={() => {
            window.location.hash = `#/workflow?workflow_id=${encodeURIComponent(selected.workflow_id!)}`
          }}
        >
          {t('openWorkflow')}
        </Button>
      ) : null}
    </Space>
  ) : null

  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('descriptionOnCall')}
        actions={
          <Space wrap>
            <Segmented
              value={kind}
              onChange={(value) => setKind(value as ApprovalKind)}
              options={[
                { value: 'workflow', label: t('kindWorkflow') },
                { value: 'upload', label: t('kindUpload') },
                { value: 'agent', label: t('kindAgent') },
                { value: 'all', label: t('kindAll') },
              ]}
            />
            <Select
              value={status}
              onChange={setStatus}
              style={{ minWidth: 140 }}
              options={[
                { value: '', label: t('allStatuses') },
                ...['pending', 'approved', 'rejected'].map((value) => ({
                  value,
                  label: statusLabel(value),
                })),
              ]}
            />
          </Space>
        }
      />
      <Card className="workbench-card">
        {kind === 'workflow' && status === 'pending' ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            title={t('workflowOnCallHint')}
          />
        ) : null}
        <Table<Approval>
          rowKey="id"
          dataSource={rows}
          loading={query.isLoading}
          scroll={{ x: 1290 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            showTotal: (value) => `${value}`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage)
              if (nextSize !== pageSize) {
                setPageSize(nextSize)
                setPage(1)
              }
            },
          }}
          rowClassName={(row) => (row.id === selected?.id ? 'selected-table-row' : '')}
          onRow={(row) => ({
            tabIndex: 0,
            role: 'button',
            'aria-label': t('viewApproval', { id: row.id }),
            onClick: () => setSelected(row),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelected(row)
              }
            },
          })}
          columns={columns}
        />
      </Card>
      <Drawer size={760} open={Boolean(selected)} onClose={() => setSelected(null)} title="Approval detail" extra={approvalActions}>
        {selected && (
          <>
            {selected.status === 'approved' && <Alert type="success" showIcon title={t('approved')} style={{ marginBottom: 16 }} />}
            {selected.status === 'rejected' && (
              <Alert
                type="error"
                showIcon
                title={t('rejected')}
                description={rejectionReason(selected) || t('noRejectReason')}
                style={{ marginBottom: 16 }}
              />
            )}
            {runStatus(selected) === 'ERROR' && (
              <Alert
                type="warning"
                showIcon
                title={t('resumeFailed')}
                description={t('resumeFailedDescription')}
                style={{ marginBottom: 16 }}
              />
            )}
            {(() => {
              const details = detailItems(selected, formatDate, t)
              return (
                <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                  <Card size="small" title="Decision" className="approval-detail-section">
                    <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={details.decision} />
                  </Card>
                  <Card size="small" title="People" className="approval-detail-section">
                    <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={details.people} />
                  </Card>
                  <Card size="small" title="Request" className="approval-detail-section">
                    <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={details.request} />
                  </Card>
                  <Card size="small" title="Request data" className="approval-detail-section">
                    <PayloadViewer value={approvalPayload(selected)} />
                  </Card>
                </Space>
              )
            })()}
            {canResolve && selected.resource_type === 'skill' && selected.status === 'pending' && (
              <Card
                size="small"
                title={t('zipPreview')}
                loading={skillPreview.isLoading}
                style={{ marginTop: 16 }}
              >
                {skillPreview.data && (
                  <>
                    <Table
                      size="small"
                      rowKey="name"
                      pagination={false}
                      dataSource={skillPreview.data.files}
                      columns={[
                        { title: t('common:file'), dataIndex: 'name', sorter: (a, b) => a.name.localeCompare(b.name) },
                        {
                          title: t('common:size'),
                          dataIndex: 'size',
                          width: 120,
                          sorter: (a, b) => a.size - b.size,
                          render: (size: number) => `${size} B`,
                        },
                      ]}
                    />
                    {Object.keys(skillPreview.data.previews).length > 0 && (
                      <Collapse
                        size="small"
                        style={{ marginTop: 12 }}
                        items={Object.entries(skillPreview.data.previews).map(([name, content]) => {
                          const supportsMarkdown = name.toLowerCase().endsWith('.md')
                          const mode = markdownPreviewModes[name] ?? 'raw'
                          return {
                            key: name,
                            label: name,
                            extra: supportsMarkdown ? (
                              <Segmented
                                size="small"
                                value={mode}
                                options={[
                                  { label: 'Raw', value: 'raw' },
                                  { label: 'Markdown', value: 'markdown' },
                                ]}
                                onClick={(event) => event.stopPropagation()}
                                onChange={(value) =>
                                  setMarkdownPreviewModes((current) => ({
                                    ...current,
                                    [name]: value as 'raw' | 'markdown',
                                  }))
                                }
                              />
                            ) : null,
                            children: mode === 'markdown' ? (
                              <div className="payload-viewer">
                                <Markdown content={content} openLinksInNewTab escapeRawHtml />
                              </div>
                            ) : (
                              <pre className="payload-viewer">{content}</pre>
                            ),
                          }
                        })}
                      />
                    )}
                  </>
                )}
                {skillPreview.isError && <p>{t('zipPreviewFailed')}</p>}
              </Card>
            )}
          </>
        )}
      </Drawer>
      <Modal
        open={approveOpen}
        title={
          selected && workflowPauseType(selected) === 'output_review'
            ? t('approveOutputReview')
            : t('approveUserInput')
        }
        okText={t('common:approve')}
        confirmLoading={resolve.isPending}
        okButtonProps={{
          disabled: (() => {
            if (!selected || workflowPauseType(selected) !== 'user_input') return false
            const schema = parseUserInputSchema(selected)
            if (!schema.length) return !userInputText.trim()
            return schema.some(
              (field) => field.required !== false && !(userInputValues[field.name] ?? '').trim()
            )
          })(),
        }}
        onCancel={() => {
          setApproveOpen(false)
          setUserInputText('')
          setEditedOutput('')
        }}
        onOk={() => {
          if (!selected) return
          const pause = workflowPauseType(selected)
          if (pause === 'user_input') {
            const schema = parseUserInputSchema(selected)
            const user_input = schema.length
              ? Object.fromEntries(
                  schema.map((field) => [field.name, (userInputValues[field.name] ?? '').trim()])
                )
              : { response: userInputText.trim() }
            resolve.mutate({
              approval: selected,
              decision: 'approved',
              resolutionData: { user_input },
            })
            return
          }
          if (pause === 'output_review') {
            resolve.mutate({
              approval: selected,
              decision: 'approved',
              resolutionData: { edited_output: editedOutput },
            })
            return
          }
          resolve.mutate({ approval: selected, decision: 'approved' })
        }}
      >
        {selected ? (
          <>
            {workflowPrompt(selected) ? (
              <Typography.Paragraph type="secondary">{workflowPrompt(selected)}</Typography.Paragraph>
            ) : null}
            {workflowPauseType(selected) === 'user_input' ? (
              parseUserInputSchema(selected).length ? (
                <Space orientation="vertical" style={{ width: '100%' }} size={10}>
                  {parseUserInputSchema(selected).map((field) => (
                    <div key={field.name}>
                      <Typography.Text strong>
                        {field.name}
                        {field.required === false ? '' : ' *'}
                      </Typography.Text>
                      {field.description ? (
                        <Typography.Paragraph type="secondary" style={{ marginBottom: 4 }}>
                          {field.description}
                        </Typography.Paragraph>
                      ) : null}
                      <Input.TextArea
                        rows={field.field_type === 'str' || !field.field_type ? 3 : 2}
                        value={userInputValues[field.name] ?? ''}
                        onChange={(event) =>
                          setUserInputValues((current) => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        placeholder={field.description || field.name}
                      />
                    </div>
                  ))}
                </Space>
              ) : (
                <Input.TextArea
                  rows={4}
                  value={userInputText}
                  onChange={(event) => setUserInputText(event.target.value)}
                  placeholder={t('userInputPlaceholder')}
                />
              )
            ) : (
              <Input.TextArea
                rows={8}
                value={editedOutput}
                onChange={(event) => setEditedOutput(event.target.value)}
                placeholder={t('editedOutputPlaceholder')}
              />
            )}
          </>
        ) : null}
      </Modal>
      <Modal
        open={rejectOpen}
        title={t('rejectApproval')}
        okText={t('confirmReject')}
        okButtonProps={{ danger: true, disabled: !rejectReason.trim() }}
        cancelText={t('common:cancel')}
        confirmLoading={resolve.isPending}
        styles={{ body: { paddingBottom: 8 }, footer: { marginTop: 20 } }}
        onCancel={() => {
          setRejectOpen(false)
          setRejectReason('')
        }}
        onOk={() => {
          if (selected) resolve.mutate({ approval: selected, decision: 'rejected', rejectionReason: rejectReason.trim() })
        }}
      >
        <Typography.Paragraph type="secondary">{t('rejectReasonHint')}</Typography.Paragraph>
        <div style={{ paddingBottom: 28 }}>
          <Input.TextArea
            rows={4}
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            placeholder={t('rejectReasonPlaceholder')}
            maxLength={2000}
            showCount
          />
        </div>
      </Modal>
    </main>
  )
}
