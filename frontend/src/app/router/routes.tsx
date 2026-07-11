import { lazy } from 'react'
import { createHashHistory, createRootRoute, createRoute, createRouter, Outlet, redirect } from '@tanstack/react-router'
import { AppFrame } from '@/app/shell/AppFrame'

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
const SchedulerPage = lazy(() => import('@/features/scheduler').then((module) => ({ default: module.SchedulerPage })))
const CvePage = lazy(() => import('@/features/cve').then((module) => ({ default: module.CvePage })))
const CollectPage = lazy(() => import('@/features/collect').then((module) => ({ default: module.CollectPage })))
const SettingsPage = lazy(() => import('@/features/settings').then((module) => ({ default: module.SettingsPage })))

const rootRoute = createRootRoute({ component: () => <AppFrame><Outlet /></AppFrame> })
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', beforeLoad: () => { throw redirect({ to: '/dashboard', replace: true }) } })
const pages = [
  ['/dashboard', DashboardPage], ['/chat', ChatPage], ['/workflow', WorkflowPage],
  ['/skills', SkillsPage], ['/mcp', McpPage], ['/knowledge', KnowledgePage], ['/trace', TracePage],
  ['/memory', MemoryPage], ['/evaluations', EvaluationsPage], ['/approvals', ApprovalsPage], ['/scheduler', SchedulerPage],
  ['/cve', CvePage], ['/collect', CollectPage], ['/audit', AuditPage], ['/settings', SettingsPage],
] as const
const routeTree = rootRoute.addChildren([indexRoute, ...pages.map(([path, component]) => createRoute({ getParentRoute: () => rootRoute, path, component }))])
export const router = createRouter({ routeTree, history: createHashHistory() })

declare module '@tanstack/react-router' { interface Register { router: typeof router } }
