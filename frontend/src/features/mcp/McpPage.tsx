import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Descriptions, Empty, Form, Grid, Input, InputNumber, Modal, Space, Splitter, Switch, Table, Tabs, Tag } from 'antd'
import { ApiOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { FormattedContentCard } from '@/shared/ui/FormattedContentCard'
import { MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { deleteToken, getConfig, issueToken, listTokens, setServerVisibility, updateConfig, uploadServer, type McpServer, type McpToken } from './api'
import { getAvailableMcpServices, manifestServiceNames } from './utils'

type McpResource = {
  key: string
  name: string
  type: 'built-in' | 'server'
  source: string
  enabled: boolean
  availableServices: string[]
  server?: McpServer
}

type Selection =
  | { kind: 'resource'; resource: McpResource }
  | { kind: 'token'; token: McpToken }
  | null

const tokenTime = (value: number) => value ? new Date(value * 1000).toLocaleString() : '-'

export function McpPage() {
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const vertical = screens.md === false
  const client = useQueryClient()
  const config = useQuery({ queryKey: ['mcp', 'config'], queryFn: getConfig })
  const tokens = useQuery({ queryKey: ['mcp', 'tokens'], queryFn: listTokens })
  const [selection, setSelection] = useState<Selection>(null)
  const [issueOpen, setIssueOpen] = useState(false)
  const [serverOpen, setServerOpen] = useState(false)

  const refresh = () => client.invalidateQueries({ queryKey: ['mcp'] })
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateConfig(id, enabled),
    onSuccess: refresh,
    onError: (error) => message.error(error.message),
  })

  const availableServices = useMemo(() => getAvailableMcpServices(config.data), [config.data])
  const resources = useMemo<McpResource[]>(() => {
    const builtIn = Object.entries(config.data?.services ?? {}).map(([name, enabled]) => ({
      key: `built-in:${name}`,
      name,
      type: 'built-in' as const,
      source: 'T.A.I.S runtime',
      enabled,
      availableServices: enabled ? [name] : [],
    }))
    const external = (config.data?.mcp_servers ?? []).map((server) => ({
      key: `server:${server.name}`,
      name: server.name,
      type: 'server' as const,
      source: server.kind,
      enabled: server.enabled,
      availableServices: server.enabled ? manifestServiceNames(server) : [],
      server,
    }))
    return [...builtIn, ...external]
  }, [config.data])

  const selectedResource = selection?.kind === 'resource' ? selection.resource : null
  const selectedToken = selection?.kind === 'token' ? selection.token : null

  return <main className="page mcp-page">
    <PageHeader title="MCP" description="管理 FastMCP 服务、服务器清单和访问令牌" actions={<>
      <Button icon={<PlusOutlined />} onClick={() => setServerOpen(true)}>上传 Server</Button>
      <Button type="primary" icon={<KeyOutlined />} onClick={() => setIssueOpen(true)}>签发令牌</Button>
    </>} />
    <Splitter className="workbench-splitter mcp-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
      <Splitter.Panel defaultSize="70%" min={vertical ? 280 : '45%'}>
        <Card className="workbench-card splitter-panel-card">
          <Tabs
            items={[
              {
                key: 'resources',
                label: 'Services',
                children: <Table<McpResource>
                  rowKey="key"
                  loading={config.isLoading}
                  dataSource={resources}
                  pagination={false}
                  scroll={{ x: 760 }}
                  onRow={(row) => ({ onClick: () => setSelection({ kind: 'resource', resource: row }) })}
                  columns={[
                    { title: 'MCP', dataIndex: 'name', render: (name, row) => <Space><strong>{name}</strong><Tag color={row.type === 'built-in' ? 'blue' : 'purple'}>{row.type}</Tag></Space> },
                    { title: 'Available', dataIndex: 'availableServices', ellipsis: true, render: (services: string[]) => services.length ? <Space wrap>{services.map((service) => <Tag key={service} color="success">{service}</Tag>)}</Space> : <Tag>disabled</Tag> },
                    { title: 'Source', dataIndex: 'source', ellipsis: true },
                    { title: 'Enabled', dataIndex: 'enabled', width: 110, render: (enabled, row) => row.type === 'built-in'
                      ? <Switch checked={enabled} loading={toggle.isPending} onClick={(_, event) => event.stopPropagation()} onChange={(value) => toggle.mutate({ id: row.name, enabled: value })} />
                      : <Switch checked={enabled} disabled /> },
                    { title: 'Visibility', width: 150, render: (_, row) => row.server ? <VisibilitySelect value={row.server.visibility} disabled={!row.server.can_manage} onClick={(event) => event.stopPropagation()} onChange={(value) => void setServerVisibility(row.server!.name, value).then(refresh)} /> : '-' },
                  ]}
                />,
              },
              {
                key: 'available',
                label: 'Available MCP',
                children: <Table
                  rowKey="key"
                  dataSource={availableServices}
                  pagination={false}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有启用的 MCP 服务" /> }}
                  columns={[
                    { title: 'Service', dataIndex: 'name', render: (name) => <strong>{name}</strong> },
                    { title: 'Source', dataIndex: 'source' },
                    { title: 'Kind', dataIndex: 'kind', width: 120, render: (kind) => <Tag color={kind === 'built-in' ? 'blue' : 'purple'}>{kind}</Tag> },
                  ]}
                />,
              },
              {
                key: 'tokens',
                label: 'Tokens',
                children: <Table<McpToken>
                  rowKey="id"
                  loading={tokens.isLoading}
                  dataSource={tokens.data ?? []}
                  onRow={(row) => ({ onClick: () => setSelection({ kind: 'token', token: row }) })}
                  columns={[
                    { title: 'Name', dataIndex: 'name' },
                    { title: 'Created', dataIndex: 'created_at', render: tokenTime },
                    { title: 'Expires', dataIndex: 'expires_at', render: tokenTime },
                    { title: 'Actions', width: 120, render: (_, row) => <Button danger onClick={async (event) => { event.stopPropagation(); await deleteToken(row.id); await refresh() }}>删除</Button> },
                  ]}
                />,
              },
            ]}
          />
        </Card>
      </Splitter.Panel>
      <Splitter.Panel defaultSize="30%" min={vertical ? 220 : '20%'}>
        <Card className="workbench-card splitter-panel-card" title="Detail">
          {!selection && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择 MCP 服务或令牌查看详情" />}
          {selectedResource && <Tabs destroyOnHidden items={[
            { key: 'overview', label: 'Overview', icon: <ApiOutlined />, children: <MetadataDescriptions items={[
              { key: 'name', label: 'Name', children: selectedResource.name },
              { key: 'type', label: 'Type', children: <Tag color={selectedResource.type === 'built-in' ? 'blue' : 'purple'}>{selectedResource.type}</Tag> },
              { key: 'enabled', label: 'Enabled', children: <Tag color={selectedResource.enabled ? 'success' : 'default'}>{String(selectedResource.enabled)}</Tag> },
              { key: 'source', label: 'Source', children: selectedResource.source },
              { key: 'mcp-url', label: 'MCP URL', children: config.data?.mcp_url ?? '-' },
              { key: 'fastmcp', label: 'FastMCP', children: config.data?.fastmcp ?? '-' },
            ]} value={{
              available_services: selectedResource.availableServices,
              visibility: selectedResource.server?.visibility,
              owner_user_id: selectedResource.server?.owner_user_id,
            }} /> },
            { key: 'manifest', label: 'Manifest', children: selectedResource.server
              ? <FormattedContentCard title="Manifest" value={selectedResource.server.manifest} />
              : <Descriptions column={1} size="small" items={[{ key: 'builtin', label: 'Manifest', children: '内置服务由 T.A.I.S runtime 提供，无独立 manifest。' }]} /> },
          ]} />}
          {selectedToken && <Tabs destroyOnHidden items={[
            { key: 'overview', label: 'Overview', icon: <KeyOutlined />, children: <MetadataDescriptions items={[
              { key: 'name', label: 'Name', children: selectedToken.name },
              { key: 'id', label: 'ID', children: String(selectedToken.id) },
              { key: 'created', label: 'Created', children: tokenTime(selectedToken.created_at) },
              { key: 'expires', label: 'Expires', children: tokenTime(selectedToken.expires_at) },
              { key: 'token', label: 'Token', children: <Button type="link" onClick={() => void copyToClipboard(selectedToken.token)}>复制令牌</Button> },
            ]} /> },
          ]} />}
        </Card>
      </Splitter.Panel>
    </Splitter>
    <Modal open={issueOpen} footer={null} onCancel={() => setIssueOpen(false)} title="签发 MCP Token">
      <Form layout="vertical" initialValues={{ expires_in: 86400 }} onFinish={async (values: { name: string; expires_in: number }) => { const result = await issueToken(values.name, values.expires_in); await copyToClipboard(result.token); message.success('令牌已签发并复制'); setIssueOpen(false); await refresh() }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="expires_in" label="有效期（秒）"><InputNumber min={60} style={{ width: '100%' }} /></Form.Item>
        <Button type="primary" htmlType="submit">签发</Button>
      </Form>
    </Modal>
    <Modal open={serverOpen} footer={null} onCancel={() => setServerOpen(false)} title="上传 MCP Server">
      <Form layout="vertical" initialValues={{ visibility: 'private', manifest: '{}' }} onFinish={async (values) => { await uploadServer(values); message.success('Server 已上传'); setServerOpen(false); await refresh() }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="description" label="描述"><Input /></Form.Item>
        <Form.Item name="manifest" label="Manifest JSON"><Input.TextArea rows={8} /></Form.Item>
        <Form.Item name="visibility" label="可见性"><VisibilitySelect style={{ width: '100%' }} /></Form.Item>
        <Button type="primary" htmlType="submit">上传</Button>
      </Form>
    </Modal>
  </main>
}
