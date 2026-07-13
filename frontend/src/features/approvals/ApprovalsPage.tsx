import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Collapse, Descriptions, Drawer, Input, Modal, Segmented, Select, Space, Table, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import XMarkdown from '@ant-design/x-markdown'
import { PageHeader } from '@/shared/ui/PageHeader'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import {
  getApprovals,
  getSkillSubmissionPreview,
  isSubmissionApproval,
  resolveApproval,
  resolveSubmissionApproval,
  type Approval,
} from './api'
import { compactId, formatDate } from '@/shared/lib/format'

const approvalTitle = (approval: Approval) => {
  if (approval.resource_type === 'skill') return 'Skill 上传'
  if (approval.resource_type === 'mcp') return 'MCP Server 上传'
  return approval.tool_name ?? '-'
}

const approvalType = (approval: Approval) => approval.resource_type ? `${approval.resource_type} upload` : approval.approval_type ?? '-'

const approvalPayload = (approval: Approval) => approval.payload ?? approval.tool_args

const actorEmail = (actor: Approval['submitted_by'] | Approval['resolved_by'], legacyEmail?: string) =>
  typeof actor === 'object' && actor !== null ? actor.email || '-' : legacyEmail || '-'

const actorId = (actor: Approval['submitted_by'] | Approval['resolved_by']) =>
  typeof actor === 'object' && actor !== null ? actor.id || '-' : actor || '-'

const statusLabel = (status: string) => status ? `${status.slice(0, 1).toUpperCase()}${status.slice(1)}` : '-'

const rejectionReason = (approval: Approval) =>
  approval.rejection_reason ?? (typeof approval.resolution_data?.rejection_reason === 'string' ? approval.resolution_data.rejection_reason : '')

export function ApprovalsPage() {
  const { message } = App.useApp()
  const client = useQueryClient()
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<Approval | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [markdownPreviewModes, setMarkdownPreviewModes] = useState<Record<string, 'raw' | 'markdown'>>({})
  const query = useQuery({ queryKey: ['approvals', status], queryFn: () => getApprovals(status) })
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
      message.success(`审批已${row.status}`)
      await refresh()
    },
  })
  const approvalActions = selected ? (
    <Space size={4}>
      <Button
        type="primary"
        icon={<CheckOutlined />}
        disabled={selected.status !== 'pending'}
        loading={resolve.isPending}
        style={{ minWidth: 84 }}
        onClick={() => resolve.mutate({ approval: selected, decision: 'approved' })}
      >
        批准
      </Button>
      <Button
        danger
        icon={<CloseOutlined />}
        disabled={selected.status !== 'pending'}
        loading={resolve.isPending}
        style={{ minWidth: 84 }}
        onClick={() => setRejectOpen(true)}
      >
        拒绝
      </Button>
    </Space>
  ) : null
  return (
    <main className="page">
      <PageHeader
        title="Approvals"
        description="处理暂停的 Agent 操作、人工确认与资源上传请求"
        actions={
          <Select
            value={status}
            onChange={setStatus}
            options={[
              { value: '', label: '全部状态' },
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
          rowClassName={(row) => (row.id === selected?.id ? 'selected-table-row' : '')}
          onRow={(row) => ({
            tabIndex: 0,
            role: 'button',
            'aria-label': `查看审批 ${row.id}`,
            onClick: () => setSelected(row),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelected(row)
              }
            },
          })}
          columns={[
            { title: 'ID', dataIndex: 'id', render: compactId },
            { title: 'Request', render: (_, row) => approvalTitle(row) },
            { title: 'Type', render: (_, row) => approvalType(row) },
            {
              title: 'Status',
              dataIndex: 'status',
              render: (value) => <Tag color={value === 'pending' ? 'warning' : value === 'approved' ? 'success' : 'error'}>{statusLabel(value)}</Tag>,
            },
            { title: 'Submitted user email', render: (_, row) => actorEmail(row.submitted_by, row.submitted_by_email), ellipsis: true },
            { title: 'Created', dataIndex: 'created_at', render: formatDate },
            { title: '处理时间', dataIndex: 'resolved_at', render: formatDate },
          ]}
        />
      </Card>
      <Drawer size={600} open={Boolean(selected)} onClose={() => setSelected(null)} title="Approval detail" extra={approvalActions}>
        {selected && (
          <>
            {selected.status === 'approved' && <Alert type="success" showIcon message="已批准" style={{ marginBottom: 16 }} />}
            {selected.status === 'rejected' && (
              <Alert
                type="error"
                showIcon
                message="已拒绝"
                description={rejectionReason(selected) || '未提供拒绝原因'}
                style={{ marginBottom: 16 }}
              />
            )}
            <Descriptions
              bordered
              column={1}
              items={[
                { key: 'id', label: 'ID', children: selected.id },
                { key: 'run', label: 'Run', children: selected.run_id ?? '-' },
                { key: 'session', label: 'Session', children: selected.session_id ?? '-' },
                { key: 'submitter-email', label: 'Submitted user email', children: actorEmail(selected.submitted_by, selected.submitted_by_email) },
                { key: 'submitter-id', label: 'Submitted user ID', children: actorId(selected.submitted_by) },
                { key: 'resolver-email', label: 'Approved by email', children: actorEmail(selected.resolved_by, selected.resolved_by_email) },
                { key: 'resolver-id', label: 'Approved by ID', children: actorId(selected.resolved_by) },
              ]}
            />
            <PayloadViewer value={approvalPayload(selected)} />
            {selected.resource_type === 'skill' && selected.status === 'pending' && (
              <Card
                size="small"
                title="ZIP 内容预览"
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
                        { title: '文件', dataIndex: 'name' },
                        { title: '大小', dataIndex: 'size', render: (size: number) => `${size} B` },
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
                {skillPreview.isError && <p>无法加载 ZIP 预览。</p>}
              </Card>
            )}
          </>
        )}
      </Drawer>
      <Modal
        open={rejectOpen}
        title="拒绝审批"
        okText="确认拒绝"
        okButtonProps={{ danger: true, disabled: !rejectReason.trim() }}
        cancelText="取消"
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
        <Typography.Paragraph type="secondary">拒绝原因会发送给申请用户。</Typography.Paragraph>
        <div style={{ paddingBottom: 28 }}>
          <Input.TextArea
            rows={4}
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            placeholder="请说明拒绝原因"
            maxLength={2000}
            showCount
          />
        </div>
      </Modal>
    </main>
  )
}
