type TraceApiItem = {
  trace_id?: string
  name?: string
  status?: string
  duration_ms?: number
  start_time?: string
  end_time?: string
  agent_id?: string | null
  session_id?: string | null
}

type KnowledgeStatus = {
  documents?: number
  chunks?: number
  collection?: string
  top_k?: number
}

type KnowledgeDocument = {
  id?: string
  title?: string
  source?: string
  chunks?: number
  created_at?: string
}

type SkillItem = {
  name?: string
  description?: string
  enabled?: boolean
  has_scripts?: boolean
}

type McpConfig = {
  services?: Record<string, boolean>
  mcp_url?: string
  fastmcp?: string
}

type ModelItem = {
  id?: string
  name?: string
  model_id?: string
  description?: string
  enabled?: boolean
  configured?: boolean
}

export type DashboardTrace = {
  traceId: string
  name: string
  status: string
  durationMs: number
  startTime: string
  endTime: string
  agentId: string
  sessionId: string
}

export type DashboardSkill = {
  name: string
  description: string
  enabled: boolean
  hasScripts: boolean
}

export type DashboardDocument = {
  id: string
  title: string
  source: string
  chunks: number
  createdAt: string
}

export type DashboardModel = {
  id: string
  name: string
  modelId: string
  description: string
  enabled: boolean
  configured: boolean
}

export type DashboardSnapshot = {
  apiOnline: boolean
  degraded: boolean
  fetchedAt: string
  backendLabel: string
  knowledgeCollection: string
  topK: number
  liveTraces: number
  successRate: number
  averageDurationMs: number
  knowledgeDocuments: number
  knowledgeChunks: number
  enabledSkills: number
  enabledServices: number
  activeModelName: string
  activeModelId: string
  mcpUrl: string
  mcpFastmcp: string
  serviceStates: Array<{ name: string; enabled: boolean }>
  traces: DashboardTrace[]
  skills: DashboardSkill[]
  documents: DashboardDocument[]
  models: DashboardModel[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const BACKEND_RETRY_DELAY_MS = 60_000

let backendRetryAfter = 0

const now = () => new Date().toISOString()

const minutesAgo = (minutes: number) =>
  new Date(Date.now() - minutes * 60_000).toISOString()

export const fallbackDashboardSnapshot: DashboardSnapshot = {
  apiOnline: false,
  degraded: true,
  fetchedAt: now(),
  backendLabel: 'local demo',
  knowledgeCollection: 'security_knowledge',
  topK: 5,
  liveTraces: 18,
  successRate: 94,
  averageDurationMs: 842,
  knowledgeDocuments: 28,
  knowledgeChunks: 186,
  enabledSkills: 5,
  enabledServices: 2,
  activeModelName: 'SecOps Analyst',
  activeModelId: 'gpt-4.1',
  mcpUrl: '/mcp/',
  mcpFastmcp: 'in-process',
  serviceStates: [
    { name: 'basic', enabled: true },
    { name: 'agent', enabled: true },
    { name: 'playbook', enabled: false },
  ],
  traces: [
    {
      traceId: 'trace-edge-proxy-triage',
      name: 'Edge proxy exposure triage',
      status: 'OK',
      durationMs: 724,
      startTime: minutesAgo(4),
      endTime: minutesAgo(3),
      agentId: 'threat-hunter',
      sessionId: 'soc-ops-01',
    },
    {
      traceId: 'trace-rag-context-merge',
      name: 'RAG evidence stitching',
      status: 'OK',
      durationMs: 981,
      startTime: minutesAgo(11),
      endTime: minutesAgo(10),
      agentId: 'knowledge-watch',
      sessionId: 'soc-ops-02',
    },
    {
      traceId: 'trace-mcp-route-audit',
      name: 'MCP route access audit',
      status: 'ERROR',
      durationMs: 1418,
      startTime: minutesAgo(18),
      endTime: minutesAgo(16),
      agentId: 'control-plane',
      sessionId: 'soc-ops-03',
    },
    {
      traceId: 'trace-asset-surface-review',
      name: 'Asset surface review',
      status: 'OK',
      durationMs: 612,
      startTime: minutesAgo(23),
      endTime: minutesAgo(22),
      agentId: 'asset-radar',
      sessionId: 'soc-ops-04',
    },
  ],
  skills: [
    {
      name: 'cve_triage',
      description: 'CVE 线索归并与利用链摘要',
      enabled: true,
      hasScripts: true,
    },
    {
      name: 'asset_hunt',
      description: '资产指纹与暴露面回溯',
      enabled: true,
      hasScripts: true,
    },
    {
      name: 'rag_watch',
      description: '知识库命中与上下文召回',
      enabled: true,
      hasScripts: false,
    },
    {
      name: 'playbook_guard',
      description: '剧本执行安全闸门',
      enabled: false,
      hasScripts: true,
    },
  ],
  documents: [
    {
      id: 'doc-1',
      title: '外网代理暴露处置手册',
      source: 'playbook',
      chunks: 26,
      createdAt: '2026-06-27T17:18:00+08:00',
    },
    {
      id: 'doc-2',
      title: 'MCP 接入审计基线',
      source: 'policy',
      chunks: 18,
      createdAt: '2026-06-26T13:42:00+08:00',
    },
    {
      id: 'doc-3',
      title: '高危 CVE 应急复盘',
      source: 'incident',
      chunks: 42,
      createdAt: '2026-06-24T09:20:00+08:00',
    },
  ],
  models: [
    {
      id: 'secops-main',
      name: 'SecOps Analyst',
      modelId: 'gpt-4.1',
      description: '统一研判与工具调度',
      enabled: true,
      configured: true,
    },
    {
      id: 'triage-fast',
      name: 'Triage Fastlane',
      modelId: 'gpt-4.1-mini',
      description: '轻量级线索分类',
      enabled: true,
      configured: true,
    },
    {
      id: 'cn-rag',
      name: 'CN Knowledge',
      modelId: 'qwen-plus',
      description: '中文知识检索增强',
      enabled: false,
      configured: true,
    },
  ],
}

async function requestJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })

    if (!response.ok) {
      return null
    }

    return (await response.json()) as T
  } catch {
    return null
  }
}

function withFallback<T>(value: T | null | undefined, fallback: T): T {
  return value ?? fallback
}

function normalizeTrace(item: TraceApiItem, index: number): DashboardTrace {
  return {
    traceId: withFallback(item.trace_id, `trace-${index + 1}`),
    name: withFallback(item.name, 'Unknown trace'),
    status: withFallback(item.status, 'UNSET'),
    durationMs: typeof item.duration_ms === 'number' ? item.duration_ms : 0,
    startTime: withFallback(item.start_time, now()),
    endTime: withFallback(item.end_time, withFallback(item.start_time, now())),
    agentId: withFallback(item.agent_id ?? undefined, 'unknown-agent'),
    sessionId: withFallback(item.session_id ?? undefined, 'unknown-session'),
  }
}

function formatServiceStates(services: Record<string, boolean> | undefined) {
  if (!services) {
    return fallbackDashboardSnapshot.serviceStates
  }

  const entries = Object.entries(services).map(([name, enabled]) => ({
    name,
    enabled,
  }))

  return entries.length ? entries : fallbackDashboardSnapshot.serviceStates
}

function buildFallbackSnapshot(): DashboardSnapshot {
  return {
    ...fallbackDashboardSnapshot,
    fetchedAt: now(),
  }
}

export async function fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
  if (backendRetryAfter > Date.now()) {
    return buildFallbackSnapshot()
  }

  const health = await requestJson<{ status?: string }>('/api/health')

  if (!health) {
    backendRetryAfter = Date.now() + BACKEND_RETRY_DELAY_MS
    return buildFallbackSnapshot()
  }

  backendRetryAfter = 0

  const [
    tracesPayload,
    knowledgePayload,
    skillsPayload,
    mcpPayload,
    modelsPayload,
  ] = await Promise.all([
    requestJson<{ items?: TraceApiItem[]; total_count?: number }>(
      '/api/traces?limit=6',
    ),
    requestJson<{ status?: KnowledgeStatus; documents?: KnowledgeDocument[] }>(
      '/api/knowledge',
    ),
    requestJson<{ skills?: SkillItem[] }>('/api/skills'),
    requestJson<McpConfig>('/api/mcp/config'),
    requestJson<{ active_model_id?: string; models?: ModelItem[] }>(
      '/api/models',
    ),
  ])

  const apiOnline = health.status === 'ok'

  const traces =
    tracesPayload?.items?.map(normalizeTrace) ??
    fallbackDashboardSnapshot.traces
  const totalTraces = tracesPayload?.total_count ?? traces.length

  const skills =
    skillsPayload?.skills?.map((item, index) => ({
      name: withFallback(item.name, `skill-${index + 1}`),
      description: withFallback(item.description, '未提供技能描述'),
      enabled: Boolean(item.enabled),
      hasScripts: Boolean(item.has_scripts),
    })) ?? fallbackDashboardSnapshot.skills

  const documents =
    knowledgePayload?.documents?.map((item, index) => ({
      id: withFallback(item.id, `doc-${index + 1}`),
      title: withFallback(item.title, '未命名知识文档'),
      source: withFallback(item.source, 'manual'),
      chunks: typeof item.chunks === 'number' ? item.chunks : 0,
      createdAt: withFallback(item.created_at, now()),
    })) ?? fallbackDashboardSnapshot.documents

  const models =
    modelsPayload?.models?.map((item, index) => ({
      id: withFallback(item.id, `model-${index + 1}`),
      name: withFallback(item.name, 'Unnamed model'),
      modelId: withFallback(item.model_id, 'unknown-model'),
      description: withFallback(item.description, '未提供模型说明'),
      enabled: item.enabled !== false,
      configured: item.configured !== false,
    })) ?? fallbackDashboardSnapshot.models

  const activeModel =
    models.find((item) => item.id === modelsPayload?.active_model_id) ??
    models.find((item) => item.enabled) ??
    fallbackDashboardSnapshot.models[0]

  const okCount = traces.filter((item) => item.status === 'OK').length
  const successRate = traces.length
    ? Math.round((okCount / traces.length) * 100)
    : fallbackDashboardSnapshot.successRate
  const averageDurationMs = traces.length
    ? Math.round(
        traces.reduce((total, item) => total + item.durationMs, 0) /
          traces.length,
      )
    : fallbackDashboardSnapshot.averageDurationMs

  const knowledgeDocuments =
    knowledgePayload?.status?.documents ?? documents.length
  const knowledgeChunks =
    knowledgePayload?.status?.chunks ??
    documents.reduce((total, item) => total + item.chunks, 0)
  const topK = knowledgePayload?.status?.top_k ?? fallbackDashboardSnapshot.topK
  const knowledgeCollection =
    knowledgePayload?.status?.collection ??
    fallbackDashboardSnapshot.knowledgeCollection

  const serviceStates = formatServiceStates(mcpPayload?.services)
  const enabledServices = serviceStates.filter((item) => item.enabled).length
  const enabledSkills = skills.filter((item) => item.enabled).length

  const endpointCount = 6
  const successCount = [
    health,
    tracesPayload,
    knowledgePayload,
    skillsPayload,
    mcpPayload,
    modelsPayload,
  ].filter(Boolean).length

  return {
    apiOnline,
    degraded: successCount < endpointCount,
    fetchedAt: now(),
    backendLabel:
      successCount === endpointCount
        ? 'live api'
        : apiOnline
          ? 'partially degraded'
          : 'local demo',
    knowledgeCollection,
    topK,
    liveTraces: totalTraces,
    successRate,
    averageDurationMs,
    knowledgeDocuments,
    knowledgeChunks,
    enabledSkills,
    enabledServices,
    activeModelName: activeModel.name,
    activeModelId: activeModel.modelId,
    mcpUrl: withFallback(mcpPayload?.mcp_url, fallbackDashboardSnapshot.mcpUrl),
    mcpFastmcp: withFallback(
      mcpPayload?.fastmcp,
      fallbackDashboardSnapshot.mcpFastmcp,
    ),
    serviceStates,
    traces,
    skills,
    documents,
    models,
  }
}

export function formatDuration(durationMs: number) {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)}s`
  }

  return `${durationMs}ms`
}

export function formatCount(value: number) {
  if (value >= 10_000) {
    return `${(value / 10_000).toFixed(1)}w`
  }

  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}k`
  }

  return `${value}`
}

export function formatSnapshotTime(isoTime: string) {
  const date = new Date(isoTime)

  if (Number.isNaN(date.getTime())) {
    return '--'
  }

  const normalized = date.toISOString()
  return `${normalized.slice(5, 10)} ${normalized.slice(11, 16)}`
}
