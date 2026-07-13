import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import {
  Avatar,
  Badge,
  Button,
  Drawer,
  Dropdown,
  Empty,
  Grid,
  Layout,
  Menu,
  Popover,
  Skeleton,
  Space,
  Spin,
  Tooltip,
  Typography,
  type MenuProps,
} from 'antd'
import {
  ApiOutlined,
  AuditOutlined,
  BellOutlined,
  BookOutlined,
  BugOutlined,
  BulbOutlined,
  CloudDownloadOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  GithubOutlined,
  InfoCircleOutlined,
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
import { getNotifications, markAllNotificationsRead, markNotificationRead, type Notification } from '@/features/notifications/api'
import { loginPath, nextPathFromLocation } from '@/features/auth/routing'
import { getToken } from '@/shared/auth/storage'
import { hasScope } from '@/shared/auth/permissions'
import { usePreferences } from '@/app/providers/AppProviders'
import {
  defaultOpenNavigationGroupKeys,
  filterNavigationGroups,
  navigationGroupMenuKey,
  readRecentConversationsExpanded,
  writeRecentConversationsExpanded,
  type NavigationGroup,
} from './utils'

const { Header, Sider, Content } = Layout

interface NavigationItem {
  key: string
  icon: ReactNode
  labelKey: string
  scope?: string
}

const navigationGroups: NavigationGroup<NavigationItem>[] = [
  {
    key: 'workspace',
    labelKey: 'workspace',
    items: [
      { key: '/chat', icon: <MessageOutlined />, labelKey: 'chat', scope: 'sessions:write' },
      { key: '/workflow', icon: <NodeIndexOutlined />, labelKey: 'workflow', scope: 'mcp:read' },
    ],
  },
  {
    key: 'capabilities',
    labelKey: 'capabilities',
    items: [
      { key: '/skills', icon: <BulbOutlined />, labelKey: 'skills', scope: 'skill:read' },
      { key: '/mcp', icon: <ApiOutlined />, labelKey: 'mcp', scope: 'mcp:read' },
      { key: '/knowledge', icon: <BookOutlined />, labelKey: 'knowledge', scope: 'knowledge:read' },
      { key: '/memory', icon: <DatabaseOutlined />, labelKey: 'memory', scope: 'memories:read' },
    ],
  },
  {
    key: 'governance',
    labelKey: 'governance',
    items: [
      { key: '/trace', icon: <CodeOutlined />, labelKey: 'trace', scope: 'traces:read' },
      { key: '/evaluations', icon: <ExperimentOutlined />, labelKey: 'evaluations', scope: 'evals:read' },
      { key: '/approvals', icon: <AuditOutlined />, labelKey: 'approvals', scope: 'approvals:read' },
      { key: '/audit', icon: <FileSearchOutlined />, labelKey: 'audit', scope: 'audit:read' },
    ],
  },
  {
    key: 'intelligence',
    labelKey: 'intelligence',
    items: [
      { key: '/cve', icon: <BugOutlined />, labelKey: 'cve', scope: 'cve:read' },
      { key: '/collect', icon: <CloudDownloadOutlined />, labelKey: 'collect', scope: 'collect:write' },
    ],
  },
]

const settingsNav: NavigationItem[] = [{ key: '/settings', icon: <SettingOutlined />, labelKey: 'settings', scope: 'config:read' }]
const defaultOpenNavigationGroups = defaultOpenNavigationGroupKeys(navigationGroups)

const relativeTime = (timestamp: number) => {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000) - timestamp)
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`
  if (seconds < 172800) return 'Yesterday'
  return `${Math.floor(seconds / 86400)} days ago`
}

const notificationKind = (notification: Notification) => {
  const status = typeof notification.data.status === 'string' ? notification.data.status : ''
  if (status === 'rejected' || notification.title.toLowerCase().includes('rejected'))
    return { icon: <CloseCircleOutlined />, className: 'notification-kind-rejected' }
  if (typeof notification.data.approval_id === 'string') return { icon: <AuditOutlined />, className: 'notification-kind-approval' }
  return { icon: <InfoCircleOutlined />, className: 'notification-kind-info' }
}

export function AppFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const router = useRouter()
  const queryClient = useQueryClient()
  const preferences = usePreferences()
  const screens = Grid.useBreakpoint()
  const mobile = !screens.lg
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [openNavigationGroups, setOpenNavigationGroups] = useState(defaultOpenNavigationGroups)
  const [mobileOpenNavigationGroups, setMobileOpenNavigationGroups] = useState(defaultOpenNavigationGroups)
  const [recentConversationsExpanded, setRecentConversationsExpanded] = useState(readRecentConversationsExpanded)
  const [mobileRecentConversationsExpanded, setMobileRecentConversationsExpanded] = useState(false)
  const [notificationOpen, setNotificationOpen] = useState(false)
  const [markingAllNotifications, setMarkingAllNotifications] = useState(false)
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
      filterNavigationGroups(navigationGroups, (scope) => hasScope(userQuery.data, scope)).map((group) => ({
        key: navigationGroupMenuKey(group.key),
        label: t(`shell.groups.${group.labelKey}`),
        children: group.items.map((item) => ({
          key: item.key,
          icon: item.icon,
          label: t(`shell.${item.labelKey}`),
          title: t(`shell.${item.labelKey}`),
        })),
      })),
    [t, userQuery.data]
  )
  const collapsedItems = useMemo<MenuProps['items']>(
    () =>
      filterNavigationGroups(navigationGroups, (scope) => hasScope(userQuery.data, scope)).flatMap((group) =>
        group.items.map((item) => ({
          key: item.key,
          icon: item.icon,
          label: t(`shell.${item.labelKey}`),
          title: t(`shell.${item.labelKey}`),
        }))
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
    setMobileRecentConversationsExpanded(false)
  }
  const navigateToDashboard = () => {
    void router.history.push('/dashboard')
    setMobileOpen(false)
  }
  const toggleRecentConversations = (expanded: boolean) => {
    setRecentConversationsExpanded(expanded)
    writeRecentConversationsExpanded(expanded)
  }
  const openMobileNavigation = () => {
    setMobileRecentConversationsExpanded(false)
    setMobileOpenNavigationGroups([...defaultOpenNavigationGroups])
    setMobileOpen(true)
  }
  const openNotification = async (notification: Notification) => {
    setNotificationOpen(false)
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
  const markAllAsRead = async () => {
    setMarkingAllNotifications(true)
    try {
      await markAllNotificationsRead()
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    } finally {
      setMarkingAllNotifications(false)
    }
  }
  useEffect(() => {
    setMobileOpen(false)
    setMobileRecentConversationsExpanded(false)
    setMobileOpenNavigationGroups([...defaultOpenNavigationGroups])
  }, [path])
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
        <button type="button" className="shell-brand" onClick={navigateToDashboard} aria-label={t('shell.openDashboard')}>
          <span className="brand-mark">T</span>
          <div className="shell-brand-copy">
            <strong>T.A.I.S</strong>
            <small>Trinity AI Security</small>
          </div>
        </button>
        <div className="shell-sider-body">
          <Menu
            mode="inline"
            inlineCollapsed={collapsed}
            openKeys={collapsed ? undefined : openNavigationGroups}
            onOpenChange={setOpenNavigationGroups}
            selectedKeys={path === '/settings' ? [] : [path]}
            items={collapsed ? collapsedItems : items}
            onClick={navigateFromMenu}
            className="shell-menu shell-main-menu"
            tooltip={{ placement: 'right' }}
          />
          {!mobile && !collapsed ? (
            <ChatTaskPanel expanded={recentConversationsExpanded} onExpandedChange={toggleRecentConversations} variant="sider" />
          ) : null}
          {settingsItems?.length ? (
            <Menu
              mode="inline"
              inlineCollapsed={collapsed}
              selectedKeys={path === '/settings' ? [path] : []}
              items={settingsItems}
              onClick={navigateFromMenu}
              className="shell-menu shell-bottom-menu"
              tooltip={{ placement: 'right' }}
            />
          ) : null}
        </div>
      </Sider>
      <Layout>
        <Header className="shell-header">
          <Space>
            {mobile && <Button type="text" icon={<MenuOutlined />} onClick={openMobileNavigation} aria-label={t('shell.openNavigation')} />}
            {!mobile && (
              <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed((value) => !value)}
                aria-label={t('shell.toggleNavigation')}
              />
            )}
          </Space>
          <Space>
            {canReadNotifications && (
              <Popover
                trigger="click"
                placement="bottomRight"
                arrow={false}
                open={notificationOpen}
                onOpenChange={setNotificationOpen}
                classNames={{ root: 'notification-popover' }}
                content={
                  <section className="notification-center" aria-label="Notifications">
                    <header className="notification-center-header">
                      <div>
                        <Typography.Text strong>Notifications</Typography.Text>
                        <Typography.Text type="secondary" className="notification-center-count">
                          {notificationsQuery.data?.unread_count ?? 0} unread
                        </Typography.Text>
                      </div>
                      <Button
                        type="link"
                        size="small"
                        loading={markingAllNotifications}
                        disabled={!notificationsQuery.data?.unread_count}
                        onClick={() => void markAllAsRead()}
                      >
                        Mark all as read
                      </Button>
                    </header>
                    <div className="notification-center-list">
                      {notificationsQuery.isLoading ? (
                        <div className="notification-center-loading" aria-label="Loading notifications">
                          <Skeleton active title={{ width: '42%' }} paragraph={{ rows: 2 }} />
                          <Skeleton active title={{ width: '56%' }} paragraph={{ rows: 2 }} />
                        </div>
                      ) : notificationsQuery.data?.notifications.length ? (
                        notificationsQuery.data.notifications.slice(0, 6).map((notification) => {
                          const kind = notificationKind(notification)
                          return (
                            <button
                              key={notification.id}
                              type="button"
                              className={`notification-item ${notification.read ? 'notification-item-read' : 'notification-item-unread'}`}
                              onClick={() => void openNotification(notification)}
                            >
                              <span className={`notification-item-icon ${kind.className}`}>{kind.icon}</span>
                              <span className="notification-item-content">
                                <span className="notification-item-title">{notification.title}</span>
                                <span className="notification-item-body" title={notification.body}>
                                  {notification.body}
                                </span>
                                <span className="notification-item-time">{relativeTime(notification.created_at)}</span>
                              </span>
                              {!notification.read && <span className="notification-item-unread-dot" aria-label="Unread" />}
                            </button>
                          )
                        })
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通知" className="notification-center-empty" />
                      )}
                    </div>
                  </section>
                }
              >
                <Tooltip title="通知">
                  <Button
                    type="text"
                    aria-label="Notifications"
                    icon={
                      <Badge count={notificationsQuery.data?.unread_count ?? 0} size="small">
                        <BellOutlined />
                      </Badge>
                    }
                  />
                </Tooltip>
              </Popover>
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
        onClose={() => {
          setMobileOpen(false)
          setMobileRecentConversationsExpanded(false)
          setMobileOpenNavigationGroups([...defaultOpenNavigationGroups])
        }}
        title="T.A.I.S"
        styles={{ body: { padding: 8 } }}
      >
        <div className="shell-drawer-body">
          <Menu
            mode="inline"
            openKeys={mobileOpenNavigationGroups}
            onOpenChange={setMobileOpenNavigationGroups}
            selectedKeys={path === '/settings' ? [] : [path]}
            onClick={navigateFromMenu}
            items={items}
            className="shell-menu shell-main-menu shell-drawer-menu"
          />
          <ChatTaskPanel
            expanded={mobileRecentConversationsExpanded}
            onExpandedChange={setMobileRecentConversationsExpanded}
            onNavigate={() => {
              setMobileOpen(false)
              setMobileRecentConversationsExpanded(false)
            }}
            variant="drawer"
          />
          {settingsItems?.length ? (
            <Menu
              mode="inline"
              selectedKeys={path === '/settings' ? [path] : []}
              onClick={navigateFromMenu}
              items={settingsItems}
              className="shell-menu shell-bottom-menu"
            />
          ) : null}
        </div>
      </Drawer>
    </Layout>
  )
}
