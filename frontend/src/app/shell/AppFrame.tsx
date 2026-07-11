import { Suspense, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useRouterState } from '@tanstack/react-router'
import { Avatar, Button, Drawer, Dropdown, Grid, Layout, Menu, Space, Spin, Tooltip, Typography, type MenuProps } from 'antd'
import {
  ApiOutlined, AuditOutlined, BookOutlined, BugOutlined, BulbOutlined, CalendarOutlined, CloudDownloadOutlined,
  CodeOutlined, DashboardOutlined, DatabaseOutlined, ExperimentOutlined, FileSearchOutlined, GithubOutlined,
  MenuFoldOutlined, MenuOutlined, MenuUnfoldOutlined, MessageOutlined, MoonOutlined, NodeIndexOutlined, SafetyCertificateOutlined,
  SettingOutlined, SunOutlined, TranslationOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { AuthPage, authKeys, currentUserQuery, logout } from '@/features/auth'
import { getToken } from '@/shared/auth/storage'
import { hasScope } from '@/shared/auth/permissions'
import { usePreferences } from '@/app/providers/AppProviders'
import { joinMenuGroups, splitNavigation } from './utils'

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
  { key: '/scheduler', icon: <CalendarOutlined />, labelKey: 'scheduler', scope: 'schedules:read' },
  { key: '/cve', icon: <BugOutlined />, labelKey: 'cve', scope: 'cve:read' },
  { key: '/collect', icon: <CloudDownloadOutlined />, labelKey: 'collect', scope: 'collect:write' },
  { key: '/audit', icon: <FileSearchOutlined />, labelKey: 'audit', scope: 'audit:read' },
  { key: '/settings', icon: <SettingOutlined />, labelKey: 'settings', scope: 'config:read' },
]

export function AppFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const preferences = usePreferences()
  const screens = Grid.useBreakpoint()
  const mobile = !screens.lg
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const path = useRouterState({ select: (state) => state.location.pathname })
  const token = getToken()
  const userQuery = useQuery({ ...currentUserQuery(), enabled: Boolean(token), retry: false })

  const authenticate = async () => {
    await queryClient.invalidateQueries({ queryKey: authKeys.current })
    await userQuery.refetch()
  }

  const items = useMemo<MenuProps['items']>(() => joinMenuGroups(
    splitNavigation(nav).map((group) => group
      .filter((item) => !item.scope || hasScope(userQuery.data, item.scope))
      .map((item) => ({
        key: item.key,
        icon: item.icon,
        label: <Link to={item.key}>{t(`shell.${item.labelKey}`)}</Link>,
      }))),
  ), [t, userQuery.data])
  useEffect(() => setMobileOpen(false), [path])

  if (!token || userQuery.isError) return <AuthPage onAuthenticated={authenticate} />
  if (userQuery.isLoading) return <div className="boot-screen"><Spin size="large" /></div>

  const initials = userQuery.data?.email.slice(0, 2).toUpperCase() ?? 'AI'
  return (
    <Layout className="app-shell">
      <Sider width={264} collapsedWidth={76} collapsed={mobile ? true : collapsed} className="shell-sider" trigger={null}>
        <div className="shell-brand"><span className="brand-mark">T</span>{!collapsed && !mobile && <div><strong>T.A.I.S</strong><small>Trinity AI Security</small></div>}</div>
        <Menu mode="inline" selectedKeys={[path]} items={items} className="shell-menu" />
        <div className="shell-identity"><Avatar shape="square">{initials}</Avatar>{!collapsed && !mobile && <Typography.Text ellipsis>{userQuery.data?.email}</Typography.Text>}</div>
      </Sider>
      <Layout>
        <Header className="shell-header">
          <Space>
            {mobile && <Button type="text" icon={<MenuOutlined />} onClick={() => setMobileOpen(true)} aria-label="Open navigation" />}
            {!mobile && <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed((value) => !value)} aria-label="Toggle navigation" />}
          </Space>
          <Space>
            <Tooltip title={t('shell.language')}><Button type="text" icon={<TranslationOutlined />} onClick={preferences.toggleLocale} /></Tooltip>
            <Tooltip title={t('shell.theme')}><Button type="text" icon={preferences.dark ? <SunOutlined /> : <MoonOutlined />} onClick={preferences.toggleTheme} /></Tooltip>
            <Tooltip title="GitHub"><Button type="text" icon={<GithubOutlined />} href="https://github.com/Kenny3Shen/Agno-AIOS" target="_blank" /></Tooltip>
            <Dropdown menu={{ items: [{ key: 'logout', icon: <SafetyCertificateOutlined />, label: t('shell.logout'), onClick: async () => { await logout(); queryClient.clear(); window.location.reload() } }] }}>
              <Button type="text"><Avatar size="small">{initials}</Avatar></Button>
            </Dropdown>
          </Space>
        </Header>
        <Content className="shell-content"><Suspense fallback={<div className="boot-screen"><Spin /></div>}>{children}</Suspense></Content>
      </Layout>
      <Drawer placement="left" size="min(300px, calc(100vw - 32px))" open={mobileOpen} onClose={() => setMobileOpen(false)} title="T.A.I.S" styles={{ body: { padding: 8 } }}>
        <Menu mode="inline" selectedKeys={[path]} onClick={() => setMobileOpen(false)} items={items} />
      </Drawer>
    </Layout>
  )
}
