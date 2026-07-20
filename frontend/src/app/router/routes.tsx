import { lazy } from 'react'
import { createHashHistory, createRootRoute, createRoute, createRouter, Outlet, redirect } from '@tanstack/react-router'
import { AppFrame } from '@/app/shell/AppFrame'
import { LoginPage } from '@/features/auth'
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH, loginPath, nextPathFromLocation } from '@/features/auth/routing'
import { getToken } from '@/shared/auth/storage'

const DashboardPage = lazy(() => import('@/features/dashboard').then((module) => ({ default: module.DashboardPage })))
const ChatPage = lazy(() => import('@/features/chat').then((module) => ({ default: module.ChatPage })))
const WorkflowPage = lazy(() => import('@/features/workflow').then((module) => ({ default: module.WorkflowPage })))
const SkillsPage = lazy(() => import('@/features/skills').then((module) => ({ default: module.SkillsPage })))
const McpPage = lazy(() => import('@/features/mcp').then((module) => ({ default: module.McpPage })))
const KnowledgePage = lazy(() => import('@/features/knowledge').then((module) => ({ default: module.KnowledgePage })))
const TracePage = lazy(() => import('@/features/trace').then((module) => ({ default: module.TracePage })))
const MemoryPage = lazy(() => import('@/features/memory').then((module) => ({ default: module.MemoryPage })))
const EvaluationsPage = lazy(() => import('@/features/evaluations').then((module) => ({ default: module.EvaluationsPage })))
const ApprovalsPage = lazy(() => import('@/features/approvals').then((module) => ({ default: module.ApprovalsPage })))
const AuditPage = lazy(() => import('@/features/audit').then((module) => ({ default: module.AuditPage })))
const CvePage = lazy(() => import('@/features/cve').then((module) => ({ default: module.CvePage })))
const IpBlacklistPage = lazy(() =>
  import('@/features/ip-blacklist').then((module) => ({ default: module.IpBlacklistPage })),
)
const CollectPage = lazy(() => import('@/features/collect').then((module) => ({ default: module.CollectPage })))
const SettingsPage = lazy(() => import('@/features/settings').then((module) => ({ default: module.SettingsPage })))

const rootRoute = createRootRoute({ component: () => <Outlet /> })
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: getToken() ? DEFAULT_AUTHENTICATED_PATH : LOGIN_PATH, replace: true })
  },
})
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: LOGIN_PATH,
  component: LoginPage,
})
const protectedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'protected',
  beforeLoad: ({ location }) => {
    if (getToken()) return
    throw redirect({ href: loginPath(nextPathFromLocation(location)), replace: true })
  },
  component: () => (
    <AppFrame>
      <Outlet />
    </AppFrame>
  ),
})
const pages = [
  ['/dashboard', DashboardPage],
  ['/chat', ChatPage],
  ['/workflow', WorkflowPage],
  ['/skills', SkillsPage],
  ['/mcp', McpPage],
  ['/knowledge', KnowledgePage],
  ['/trace', TracePage],
  ['/memory', MemoryPage],
  ['/evaluations', EvaluationsPage],
  ['/approvals', ApprovalsPage],
  ['/cve', CvePage],
  ['/ip-blacklist', IpBlacklistPage],
  ['/collect', CollectPage],
  ['/audit', AuditPage],
  ['/settings', SettingsPage],
] as const
const protectedPages = pages.map(([path, component]) => createRoute({ getParentRoute: () => protectedRoute, path, component }))
const routeTree = rootRoute.addChildren([indexRoute, loginRoute, protectedRoute.addChildren(protectedPages)])
export const router = createRouter({ routeTree, history: createHashHistory() })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
