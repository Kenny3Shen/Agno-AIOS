import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { DeleteOutlined, KeyOutlined, PlusOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { FormattedContentCard } from '@/shared/ui/FormattedContentCard'
import { MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import type { JsonRecord, ResourceVisibility } from '@/shared/types/common'
import { useTranslation } from 'react-i18next'
import {
  callTool,
  deleteToken,
  deleteServer,
  getConfig,
  issueToken,
  listComponents,
  listTokens,
  setComponentEnabled,
  setServerEnabled,
  setServerVisibility,
  testServer,
  updateConfig,
  uploadServer,
  type McpComponent,
  type McpServer,
  type McpToken,
} from './api'

const tokenTime = (value: number, neverExpires: string) => (value ? new Date(value * 1000).toLocaleString() : neverExpires)

function RiskTags({ item }: { item: McpComponent }) {
  const { t } = useTranslation('mcp')
  const annotations = item.annotations ?? {}
  return (
    <Space wrap>
      {annotations.readOnlyHint === true && <Tag color="blue">{t('readonly')}</Tag>}
      {annotations.destructiveHint === true && <Tag color="red">{t('destructive')}</Tag>}
      {annotations.openWorldHint === true && <Tag color="orange">{t('externalSystem')}</Tag>}
    </Space>
  )
}

export function McpPage() {
  const { t } = useTranslation('mcp')
  const { message, modal } = App.useApp()
  const client = useQueryClient()
  const [namespace, setNamespace] = useState<string>()
  const [component, setComponent] = useState<McpComponent>()
  const [detailOpen, setDetailOpen] = useState(false)
  const [issueOpen, setIssueOpen] = useState(false)
  const [serverOpen, setServerOpen] = useState(false)
  const [callOpen, setCallOpen] = useState(false)
  const [callArgs, setCallArgs] = useState('{}')
  const [callResult, setCallResult] = useState<unknown>()
  const [serverForm] = Form.useForm()

  const config = useQuery({ queryKey: ['mcp', 'config'], queryFn: getConfig })
  const components = useQuery({ queryKey: ['mcp', 'components', namespace], queryFn: () => listComponents(namespace) })
  const tokens = useQuery({ queryKey: ['mcp', 'tokens'], queryFn: listTokens })
  const refresh = () => client.invalidateQueries({ queryKey: ['mcp'] })
  const updateServerVisibility = async (name: string, visibility: ResourceVisibility) => {
    try {
      await setServerVisibility(name, visibility)
      await refresh()
      message.success(t('visibilityUpdated'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('visibilityFailed'))
    }
  }
  const removeServer = async (server: McpServer) => {
    try {
      await deleteServer(server.id)
      if (namespace === server.namespace) {
        setNamespace(undefined)
        setComponent(undefined)
      }
      message.success(t('serverDeleted'))
      await refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('serverDeleteFailed'))
    }
  }

  const toggleServer = useMutation({
    mutationFn: ({ server, enabled }: { server: McpServer; enabled: boolean }) =>
      server.server_type === 'builtin' ? updateConfig(server.name, enabled) : setServerEnabled(server.id, enabled),
    onSuccess: async (_, { enabled }) => {
      message.success(enabled ? t('serverEnabled') : t('serverDisabled'))
      await refresh()
    },
    onError: (error) => message.error(error.message),
  })
  const toggleComponent = useMutation({
    mutationFn: ({ item, enabled }: { item: McpComponent; enabled: boolean }) => setComponentEnabled(item, enabled),
    onSuccess: async (_, { enabled }) => {
      message.success(enabled ? t('componentEnabled') : t('componentDisabled'))
      await refresh()
    },
    onError: (error) => message.error(error.message),
  })

  const servers = config.data?.mcp_servers ?? []
  const selectedServer = servers.find((server) => server.namespace === namespace)

  const executeTool = async () => {
    if (!component) return
    try {
      const args = JSON.parse(callArgs) as JsonRecord
      const result = await callTool(component.name, args)
      setCallResult(result)
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('paramsMustBeObject'))
    }
  }

  const runTool = () => {
    if (component?.annotations?.destructiveHint === true) {
      modal.confirm({
        title: t('confirmDestructive'),
        content: component.name,
        okText: t('confirmCall'),
        okButtonProps: { danger: true },
        onOk: executeTool,
      })
      return
    }
    void executeTool()
  }

  return (
    <main className="page mcp-page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <>
            <Button icon={<PlusOutlined />} onClick={() => setServerOpen(true)}>
              {t('addServerShort')}
            </Button>
            <Button type="primary" icon={<KeyOutlined />} onClick={() => setIssueOpen(true)}>
              {t('issueTokenShort')}
            </Button>
          </>
        }
      />
      <Tabs
        items={[
          {
            key: 'components',
            label: 'Servers & Components',
            children: (
              <Card className="workbench-card">
                <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                  <Table<McpServer>
                    rowKey="id"
                    size="small"
                    loading={config.isLoading}
                    dataSource={servers}
                    pagination={false}
                    rowClassName={(row) => (row.namespace === namespace ? 'ant-table-row-selected' : '')}
                    onRow={(row) => ({
                      onClick: () => {
                        setNamespace(row.namespace)
                        setComponent(undefined)
                        setDetailOpen(true)
                      },
                    })}
                    columns={[
                      {
                        title: 'Server / Namespace',
                        render: (_, row) => (
                          <Space>
                            <strong>{row.name}</strong>
                            <Typography.Text type="secondary">{row.namespace}</Typography.Text>
                          </Space>
                        ),
                      },
                      { title: 'Transport', dataIndex: 'transport', width: 150, render: (value) => <Tag>{value}</Tag> },
                      {
                        title: 'Enabled',
                        width: 90,
                        render: (_, row) => {
                          const pending = toggleServer.isPending && toggleServer.variables?.server.id === row.id
                          return (
                            <Switch
                              checked={row.enabled}
                              loading={pending}
                              disabled={!row.can_manage || pending}
                              onClick={(_checked, event) => event.stopPropagation()}
                              onChange={(enabled) => toggleServer.mutate({ server: row, enabled })}
                            />
                          )
                        },
                      },
                      {
                        title: 'Visibility',
                        width: 140,
                        render: (_, row) => (
                          <VisibilitySelect
                            value={row.visibility}
                            disabled={!row.can_manage}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(value) => void updateServerVisibility(row.name, value)}
                          />
                        ),
                      },
                      {
                        title: 'Actions',
                        width: 76,
                        render: (_, row) =>
                          row.can_delete ? (
                            <Popconfirm title={t('deleteServerConfirm', { name: row.name })} okText={t('common:delete')} okButtonProps={{ danger: true }} onConfirm={() => removeServer(row)}>
                              <Button danger type="text" icon={<DeleteOutlined />} aria-label={t('deleteServerNamed', { name: row.name })} onClick={(event) => event.stopPropagation()} />
                            </Popconfirm>
                          ) : null,
                      },
                    ]}
                  />
                  <Table<McpComponent>
                    rowKey="key"
                    size="small"
                    loading={components.isLoading}
                    dataSource={components.data ?? []}
                    pagination={false}
                    locale={{
                      emptyText: (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={namespace ? t('noVisibleComponents') : t('selectServerForComponents')}
                        />
                      ),
                    }}
                    onRow={(row) => ({
                      onClick: () => {
                        setComponent(row)
                        setDetailOpen(true)
                      },
                    })}
                    columns={[
                      {
                        title: 'Component',
                        render: (_, row) => (
                          <Space>
                            <Tag>{row.type}</Tag>
                            <strong>{row.name}</strong>
                          </Space>
                        ),
                      },
                      { title: 'Title', dataIndex: 'title', ellipsis: true },
                      { title: 'Namespace', dataIndex: 'namespace', width: 140 },
                      {
                        title: 'Risk',
                        width: 180,
                        render: (_, row) => <RiskTags item={row} />,
                      },
                      {
                        title: 'Enabled',
                        width: 90,
                        render: (_, row) => {
                          const pending = toggleComponent.isPending && toggleComponent.variables?.item.key === row.key
                          const server = servers.find((item) => item.id === row.server_id)
                          return (
                            <Switch
                              aria-label={`${row.name} enabled`}
                              checked={row.enabled}
                              disabled={!server?.can_manage || pending}
                              loading={pending}
                              onClick={(_checked, event) => event.stopPropagation()}
                              onChange={(enabled) => toggleComponent.mutate({ item: row, enabled })}
                            />
                          )
                        },
                      },
                    ]}
                  />
                </Space>
              </Card>
            ),
          },
          {
            key: 'tokens',

            label: 'Tokens',
            children: (
              <Card className="workbench-card">
                <Table<McpToken>
                  rowKey="id"
                  loading={tokens.isLoading}
                  dataSource={tokens.data ?? []}
                  columns={[
                    { title: 'Name', dataIndex: 'name' },
                    { title: 'Created', dataIndex: 'created_at', render: (value: number) => tokenTime(value, t('neverExpires')) },
                    { title: 'Expires', dataIndex: 'expires_at', render: (value: number) => tokenTime(value, t('neverExpires')) },
                    {
                      title: 'Actions',
                      width: 120,
                      render: (_, row) => (
                        <Popconfirm
                          title={t('deleteTokenConfirm')}
                          onConfirm={async () => {
                            await deleteToken(row.id)
                            await refresh()
                          }}
                        >
                          <Button danger>{t('common:delete')}</Button>
                        </Popconfirm>
                      ),
                    },
                  ]}
                />

              </Card>
            ),
          },
        ]}
      />
      <Drawer
        size={640}
        open={detailOpen && Boolean(component || selectedServer)}
        onClose={() => {
          setDetailOpen(false)
          setComponent(undefined)
        }}
        title={component?.name || selectedServer?.name || 'Detail'}
        destroyOnHidden
        extra={
          component?.type === 'tool' ? (
            <Button
              icon={<PlayCircleOutlined />}
              onClick={() => {
                setCallResult(undefined)
                setCallOpen(true)
              }}
            >
              {t('tryCallShort')}
            </Button>
          ) : null
        }
      >
        {!component && selectedServer ? (
          <MetadataDescriptions
            items={[
              { key: 'name', label: 'Name', children: selectedServer.name },
              { key: 'namespace', label: 'Namespace', children: selectedServer.namespace },
              { key: 'transport', label: 'Transport', children: selectedServer.transport },
              { key: 'store', label: 'Config store', children: config.data?.config_store },
            ]}
            value={selectedServer.manifest}
            prefix="Manifest"
          />
        ) : null}
        {!component && !selectedServer ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectForDetails')} />
        ) : null}
        {component ? (
          <Tabs
            destroyOnHidden
            items={[
              {
                key: 'overview',
                label: 'Overview',
                children: (
                  <MetadataDescriptions
                    items={[
                      { key: 'name', label: 'Name', children: component.name },
                      { key: 'title', label: 'Title', children: component.title || '-' },
                      { key: 'namespace', label: 'Namespace', children: component.namespace || '-' },
                      { key: 'description', label: 'Description', children: component.description || '-' },
                    ]}
                    value={{ tags: component.tags, annotations: component.annotations }}
                  />
                ),
              },
              {
                key: 'schemas',
                label: 'Schemas',
                children: (
                  <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                    <FormattedContentCard title="Input schema" value={component.input_schema} />
                    <FormattedContentCard title="Output schema" value={component.output_schema} />
                  </Space>
                ),
              },
              { key: 'metadata', label: 'Metadata', children: <MetadataDescriptions value={component.meta} /> },
            ]}
          />
        ) : null}
      </Drawer>


      <Modal open={issueOpen} footer={null} onCancel={() => setIssueOpen(false)} title={t('issueToken')}>
        <Form
          layout="vertical"
          initialValues={{ expires_in: 86400 }}
          onFinish={async (values: { name: string; expires_in: number }) => {
            try {
              const result = await issueToken(values.name, values.expires_in)
              await copyToClipboard(result.token)
              message.success(t('tokenIssued'))
              setIssueOpen(false)
              await refresh()
            } catch (error) {
              message.error(error instanceof Error ? error.message : t('issueTokenFailed'))
            }
          }}
        >
          <Form.Item name="name" label={t('common:name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="expires_in" label={t('ttlSeconds')}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            {t('issue')}
          </Button>
        </Form>
      </Modal>

      <Modal open={serverOpen} footer={null} onCancel={() => setServerOpen(false)} title={t('addServer')}>
        <Form
          form={serverForm}
          layout="vertical"
          initialValues={{ visibility: 'private', manifest: '{\n  "mcpServers": {}\n}' }}
          onFinish={async (values: { name: string; description: string; manifest: string; visibility: ResourceVisibility }) => {
            try {
              const result = await uploadServer(values)
              if (result.status === 'pending') {
                message.success(t('serverPendingApproval'))
              } else {
                message.success(t('serverSavedRestart'))
                await refresh()
              }
              setServerOpen(false)
            } catch (error) {
              message.error(error instanceof Error ? error.message : t('submitServerFailed'))
            }
          }}
        >
          <Form.Item name="name" label={t('common:name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label={t('common:description')}>
            <Input />
          </Form.Item>
          <Form.Item name="manifest" label="MCPConfig JSON" rules={[{ required: true }]}>
            <Input.TextArea rows={10} />
          </Form.Item>
          <Form.Item name="visibility" label={t('common:visibility')}>
            <VisibilitySelect style={{ width: '100%' }} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              {t('common:save')}
            </Button>
            <Button
              onClick={async () => {
                try {
                  const values = await serverForm.validateFields()
                  const result = await testServer(values)
                  message.success(t('connectDiscovered', { count: result.tools.length }))
                } catch (error) {
                  // validateFields reject is user-facing form state; only toast transport errors.
                  if (error && typeof error === 'object' && 'errorFields' in error) return
                  message.error(error instanceof Error ? error.message : t('testConnectionFailed'))
                }
              }}
            >
              {t('testConnection')}
            </Button>
          </Space>
        </Form>
      </Modal>

      <Modal open={callOpen} onCancel={() => setCallOpen(false)} title={t('tryCall', { name: component?.name ?? '' })} onOk={runTool} okText={t('call')}>
        <Typography.Paragraph type="secondary">{t('callHint')}</Typography.Paragraph>
        <Input.TextArea rows={8} value={callArgs} onChange={(event) => setCallArgs(event.target.value)} />
        {callResult !== undefined && <FormattedContentCard title="Result" value={callResult} />}
      </Modal>
    </main>
  )
}
