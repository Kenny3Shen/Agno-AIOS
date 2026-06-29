import {
  Activity,
  Bot,
  Cable,
  FileSearch,
  Globe,
  LibraryBig,
  Monitor,
  Route,
  Settings2,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { WorkspaceGroup, WorkspaceTabId } from '#/lib/workspace.ts'

export type WorkspaceNavItem = {
  id: WorkspaceTabId
  label: string
  description: string
  group: WorkspaceGroup
  badge?: string
  icon: LucideIcon
}

export const workspaceGroups: WorkspaceGroup[] = [
  'AI 工作台',
  '情报检索',
  '运营配置',
]

export const workspaceNavItems: WorkspaceNavItem[] = [
  {
    id: 'situation',
    label: '态势总览',
    description: 'Agent 运行态势与异常样本',
    group: 'AI 工作台',
    badge: 'Live',
    icon: Activity,
  },
  {
    id: 'chat',
    label: 'Agent 对话',
    description: '任务编排、流式回答与会话追踪',
    group: 'AI 工作台',
    icon: Bot,
  },
  {
    id: 'knowledge',
    label: 'RAG 知识库',
    description: '文档写入、检索验证与参数视图',
    group: 'AI 工作台',
    icon: LibraryBig,
  },
  {
    id: 'tracing',
    label: '运行观测',
    description: 'Trace、Span 与执行上下文',
    group: 'AI 工作台',
    icon: Route,
  },
  {
    id: 'mcp',
    label: 'MCP 工具中枢',
    description: '服务、Token 与外部 Hi-Agent',
    group: 'AI 工作台',
    icon: Cable,
  },
  {
    id: 'cve',
    label: 'CVE 情报',
    description: '漏洞检索与来源过滤',
    group: '情报检索',
    icon: FileSearch,
  },
  {
    id: 'asset',
    label: '资产画像',
    description: '指纹、IP 与暴露面查询',
    group: '情报检索',
    icon: Monitor,
  },
  {
    id: 'url2md',
    label: '网页解析',
    description: 'URL 转 Markdown 查看',
    group: '情报检索',
    icon: Globe,
  },
  {
    id: 'skills',
    label: 'Skills 管理',
    description: '安全能力模块开关与脚本清单',
    group: '运营配置',
    icon: Wrench,
  },
  {
    id: 'settings',
    label: '系统配置',
    description: '模型路由与运行时参数',
    group: '运营配置',
    icon: Settings2,
  },
]
