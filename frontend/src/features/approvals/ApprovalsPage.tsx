import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Collapse, Descriptions, Drawer, Input, Modal, Segmented, Select, Space, Table, Tag, Typography, type DescriptionsProps, type TableProps } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import XMarkdown from '@ant-design/x-markdown'
import { currentUserQuery } from '@/features/auth'
import { hasScope } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue } from '@/shared/ui/MetadataDescriptions'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import {
  getApprovals,
  getSkillSubmissionPreview,
  isSubmissionApproval,
  resolveApproval,
  resumeApproval,
  resolveSubmissionApproval,
  type Approval,
} from './api'
import { compactId, compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { useTranslation } from 'react-i18next'

const uploadPayload = (approval: Approval) => approval.payload ?? {}

const approvalTitle = (approval: Approval) => {
  const name = uploadPayload(approval).name
  if (typeof name === 'string' && name.trim()) return name
  if (approval.resource_type === 'skill') return 'Skill upload'
  if (approval.resource_type === 'mcp') return 'MCP server upload'
  return approval.tool_name ?? approval.source_name ?? '-'
}

const approvalType = (approval: Approval) => {
  if (approval.resource_type === 'skill') return 'Skill upload'
  if (approval.resource_type === 'mcp') return 'MCP upload'
  return approval.approval_type ?? approval.source_type ?? '-'
}

const approvalPayload = (approval: Approval) => approval.payload ?? approval.tool_args

interface ApprovalIdentity {
  email: string
  id: string
}

const actorIdentity = (
  actor: Approval['submitted_by'] | Approval['resolved_by'],
  legacyEmail?: string,
  fallbackId?: string
): ApprovalIdentity => {
  if (typeof actor === 'object' && actor !== null) return { email: actor.email || legacyEmail || '', id: actor.id || fallbackId || '' }
  if (typeof actor === 'string') return { email: legacyEmail || (actor.includes('@') ? actor : ''), id: actor || fallbackId || '' }
  return { email: legacyEmail || '', id: fallbackId || '' }
}

const submitter = (approval: Approval) => actorIdentity(approval.submitted_by, approval.submitted_by_email, approval.user_id)
const approver = (approval: Approval) => actorIdentity(approval.resolved_by, approval.resolved_by_email)

const statusLabel = (status: string) => status ? `${status.slice(0, 1).toUpperCase()}${status.slice(1)}` : '-'

const rejectionReason = (approval: Approval) =>
  approval.rejection_reason ?? (typeof approval.resolution_data?.rejection_reason === 'string' ? approval.resolution_data.rejection_reason : '')

const resumeStatus = (approval: Approval) =>
  approval.resume_status ?? (typeof approval.resolution_data?.resume_status === 'string' ? approval.resolution_data.resume_status : null)
const resumeError = (approval: Approval) =>
  approval.resume_error ?? (typeof approval.resolution_data?.resume_error === 'string' ? approval.resolution_data.resume_error : null)

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
      ...(resumeStatus(approval) ? [{ key: 'resume-status', label: t('resumeStatus'), children: statusLabel(resumeStatus(approval) ?? '') }] : []),
      ...(resumeError(approval) ? [{ key: 'resume-error', label: t('resumeError'), children: resumeError(approval) }] : []),
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
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<Approval | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [markdownPreviewModes, setMarkdownPreviewModes] = useState<Record<string, 'raw' | 'markdown'>>({})
  const query = useQuery({ queryKey: ['approvals', status], queryFn: () => getApprovals(status) })
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
    if (!notificationApprovalId || openedNotificationApprovalId.current === notificationApprovalId) return
    const approval = query.data?.find((item) => item.id === notificationApprovalId)
    if (approval) {
      openedNotificationApprovalId.current = notificationApprovalId
      setSelected(approval)
    }
  }, [notificationApprovalId, query.data])
  const skillPreview = useQuery({
    queryKey: ['approvals', 'skill-preview', selected?.id],
    queryFn: () => getSkillSubmissionPreview(selected?.id ?? ''),
    enabled: selected?.resource_type === 'skill' && selected.status === 'pending',
  })
  const refresh = () => client.invalidateQueries({ queryKey: ['approvals'] })
  const resolve = useMutation({
    mutationFn: ({ approval, decision, rejectionReason: reason }: { approval: Approval; decision: 'approved' | 'rejected'; rejectionReason?: string }) =>
      isSubmissionApproval(approval)
        ? resolveSubmissionApproval(approval.id, decision, reason)
        : resolveApproval(approval.id, decision, reason),
    onSuccess: async (row) => {
      setSelected(row)
      setRejectOpen(false)
      setRejectReason('')
      message.success(t('resolved', { status: row.status }))
      await refresh()
    },
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
    const values = new Set((query.data ?? []).map((row) => approvalType(row)).filter((value) => value && value !== '-'))
    return [...values].sort().map((value) => ({ text: value, value }))
  }, [query.data])

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

  const approvalActions = selected && canResolve ? (
    <Space size={4}>
      <Button
        type="primary"
        icon={<CheckOutlined />}
        disabled={selected.status !== 'pending'}
        loading={resolve.isPending}
        style={{ minWidth: 84 }}
        onClick={() => resolve.mutate({ approval: selected, decision: 'approved' })}
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
      {!isSubmissionApproval(selected) && selected.tool_name === 'simulate_containment' && resumeStatus(selected) === 'failed' && (
        <Button loading={retryResume.isPending} onClick={() => retryResume.mutate(selected)}>
          {t('retryResume')}
        </Button>
      )}
    </Space>
  ) : null
  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: '', label: t('allStatuses') },
              ...['pending', 'approved', 'rejected'].map((value) => ({ value, label: statusLabel(value) })),
            ]}
          />
        }
      />
      <Card className="workbench-card">
        <Table<Approval>
          rowKey="id"
          dataSource={query.data ?? []}
          loading={query.isLoading}
          scroll={{ x: 1290 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total}` }}
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
            {selected.status === 'approved' && <Alert type="success" showIcon message={t('approved')} style={{ marginBottom: 16 }} />}
            {selected.status === 'rejected' && (
              <Alert
                type="error"
                showIcon
                message={t('rejected')}
                description={rejectionReason(selected) || t('noRejectReason')}
                style={{ marginBottom: 16 }}
              />
            )}
            {resumeStatus(selected) === 'failed' && (
              <Alert
                type="warning"
                showIcon
                message={t('resumeFailed')}
                description={resumeError(selected) || t('resumeFailedDescription')}
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
                                <XMarkdown content={content} openLinksInNewTab escapeRawHtml />
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
