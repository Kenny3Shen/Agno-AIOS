import { useMemo, useState } from 'react'
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
import { currentUserQuery } from '@/features/auth'
import { hasScope, roleOf } from '@/shared/auth/permissions'
import {
  listCapabilities,
  setCapabilityPreference,
  type CapabilityItem,
  type CapabilityPreference,
} from '@/features/capabilities'

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
  const capabilitiesQuery = useQuery({ queryKey: ['capabilities'], queryFn: listCapabilities })
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const canSubmit = hasScope(currentUser.data, 'mcp:submit')
  const components = useQuery({ queryKey: ['mcp', 'components', namespace], queryFn: () => listComponents(namespace) })
  const tokens = useQuery({ queryKey: ['mcp', 'tokens'], queryFn: listTokens })
  const capabilityByServerId = useMemo(() => {
    const map = new Map<number, CapabilityItem>()
    for (const item of capabilitiesQuery.data ?? []) {
      if (item.kind !== 'mcp_server' || item.server_id == null) continue
      map.set(item.server_id, item)
    }
    return map
  }, [capabilitiesQuery.data])
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
      await client.invalidateQueries({ queryKey: ['capabilities'] })
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
  const updatePreference = useMutation({
    mutationFn: ({ item, state }: { item: CapabilityItem; state: CapabilityPreference }) =>
      setCapabilityPreference(item, state),
    onSuccess: (updated) => {
      client.setQueryData<CapabilityItem[]>(['capabilities'], (current) =>
        (current ?? []).map((item) =>
          item.kind === updated.kind && item.capability_key === updated.capability_key ? updated : item,
        ),
      )
      message.success(t('forMeUpdated'))
    },
    onError: (error) => message.error(error instanceof Error ? error.message : t('forMeUpdateFailed')),
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
            {canSubmit ? (
              <Button icon={<PlusOutlined />} onClick={() => setServerOpen(true)}>
                {t('addServerShort')}
              </Button>
            ) : null}
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
            label: t('tabServersComponents'),
            children: (
              <Card className="workbench-card">
                <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                  <Table<McpServer>
                    rowKey="id"
                    size="small"
                    loading={config.isLoading || capabilitiesQuery.isLoading}
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
                        title: t('colServer'),
                        render: (_, row) => (
                          <Space>
                            <strong>{row.name}</strong>
                            <Typography.Text type="secondary">{row.namespace}</Typography.Text>
                          </Space>
                        ),
                      },
                      { title: t('colTransport'), dataIndex: 'transport', width: 150, render: (value) => <Tag>{value}</Tag> },
                      ...(isAdmin
                        ? [
                            {
                              title: t('colEnabled'),
                              width: 90,
                              render: (_: unknown, row: McpServer) => {
                                if (!row.can_manage) {
                                  return <Tag>{row.enabled ? t('common:enabled') : t('common:disabled')}</Tag>
                                }
                                const pending = toggleServer.isPending && toggleServer.variables?.server.id === row.id
                                return (
                                  <Switch
                                    checked={row.enabled}
                                    loading={pending}
                                    disabled={pending}
                                    onClick={(_checked, event) => event.stopPropagation()}
                                    onChange={(enabled) => toggleServer.mutate({ server: row, enabled })}
                                  />
                                )
                              },
                            },
                          ]
                        : []),
                      {
                        title: t('colForMe'),
                        key: 'for_me',
                        width: 110,
                        render: (_: unknown, row: McpServer) => {
                          const capability = capabilityByServerId.get(row.id)
                          const pending =
                            updatePreference.isPending &&
                            updatePreference.variables?.item.capability_key === capability?.capability_key
                          const platformReady = Boolean(capability?.platform_enabled ?? row.enabled)
                          return (
                            <Switch
                              checked={Boolean(capability?.effective_enabled)}
                              loading={pending || capabilitiesQuery.isLoading}
                              disabled={!capability || !platformReady || pending}
                              aria-label={t('forMeFor', { name: row.name })}
                              onClick={(_checked, event) => event.stopPropagation()}
                              onChange={(enabled) => {
                                if (!capability) return
                                updatePreference.mutate({
                                  item: capability,
                                  state: enabled ? 'enabled' : 'disabled',
                                })
                              }}
                            />
                          )
                        },
                      },
                      {
                        title: t('colVisibility'),
                        width: 140,
                        render: (_, row) =>
                          row.can_manage ? (
                            <VisibilitySelect
                              value={row.visibility}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(value) => void updateServerVisibility(row.name, value)}
                            />
                          ) : (
                            <Tag>{row.visibility === 'public' ? t('common:public') : t('common:private')}</Tag>
                          ),
                      },
                      {
                        title: t('colActions'),
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
                        title: t('colComponent'),
                        render: (_, row) => (
                          <Space>
                            <Tag>{row.type}</Tag>
                            <strong>{row.name}</strong>
                          </Space>
                        ),
                      },
                      { title: t('colTitle'), dataIndex: 'title', ellipsis: true },
                      { title: t('colNamespace'), dataIndex: 'namespace', width: 140 },
                      {
                        title: t('colRisk'),
                        width: 180,
                        render: (_, row) => <RiskTags item={row} />,
                      },
                      {
                        title: t('colComponentEnabled'),
                        width: 90,
                        render: (_, row) => {
                          const pending = toggleComponent.isPending && toggleComponent.variables?.item.key === row.key
                          const server = servers.find((item) => item.id === row.server_id)
                          if (!server?.can_manage) {
                            return (
                              <Tag aria-label={`${row.name} enabled`}>
                                {row.enabled ? t('common:enabled') : t('common:disabled')}
                              </Tag>
                            )
                          }
                          return (
                            <Switch
                              aria-label={`${row.name} enabled`}
                              checked={row.enabled}
                              disabled={pending}
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

            label: t('tabTokens'),
            children: (
              <Card className="workbench-card">
                <Table<McpToken>
                  rowKey="id"
                  loading={tokens.isLoading}
                  dataSource={tokens.data ?? []}
                  columns={[
                    { title: t('colTokenName'), dataIndex: 'name' },
                    { title: t('colCreated'), dataIndex: 'created_at', render: (value: number) => tokenTime(value, t('neverExpires')) },
                    { title: t('colExpires'), dataIndex: 'expires_at', render: (value: number) => tokenTime(value, t('neverExpires')) },
                    {
                      title: t('colTokenActions'),
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
              { key: 'name', label: t('fieldName'), children: selectedServer.name },
              { key: 'namespace', label: t('fieldNamespace'), children: selectedServer.namespace },
              { key: 'transport', label: t('fieldTransport'), children: selectedServer.transport },
              { key: 'store', label: t('fieldConfigStore'), children: config.data?.config_store },
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
                label: t('tabOverview'),
                children: (
                  <MetadataDescriptions
                    items={[
                      { key: 'name', label: t('fieldName'), children: component.name },
                      { key: 'title', label: t('fieldTitle'), children: component.title || '-' },
                      { key: 'namespace', label: t('fieldNamespace'), children: component.namespace || '-' },
                      { key: 'description', label: t('fieldDescription'), children: component.description || '-' },
                    ]}
                    value={{ tags: component.tags, annotations: component.annotations }}
                  />
                ),
              },
              {
                key: 'schemas',
                label: t('tabSchemas'),
                children: (
                  <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                    <FormattedContentCard title={t('inputSchema')} value={component.input_schema} />
                    <FormattedContentCard title={t('outputSchema')} value={component.output_schema} />
                  </Space>
                ),
              },
              { key: 'metadata', label: t('fieldMetadata'), children: <MetadataDescriptions value={component.meta} /> },
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
        {callResult !== undefined && <FormattedContentCard title={t('callResult')} value={callResult} />}
      </Modal>
    </main>
  )
}
