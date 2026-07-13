import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { Avatar, Badge, Button, Drawer, Dropdown, Grid, Layout, Menu, Space, Spin, Tooltip, Typography, type MenuProps } from 'antd'
import {
  ApiOutlined,
  AuditOutlined,
  BellOutlined,
  BookOutlined,
  BugOutlined,
  BulbOutlined,
  CloudDownloadOutlined,
  CodeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  GithubOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  MoonOutlined,
  NodeIndexOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  SunOutlined,
  TranslationOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { currentUserQuery, logout } from '@/features/auth'
import { ChatTaskPanel } from '@/features/chat/ChatTaskPanel'
import { getNotifications, markNotificationRead, type Notification } from '@/features/notifications/api'
import { loginPath, nextPathFromLocation } from '@/features/auth/routing'
import { getToken } from '@/shared/auth/storage'
import { hasScope } from '@/shared/auth/permissions'
import { usePreferences } from '@/app/providers/AppProviders'
import { groupNavigation, joinMenuGroups } from './utils'

const { Header, Sider, Content } = Layout

const nav = [
  { key: '/dashboard', icon: <DashboardOutlined />, labelKey: 'dashboard' },
  { key: '/chat', icon: <MessageOutlined />, labelKey: 'chat', scope: 'sessions:write' },
  { key: '/workflow', icon: <NodeIndexOutlined />, labelKey: 'workflow', scope: 'mcp:read' },
  { key: '/skills', icon: <BulbOutlined />, labelKey: 'skills', scope: 'skill:read' },
  { key: '/mcp', icon: <ApiOutlined />, labelKey: 'mcp', scope: 'mcp:read' },
  { key: '/knowledge', icon: <BookOutlined />, labelKey: 'knowledge', scope: 'knowledge:read' },
  { key: '/trace', icon: <CodeOutlined />, labelKey: 'trace', scope: 'traces:read' },
  { key: '/memory', icon: <DatabaseOutlined />, labelKey: 'memory', scope: 'memories:read' },
  { key: '/evaluations', icon: <ExperimentOutlined />, labelKey: 'evaluations', scope: 'evals:read' },
  { key: '/approvals', icon: <AuditOutlined />, labelKey: 'approvals', scope: 'approvals:read' },
  { key: '/cve', icon: <BugOutlined />, labelKey: 'cve', scope: 'cve:read' },
  { key: '/collect', icon: <CloudDownloadOutlined />, labelKey: 'collect', scope: 'collect:write' },
  { key: '/audit', icon: <FileSearchOutlined />, labelKey: 'audit', scope: 'audit:read' },
  { key: '/settings', icon: <SettingOutlined />, labelKey: 'settings', scope: 'config:read' },
]
const primaryNav = nav.filter((item) => item.key !== '/settings')
const settingsNav = nav.filter((item) => item.key === '/settings')

export function AppFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const router = useRouter()
  const queryClient = useQueryClient()
  const preferences = usePreferences()
  const screens = Grid.useBreakpoint()
  const mobile = !screens.lg
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const path = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const currentNextPath = nextPathFromLocation({ pathname: path, searchStr })
  const nextPathRef = useRef<string | null>(currentNextPath)
  const token = getToken()
  const userQuery = useQuery({ ...currentUserQuery(), enabled: Boolean(token), retry: false })
  const canReadApprovals = hasScope(userQuery.data, 'approvals:read')
  const canReadNotifications = hasScope(userQuery.data, 'sessions:read')
  const notificationsQuery = useQuery({
    queryKey: ['notifications'],
    queryFn: getNotifications,
    enabled: Boolean(token) && canReadNotifications,
    refetchInterval: 30_000,
  })

  const items = useMemo<MenuProps['items']>(
    () =>
      joinMenuGroups(
        groupNavigation(primaryNav).map((group) =>
          group
            .filter((item) => !item.scope || hasScope(userQuery.data, item.scope))
            .map((item) => ({
              key: item.key,
              icon: item.icon,
              label: t(`shell.${item.labelKey}`),
            }))
        )
      ),
    [t, userQuery.data]
  )
  const settingsItems = useMemo<MenuProps['items']>(
    () =>
      settingsNav
        .filter((item) => !item.scope || hasScope(userQuery.data, item.scope))
        .map((item) => ({
          key: item.key,
          icon: item.icon,
          label: t(`shell.${item.labelKey}`),
        })),
    [t, userQuery.data]
  )
  const navigateFromMenu: MenuProps['onClick'] = ({ key }) => {
    void router.history.push(key === '/chat' ? '/chat' : key)
    setMobileOpen(false)
  }
  const openNotification = async (notification: Notification) => {
    try {
      await markNotificationRead(notification.id)
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    } finally {
      const approvalId = typeof notification.data.approval_id === 'string' ? notification.data.approval_id : ''
      const targetPath = typeof notification.data.path === 'string' && notification.data.path.startsWith('/') ? notification.data.path : ''
      if (approvalId && canReadApprovals) {
        void router.history.push(`/approvals?approval_id=${encodeURIComponent(approvalId)}`)
      } else if (targetPath) {
        void router.history.push(targetPath)
      } else if (canReadApprovals) {
        void router.history.push('/approvals')
      }
    }
  }
  useEffect(() => setMobileOpen(false), [path])
  useEffect(() => {
    if (currentNextPath) nextPathRef.current = currentNextPath
  }, [currentNextPath])
  useEffect(() => {
    if (token && !userQuery.isError) return
    router.history.replace(loginPath(nextPathRef.current))
  }, [router.history, token, userQuery.isError])

  if (!token || userQuery.isError)
    return (
      <div className="boot-screen">
        <Spin size="large" />
      </div>
    )
  if (userQuery.isLoading)
    return (
      <div className="boot-screen">
        <Spin size="large" />
      </div>
    )

  const initials = userQuery.data?.email.slice(0, 2).toUpperCase() ?? 'AI'
  return (
    <Layout className="app-shell">
      <Sider width={264} collapsedWidth={76} collapsed={mobile ? true : collapsed} className="shell-sider" trigger={null}>
        <div className="shell-brand">
          <span className="brand-mark">T</span>
          <div className="shell-brand-copy">
            <strong>T.A.I.S</strong>
            <small>Trinity AI Security</small>
          </div>
        </div>
        <div className="shell-sider-body">
          <Menu
            mode="inline"
            selectedKeys={path === '/settings' ? [] : [path]}
            items={items}
            onClick={navigateFromMenu}
            className="shell-menu shell-main-menu"
          />
          <ChatTaskPanel />
          {settingsItems?.length ? (
            <Menu
              mode="inline"
              selectedKeys={path === '/settings' ? [path] : []}
              items={settingsItems}
              onClick={navigateFromMenu}
              className="shell-menu shell-bottom-menu"
            />
          ) : null}
        </div>
      </Sider>
      <Layout>
        <Header className="shell-header">
          <Space>
            {mobile && <Button type="text" icon={<MenuOutlined />} onClick={() => setMobileOpen(true)} aria-label="Open navigation" />}
            {!mobile && (
              <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed((value) => !value)}
                aria-label="Toggle navigation"
              />
            )}
          </Space>
          <Space>
            {canReadNotifications && (
              <Dropdown
                trigger={['click']}
                menu={{
                  items:
                    notificationsQuery.data?.notifications.slice(0, 6).map((notification) => ({
                      key: String(notification.id),
                      label: (
                        <div style={{ maxWidth: 300 }}>
                          <strong>{notification.title}</strong>
                          <Typography.Text type="secondary" ellipsis style={{ display: 'block', maxWidth: 280 }}>
                            {notification.body}
                          </Typography.Text>
                        </div>
                      ),
                    })) ?? [{ key: 'empty', label: '暂无通知', disabled: true }],
                  onClick: ({ key }) => {
                    const notification = notificationsQuery.data?.notifications.find((item) => item.id === Number(key))
                    if (notification) void openNotification(notification)
                  },
                }}
              >
                <Tooltip title="通知">
                  <Button type="text" aria-label="Approval notifications" icon={<Badge count={notificationsQuery.data?.unread_count ?? 0} size="small"><BellOutlined /></Badge>} />
                </Tooltip>
              </Dropdown>
            )}
            <Tooltip title={t('shell.language')}>
              <Button type="text" icon={<TranslationOutlined />} onClick={preferences.toggleLocale} />
            </Tooltip>
            <Tooltip title={t('shell.theme')}>
              <Button type="text" icon={preferences.dark ? <SunOutlined /> : <MoonOutlined />} onClick={preferences.toggleTheme} />
            </Tooltip>
            <Tooltip title="GitHub">
              <Button type="text" icon={<GithubOutlined />} href="https://github.com/Kenny3Shen/Agno-AIOS" target="_blank" />
            </Tooltip>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'logout',
                    icon: <SafetyCertificateOutlined />,
                    label: t('shell.logout'),
                    onClick: async () => {
                      await logout()
                      queryClient.clear()
                      window.location.reload()
                    },
                  },
                ],
              }}
            >
              <Button type="text">
                <Avatar size="small">{initials}</Avatar>
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content className="shell-content">
          <Suspense
            fallback={
              <div className="boot-screen">
                <Spin />
              </div>
            }
          >
            <div key={path} className="shell-page-transition">
              {children}
            </div>
          </Suspense>
        </Content>
      </Layout>
      <Drawer
        placement="left"
        size="min(300px, calc(100vw - 32px))"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        title="T.A.I.S"
        styles={{ body: { padding: 8 } }}
      >
        <Menu mode="inline" selectedKeys={path === '/settings' ? [] : [path]} onClick={navigateFromMenu} items={items} />
        {settingsItems?.length ? (
          <Menu mode="inline" selectedKeys={path === '/settings' ? [path] : []} onClick={navigateFromMenu} items={settingsItems} />
        ) : null}
      </Drawer>
    </Layout>
  )
}
