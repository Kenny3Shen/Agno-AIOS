export type WorkspaceTabId =
  | 'situation'
  | 'chat'
  | 'knowledge'
  | 'tracing'
  | 'mcp'
  | 'cve'
  | 'asset'
  | 'url2md'
  | 'skills'
  | 'settings'

export type WorkspaceGroup = 'AI 工作台' | '情报检索' | '运营配置'

export type TraceStatus = 'OK' | 'ERROR' | 'UNSET' | string

export interface WorkspaceMessage {
  role: 'user' | 'assistant'
  content: string
  final?: boolean
}

export interface ChatSession {
  session_id: string
  preview: string
  created_at: number
  updated_at: number
}

export interface ModelConfig {
  id: string
  name: string
  model_id: string
  base_url: string
  api_key: string
  description: string
  enabled: boolean
  builtin: boolean
  configured?: boolean
}

export interface SettingsBundle {
  settings: Record<string, string>
  active_model_id: string
  models: ModelConfig[]
}

export interface SkillInfo {
  name: string
  description: string
  enabled: boolean
  has_scripts: boolean
  scripts: string[]
}

export type McpServiceId = 'basic' | 'agent' | 'playbook'

export interface McpConfig {
  services: Record<McpServiceId, boolean>
  control_mode?: string
  fastmcp?: string
  mcp_url?: string
  config_path?: string
  tokens_db_path?: string
}

export interface McpTokenInfo {
  id: number
  name: string
  token: string
  created_at: number
  expires_at: number
}

export interface HiAgentEntry {
  name: string
  url: string
  description: string
  enabled: boolean
}

export interface McpBundle {
  config: McpConfig
  tokens: McpTokenInfo[]
  hiAgents: HiAgentEntry[]
}

export interface KnowledgeStatus {
  collection: string
  storage?: string
  documents: number
  chunks: number
  embedding: string
  embedding_dimensions?: number | null
  rerank_enabled: boolean
  top_k?: number
  retrieval_candidates?: number
  chunk_size?: number
  chunk_overlap?: number
}

export interface KnowledgeDocument {
  id: string
  title: string
  source: string
  chunks: number
  created_at: string
  metadata?: Record<string, string>
}

export interface KnowledgeSearchResult {
  content: string
  score: number
  distance: number | null
  doc_id: string
  title: string
  source: string
  chunk_index: number
  metadata?: Record<string, unknown>
}

export interface KnowledgeBundle {
  status: KnowledgeStatus
  documents: KnowledgeDocument[]
}

export interface TraceItem {
  trace_id: string
  name: string
  status: TraceStatus
  duration_ms: number
  start_time: string
  end_time: string
  total_spans?: number
  error_count?: number
  run_id?: string | null
  session_id?: string | null
  user_id?: string | null
  agent_id?: string | null
  team_id?: string | null
  workflow_id?: string | null
}

export interface SpanItem {
  span_id: string
  trace_id: string
  parent_span_id?: string | null
  name: string
  status_code: TraceStatus
  status_message?: string | null
  duration_ms: number
  start_time: string
  end_time: string
  attributes?: Record<string, unknown> | null
  events?: Array<Record<string, unknown>> | null
  kind?: string | null
}

export interface SpanTreeNode {
  span: SpanItem
  children: SpanTreeNode[]
}

export interface TraceDetailResponse {
  trace: TraceItem
  spans: SpanItem[]
  tree: SpanTreeNode[]
}

export interface TraceListResponse {
  items: TraceItem[]
  total_count: number
  page: number
  limit: number
}

export interface CveResult {
  id: number
  cve_id: string
  github_url: string
  description: string
  source: string
  create_time: string
}

export interface CveSearchResponse {
  items: CveResult[]
  total: number
}

export interface AssetResult {
  site: string
  hostname: string
  ip: string
  title: string
  status: number
  http_server: string
  finger: string[]
  tag: string[]
  port_info: number[]
  os_info: string[]
  ip_type: string
  domain: string[]
}

export interface AssetSearchResponse {
  status: number
  items: AssetResult[]
  total: number
  message?: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const BACKEND_CACHE_OK_MS = 15_000
const BACKEND_CACHE_FAIL_MS = 60_000

let backendAvailable: boolean | null = null
let backendExpiresAt = 0

const nowSeconds = () => Math.floor(Date.now() / 1000)

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function createSessionId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `preview-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function isoMinutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString()
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  fallbackMessage = '请求失败',
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as Record<
      string,
      unknown
    >
    const detail =
      (typeof payload.detail === 'string' && payload.detail) ||
      (typeof payload.message === 'string' && payload.message) ||
      fallbackMessage
    throw new Error(detail)
  }

  return (await response.json()) as T
}

export async function isBackendOnline(force = false) {
  const now = Date.now()
  if (!force && backendAvailable !== null && now < backendExpiresAt) {
    return backendAvailable
  }

  try {
    const response = await fetch(`${API_BASE}/api/health`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })
    backendAvailable = response.ok
    backendExpiresAt =
      now + (response.ok ? BACKEND_CACHE_OK_MS : BACKEND_CACHE_FAIL_MS)
    return response.ok
  } catch {
    backendAvailable = false
    backendExpiresAt = now + BACKEND_CACHE_FAIL_MS
    return false
  }
}

export function compactId(value: string | null | undefined) {
  if (!value) return 'n/a'
  if (value.length <= 12) return value
  return `${value.slice(0, 6)}...${value.slice(-4)}`
}

export function formatUnixDate(timestamp: number) {
  if (!timestamp) return 'Never'
  return new Date(timestamp * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatIsoDate(isoTime: string) {
  const date = new Date(isoTime)
  if (Number.isNaN(date.getTime())) return '--'
  const normalized = date.toISOString()
  return `${normalized.slice(5, 10)} ${normalized.slice(11, 16)}`
}

export function formatDurationMs(durationMs: number) {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)}s`
  }
  return `${Math.round(durationMs)}ms`
}

let previewModels: SettingsBundle = {
  active_model_id: 'secops-main',
  models: [
    {
      id: 'secops-main',
      name: 'SecOps Analyst',
      model_id: 'gpt-4.1',
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-preview-****************',
      description: '默认用于复杂研判、知识归并与工具路由。',
      enabled: true,
      builtin: true,
      configured: true,
    },
    {
      id: 'triage-fast',
      name: 'Triage Fastlane',
      model_id: 'gpt-4.1-mini',
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-preview-****************',
      description: '面向高频告警分类与快速摘要。',
      enabled: true,
      builtin: true,
      configured: true,
    },
    {
      id: 'cn-rag',
      name: 'CN Knowledge',
      model_id: 'qwen-plus',
      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      api_key: 'preview-config-missing',
      description: '中文知识检索增强模型。',
      enabled: false,
      builtin: false,
      configured: false,
    },
  ],
  settings: {
    MCP_SERVER_URL: 'http://127.0.0.1:8000/mcp/',
    MCP_TOKEN: 'preview-token-hidden',
    FEISHU_WEBHOOK_URL: 'https://open.feishu.cn/open-apis/bot/v2/hook/preview',
  },
}

let previewSkills: SkillInfo[] = [
  {
    name: 'cve_triage',
    description: 'CVE 线索归并与利用链摘要。',
    enabled: true,
    has_scripts: true,
    scripts: ['search_cve.py', 'summarize_exploit.py'],
  },
  {
    name: 'asset_hunt',
    description: '资产指纹画像与暴露面回溯。',
    enabled: true,
    has_scripts: true,
    scripts: ['fingerprint_search.py', 'surface_report.py'],
  },
  {
    name: 'rag_watch',
    description: 'RAG 文档命中、Chunk 质量和召回验证。',
    enabled: true,
    has_scripts: false,
    scripts: [],
  },
  {
    name: 'playbook_guard',
    description: '对处置剧本执行前置安全闸门。',
    enabled: false,
    has_scripts: true,
    scripts: ['preflight_guard.py'],
  },
]

let previewKnowledgeDocuments: KnowledgeDocument[] = [
  {
    id: 'doc-edge-proxy',
    title: '外网代理暴露处置手册',
    source: 'playbook',
    chunks: 26,
    created_at: '2026-06-27T17:18:00+08:00',
    metadata: { owner: 'soc', severity: 'high' },
  },
  {
    id: 'doc-mcp-baseline',
    title: 'MCP 接入审计基线',
    source: 'policy',
    chunks: 18,
    created_at: '2026-06-26T13:42:00+08:00',
    metadata: { owner: 'platform', scope: 'mcp' },
  },
  {
    id: 'doc-cve-review',
    title: '高危 CVE 应急复盘',
    source: 'incident',
    chunks: 42,
    created_at: '2026-06-24T09:20:00+08:00',
    metadata: { owner: 'blue-team', tag: 'postmortem' },
  },
]

let previewKnowledgeStatus: KnowledgeStatus = {
  collection: 'security_knowledge',
  storage: 'pgvector',
  documents: previewKnowledgeDocuments.length,
  chunks: previewKnowledgeDocuments.reduce(
    (total, item) => total + item.chunks,
    0,
  ),
  embedding: 'BAAI/bge-small-zh-v1.5',
  embedding_dimensions: 512,
  rerank_enabled: true,
  top_k: 5,
  retrieval_candidates: 16,
  chunk_size: 1200,
  chunk_overlap: 160,
}

let previewMcpConfig: McpConfig = {
  services: {
    basic: true,
    agent: true,
    playbook: false,
  },
  control_mode: 'fastmcp',
  fastmcp: 'in-process',
  mcp_url: 'http://127.0.0.1:8000/mcp/',
  config_path: 'tmp/mcp_config.json',
  tokens_db_path: 'tmp/mcp_tokens.sqlite3',
}

let previewTokens: McpTokenInfo[] = [
  {
    id: 1,
    name: 'soc-bridge',
    token: 'mcp_soc_bridge_preview_6ffcb2',
    created_at: nowSeconds() - 86_400,
    expires_at: nowSeconds() + 86_400 * 6,
  },
  {
    id: 2,
    name: 'asset-hunter',
    token: 'mcp_asset_hunter_preview_998ab1',
    created_at: nowSeconds() - 60_000,
    expires_at: nowSeconds() + 86_400 * 29,
  },
]

let previewHiAgents: HiAgentEntry[] = [
  {
    name: 'CVE Hunter',
    url: 'https://hi-agent.example.com/mcp/cve',
    description: '对漏洞情报源进行扩展聚合。',
    enabled: true,
  },
  {
    name: 'Playbook Runner',
    url: 'https://hi-agent.example.com/mcp/playbook',
    description: '负责剧本执行和外部自动化。',
    enabled: false,
  },
]

let previewChatSessions: ChatSession[] = [
  {
    session_id: 'soc-brief-001',
    preview: '评估 CVE 对当前资产面的影响',
    created_at: nowSeconds() - 7_200,
    updated_at: nowSeconds() - 1_200,
  },
  {
    session_id: 'incident-bridge-002',
    preview: '生成对外暴露面排查计划',
    created_at: nowSeconds() - 14_400,
    updated_at: nowSeconds() - 4_800,
  },
]

const previewMessagesBySession: Record<string, WorkspaceMessage[]> = {
  'soc-brief-001': [
    {
      role: 'assistant',
      content:
        '你好，我已经接入当前中台的知识、Trace 和 MCP 配置。请直接描述需要研判的目标。',
      final: true,
    },
    {
      role: 'user',
      content: '请评估近期 CVE 对 Nginx 暴露面的影响。',
      final: true,
    },
    {
      role: 'assistant',
      content:
        '### 初步判断\n\n- 先按 Nginx 指纹筛出公网入口。\n- 关联最近 7 天的 CVE 线索与已命中文档。\n- 对高危入口追加 URL 抓取和剧本预案。',
      final: true,
    },
  ],
  'incident-bridge-002': [
    {
      role: 'assistant',
      content:
        '我可以先从资产画像、知识库和运行链路里抽取上下文，再输出一份排查计划。',
      final: true,
    },
  ],
}

const previewCves: CveResult[] = [
  {
    id: 1,
    cve_id: 'CVE-2026-10001',
    github_url: 'https://github.com/example/security-advisory-10001',
    description: 'Nginx 反向代理请求头处理缺陷，可能导致越权转发。',
    source: 'NVD',
    create_time: '2026-06-27',
  },
  {
    id: 2,
    cve_id: 'CVE-2026-13017',
    github_url: 'https://github.com/example/security-advisory-13017',
    description: 'Spring 组件在特定序列化链下存在高危利用路径。',
    source: 'GitHub',
    create_time: '2026-06-26',
  },
  {
    id: 3,
    cve_id: 'CVE-2026-14402',
    github_url: 'https://github.com/example/security-advisory-14402',
    description: '公开 PoC 指向管理端口暴露与未授权访问风险。',
    source: 'ExploitDB',
    create_time: '2026-06-24',
  },
]

const previewAssets: AssetResult[] = [
  {
    site: 'https://edge.agno.local',
    hostname: 'edge-gateway',
    ip: '10.10.4.18',
    title: 'Agno Edge Gateway',
    status: 200,
    http_server: 'nginx/1.25.5',
    finger: ['Nginx', 'Vue', 'Prometheus'],
    tag: ['公网', '核心'],
    port_info: [80, 443, 9100],
    os_info: ['Ubuntu 22.04'],
    ip_type: '公网',
    domain: ['edge.agno.local'],
  },
  {
    site: 'https://soc.agno.local',
    hostname: 'soc-portal',
    ip: '10.10.8.21',
    title: 'SOC Portal',
    status: 302,
    http_server: 'openresty',
    finger: ['React', 'OpenResty', 'S3'],
    tag: ['办公', '跳板'],
    port_info: [443, 8443],
    os_info: ['Debian 12'],
    ip_type: '内网',
    domain: ['soc.agno.local'],
  },
  {
    site: 'https://kb.agno.local',
    hostname: 'knowledge-console',
    ip: '10.10.9.16',
    title: 'Knowledge Console',
    status: 200,
    http_server: 'uvicorn',
    finger: ['Python', 'PostgreSQL', 'RAG'],
    tag: ['知识库'],
    port_info: [443, 5432],
    os_info: ['Ubuntu 24.04'],
    ip_type: '内网',
    domain: ['kb.agno.local'],
  },
]

const previewTraces: TraceItem[] = [
  {
    trace_id: 'trace-edge-proxy-triage',
    name: 'Edge proxy exposure triage',
    status: 'OK',
    duration_ms: 724,
    start_time: isoMinutesAgo(18),
    end_time: isoMinutesAgo(17),
    total_spans: 6,
    error_count: 0,
    run_id: 'run-edge-001',
    session_id: 'soc-brief-001',
    agent_id: 'threat-hunter',
  },
  {
    trace_id: 'trace-rag-context-merge',
    name: 'RAG evidence stitching',
    status: 'OK',
    duration_ms: 981,
    start_time: isoMinutesAgo(44),
    end_time: isoMinutesAgo(43),
    total_spans: 9,
    error_count: 0,
    run_id: 'run-rag-002',
    session_id: 'soc-brief-001',
    agent_id: 'knowledge-watch',
  },
  {
    trace_id: 'trace-mcp-route-audit',
    name: 'MCP route access audit',
    status: 'ERROR',
    duration_ms: 1418,
    start_time: isoMinutesAgo(72),
    end_time: isoMinutesAgo(70),
    total_spans: 11,
    error_count: 2,
    run_id: 'run-mcp-003',
    session_id: 'incident-bridge-002',
    agent_id: 'control-plane',
  },
  {
    trace_id: 'trace-asset-surface-review',
    name: 'Asset surface review',
    status: 'OK',
    duration_ms: 612,
    start_time: isoMinutesAgo(95),
    end_time: isoMinutesAgo(94),
    total_spans: 5,
    error_count: 0,
    run_id: 'run-asset-004',
    session_id: 'incident-bridge-002',
    agent_id: 'asset-radar',
  },
]

const previewTraceDetails: Partial<Record<string, TraceDetailResponse>> = {
  'trace-edge-proxy-triage': {
    trace: previewTraces[0],
    spans: [
      {
        span_id: 'span-edge-01',
        trace_id: 'trace-edge-proxy-triage',
        name: 'Ingress normalization',
        status_code: 'OK',
        duration_ms: 164,
        start_time: previewTraces[0].start_time,
        end_time: previewTraces[0].start_time,
        kind: 'server',
        attributes: { endpoint: '/ingress', asset_scope: 'edge' },
      },
      {
        span_id: 'span-edge-02',
        trace_id: 'trace-edge-proxy-triage',
        parent_span_id: 'span-edge-01',
        name: 'Fingerprint asset',
        status_code: 'OK',
        duration_ms: 228,
        start_time: previewTraces[0].start_time,
        end_time: previewTraces[0].start_time,
        kind: 'tool',
        attributes: { matcher: 'nginx', hits: 3 },
      },
      {
        span_id: 'span-edge-03',
        trace_id: 'trace-edge-proxy-triage',
        parent_span_id: 'span-edge-02',
        name: 'Playbook recommendation',
        status_code: 'OK',
        duration_ms: 332,
        start_time: previewTraces[0].start_time,
        end_time: previewTraces[0].end_time,
        kind: 'llm',
        attributes: { model: 'gpt-4.1', confidence: 0.91 },
      },
    ],
    tree: [],
  },
  'trace-rag-context-merge': {
    trace: previewTraces[1],
    spans: [
      {
        span_id: 'span-rag-01',
        trace_id: 'trace-rag-context-merge',
        name: 'Knowledge retrieval',
        status_code: 'OK',
        duration_ms: 352,
        start_time: previewTraces[1].start_time,
        end_time: previewTraces[1].start_time,
        kind: 'retrieval',
        attributes: { top_k: 5, chunks: 12 },
      },
      {
        span_id: 'span-rag-02',
        trace_id: 'trace-rag-context-merge',
        name: 'Context ranking',
        status_code: 'OK',
        duration_ms: 221,
        start_time: previewTraces[1].start_time,
        end_time: previewTraces[1].start_time,
        kind: 'reranker',
        attributes: { rerank_enabled: true },
      },
      {
        span_id: 'span-rag-03',
        trace_id: 'trace-rag-context-merge',
        name: 'Answer drafting',
        status_code: 'OK',
        duration_ms: 408,
        start_time: previewTraces[1].start_time,
        end_time: previewTraces[1].end_time,
        kind: 'llm',
        attributes: { model: 'qwen-plus' },
      },
    ],
    tree: [],
  },
  'trace-mcp-route-audit': {
    trace: previewTraces[2],
    spans: [
      {
        span_id: 'span-mcp-01',
        trace_id: 'trace-mcp-route-audit',
        name: 'Route inventory',
        status_code: 'OK',
        duration_ms: 240,
        start_time: previewTraces[2].start_time,
        end_time: previewTraces[2].start_time,
        kind: 'tool',
        attributes: { service_count: 3 },
      },
      {
        span_id: 'span-mcp-02',
        trace_id: 'trace-mcp-route-audit',
        parent_span_id: 'span-mcp-01',
        name: 'Permission validation',
        status_code: 'ERROR',
        status_message: 'Playbook route missing allow-list entry',
        duration_ms: 518,
        start_time: previewTraces[2].start_time,
        end_time: previewTraces[2].start_time,
        kind: 'guard',
        attributes: { failed_service: 'playbook' },
      },
      {
        span_id: 'span-mcp-03',
        trace_id: 'trace-mcp-route-audit',
        parent_span_id: 'span-mcp-02',
        name: 'Rollback suggestion',
        status_code: 'ERROR',
        duration_ms: 660,
        start_time: previewTraces[2].start_time,
        end_time: previewTraces[2].end_time,
        kind: 'llm',
        attributes: { model: 'gpt-4.1-mini' },
      },
    ],
    tree: [],
  },
  'trace-asset-surface-review': {
    trace: previewTraces[3],
    spans: [
      {
        span_id: 'span-asset-01',
        trace_id: 'trace-asset-surface-review',
        name: 'Asset lookup',
        status_code: 'OK',
        duration_ms: 204,
        start_time: previewTraces[3].start_time,
        end_time: previewTraces[3].start_time,
        kind: 'search',
        attributes: { assets: 3 },
      },
      {
        span_id: 'span-asset-02',
        trace_id: 'trace-asset-surface-review',
        name: 'Exposure scoring',
        status_code: 'OK',
        duration_ms: 408,
        start_time: previewTraces[3].start_time,
        end_time: previewTraces[3].end_time,
        kind: 'analysis',
        attributes: { score: 82 },
      },
    ],
    tree: [],
  },
}

for (const detail of Object.values(previewTraceDetails)) {
  if (detail) {
    detail.tree = buildSpanTree(detail.spans)
  }
}

function buildSpanTree(spans: SpanItem[]) {
  const nodes = new Map<string, SpanTreeNode>()
  const roots: SpanTreeNode[] = []

  for (const span of spans) {
    nodes.set(span.span_id, { span, children: [] })
  }

  for (const span of spans) {
    const node = nodes.get(span.span_id)
    if (!node) continue
    if (span.parent_span_id && nodes.has(span.parent_span_id)) {
      nodes.get(span.parent_span_id)?.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

function updateKnowledgeStatus() {
  previewKnowledgeStatus = {
    ...previewKnowledgeStatus,
    documents: previewKnowledgeDocuments.length,
    chunks: previewKnowledgeDocuments.reduce(
      (total, item) => total + item.chunks,
      0,
    ),
  }
}

export async function loadSettingsBundle() {
  if (!(await isBackendOnline())) {
    return clone(previewModels)
  }

  const [settings, models] = await Promise.all([
    requestJson<{ settings: Record<string, string> }>('/api/settings'),
    requestJson<{ active_model_id: string; models: ModelConfig[] }>(
      '/api/models',
    ),
  ])

  return {
    settings: settings.settings,
    active_model_id: models.active_model_id,
    models: models.models,
  } satisfies SettingsBundle
}

export async function saveSettingsBundle(payload: SettingsBundle) {
  if (!(await isBackendOnline())) {
    previewModels = clone(payload)
    return clone(previewModels)
  }

  const [settings, models] = await Promise.all([
    requestJson<{ settings: Record<string, string> }>(
      '/api/settings',
      {
        method: 'PUT',
        body: JSON.stringify({ settings: payload.settings }),
      },
      '保存运行时配置失败',
    ),
    requestJson<{ active_model_id: string; models: ModelConfig[] }>(
      '/api/models',
      {
        method: 'PUT',
        body: JSON.stringify({
          active_model_id: payload.active_model_id,
          models: payload.models,
        }),
      },
      '保存模型配置失败',
    ),
  ])

  return {
    settings: settings.settings,
    active_model_id: models.active_model_id,
    models: models.models,
  } satisfies SettingsBundle
}

export async function loadSkills() {
  if (!(await isBackendOnline())) {
    return clone(previewSkills)
  }

  const response = await requestJson<{ skills: SkillInfo[] }>(
    '/api/skills',
    {},
    '获取 Skills 列表失败',
  )
  return response.skills
}

export async function setSkillEnabled(name: string, enabled: boolean) {
  if (!(await isBackendOnline())) {
    previewSkills = previewSkills.map((skill) =>
      skill.name === name ? { ...skill, enabled } : skill,
    )
    return
  }

  await requestJson(
    `/api/skills/${encodeURIComponent(name)}/toggle`,
    {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    },
    '切换 Skill 状态失败',
  )
}

export async function loadKnowledgeBundle() {
  if (!(await isBackendOnline())) {
    return {
      status: clone(previewKnowledgeStatus),
      documents: clone(previewKnowledgeDocuments),
    } satisfies KnowledgeBundle
  }

  return await requestJson<KnowledgeBundle>(
    '/api/knowledge',
    {},
    '加载知识库失败',
  )
}

export async function addTextKnowledgeDocument(payload: {
  title: string
  source: string
  content: string
}) {
  if (!(await isBackendOnline())) {
    const next: KnowledgeDocument = {
      id: `doc-${Date.now()}`,
      title: payload.title,
      source: payload.source,
      chunks: Math.max(1, Math.ceil(payload.content.length / 480)),
      created_at: new Date().toISOString(),
      metadata: { mode: 'preview' },
    }
    previewKnowledgeDocuments = [next, ...previewKnowledgeDocuments]
    updateKnowledgeStatus()
    return next
  }

  return await requestJson<KnowledgeDocument>(
    '/api/knowledge/documents/text',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    '写入知识文档失败',
  )
}

export async function addPathKnowledgeDocument(payload: {
  path: string
  title?: string
}) {
  if (!(await isBackendOnline())) {
    const next: KnowledgeDocument = {
      id: `doc-path-${Date.now()}`,
      title: payload.title || payload.path.split('/').pop() || '未命名路径文档',
      source: 'path',
      chunks: 12,
      created_at: new Date().toISOString(),
      metadata: { path: payload.path },
    }
    previewKnowledgeDocuments = [next, ...previewKnowledgeDocuments]
    updateKnowledgeStatus()
    return next
  }

  return await requestJson<KnowledgeDocument>(
    '/api/knowledge/documents/file',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    '导入文件失败',
  )
}

export async function deleteKnowledgeDocument(documentId: string) {
  if (!(await isBackendOnline())) {
    previewKnowledgeDocuments = previewKnowledgeDocuments.filter(
      (doc) => doc.id !== documentId,
    )
    updateKnowledgeStatus()
    return
  }

  await requestJson(
    `/api/knowledge/documents/${encodeURIComponent(documentId)}`,
    { method: 'DELETE' },
    '删除知识文档失败',
  )
}

export async function clearKnowledgeDocuments() {
  if (!(await isBackendOnline())) {
    previewKnowledgeDocuments = []
    updateKnowledgeStatus()
    return
  }

  await requestJson('/api/knowledge', { method: 'DELETE' }, '清空知识库失败')
}

export async function searchKnowledge(
  query: string,
  limit: number,
): Promise<KnowledgeSearchResult[]> {
  if (!(await isBackendOnline())) {
    return previewKnowledgeDocuments
      .filter((document) =>
        `${document.title} ${document.source} ${JSON.stringify(document.metadata ?? {})}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      )
      .slice(0, limit)
      .map((document, index) => ({
        content: `${document.title} 的命中片段，适合用于检索验证与 Chunk 回贴展示。`,
        score: 0.97 - index * 0.08,
        distance: 0.03 + index * 0.04,
        doc_id: document.id,
        title: document.title,
        source: document.source,
        chunk_index: index,
        metadata: document.metadata,
      }))
  }

  const response = await requestJson<{ results: KnowledgeSearchResult[] }>(
    '/api/knowledge/search',
    {
      method: 'POST',
      body: JSON.stringify({ query, limit }),
    },
    '检索知识库失败',
  )
  return response.results
}

export async function loadMcpBundle(): Promise<McpBundle> {
  if (!(await isBackendOnline())) {
    return {
      config: clone(previewMcpConfig),
      tokens: clone(previewTokens),
      hiAgents: clone(previewHiAgents),
    }
  }

  const [config, tokens, hiAgents] = await Promise.all([
    requestJson<McpConfig>('/api/mcp/config', {}, '获取 MCP 配置失败'),
    requestJson<McpTokenInfo[]>('/api/mcp/tokens', {}, '获取 MCP Token 失败'),
    requestJson<HiAgentEntry[]>('/api/mcp/hiagent', {}, '获取 Hi-Agent 失败'),
  ])

  return { config, tokens, hiAgents }
}

export async function setMcpServiceEnabled(id: McpServiceId, enabled: boolean) {
  if (!(await isBackendOnline())) {
    previewMcpConfig = {
      ...previewMcpConfig,
      services: {
        ...previewMcpConfig.services,
        [id]: enabled,
      },
    }
    return
  }

  await requestJson(
    '/api/mcp/config',
    {
      method: 'POST',
      body: JSON.stringify({ id, enabled }),
    },
    '更新 MCP 配置失败',
  )
}

export async function createMcpToken(name: string, expiresIn: number) {
  if (!(await isBackendOnline())) {
    const token = `mcp_${name.replace(/\s+/g, '_').toLowerCase()}_${Date.now().toString(36)}`
    const next: McpTokenInfo = {
      id: Date.now(),
      name,
      token,
      created_at: nowSeconds(),
      expires_at: expiresIn
        ? nowSeconds() + expiresIn
        : nowSeconds() + 86_400 * 365,
    }
    previewTokens = [next, ...previewTokens]
    return token
  }

  const response = await requestJson<{ token: string }>(
    '/api/mcp/tokens/issue',
    {
      method: 'POST',
      body: JSON.stringify({ name, expires_in: expiresIn }),
    },
    '生成 Token 失败',
  )
  return response.token
}

export async function deleteMcpToken(id: number) {
  if (!(await isBackendOnline())) {
    previewTokens = previewTokens.filter((token) => token.id !== id)
    return
  }

  await requestJson(
    '/api/mcp/tokens/delete',
    {
      method: 'POST',
      body: JSON.stringify({ id }),
    },
    '删除 Token 失败',
  )
}

export async function addHiAgent(entry: HiAgentEntry) {
  if (!(await isBackendOnline())) {
    previewHiAgents = [entry, ...previewHiAgents]
    return
  }

  await requestJson(
    '/api/mcp/hiagent/add',
    {
      method: 'POST',
      body: JSON.stringify(entry),
    },
    '注册 Hi-Agent 失败',
  )
}

export async function setHiAgentEnabled(url: string, enabled: boolean) {
  if (!(await isBackendOnline())) {
    previewHiAgents = previewHiAgents.map((item) =>
      item.url === url ? { ...item, enabled } : item,
    )
    return
  }

  await requestJson(
    '/api/mcp/hiagent/update',
    {
      method: 'POST',
      body: JSON.stringify({ url, enabled }),
    },
    '更新 Hi-Agent 失败',
  )
}

export async function deleteHiAgent(url: string) {
  if (!(await isBackendOnline())) {
    previewHiAgents = previewHiAgents.filter((item) => item.url !== url)
    return
  }

  await requestJson(
    '/api/mcp/hiagent/delete',
    {
      method: 'POST',
      body: JSON.stringify({ url }),
    },
    '删除 Hi-Agent 失败',
  )
}

export async function loadChatSessions() {
  if (!(await isBackendOnline())) {
    return clone(previewChatSessions).sort(
      (a, b) => b.updated_at - a.updated_at,
    )
  }

  return await requestJson<ChatSession[]>(
    '/api/chat/sessions',
    {},
    '获取会话列表失败',
  )
}

export async function loadChatHistory(sessionId: string) {
  if (!(await isBackendOnline())) {
    return clone(
      previewMessagesBySession[sessionId] ?? [
        {
          role: 'assistant',
          content: '该会话目前没有可用消息。',
          final: true,
        },
      ],
    )
  }

  return await requestJson<WorkspaceMessage[]>(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}`,
    {},
    '获取会话记录失败',
  )
}

export async function deleteChatSession(sessionId: string) {
  if (!(await isBackendOnline())) {
    previewChatSessions = previewChatSessions.filter(
      (session) => session.session_id !== sessionId,
    )
    delete previewMessagesBySession[sessionId]
    return
  }

  await fetch(
    `${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'DELETE',
    },
  )
}

function buildPreviewResponse(message: string, modelName: string) {
  return [
    `### ${modelName} 响应\n\n`,
    `- 已接收目标：${message}\n`,
    '- 先对暴露面、知识命中和最近 Trace 进行并列比对。\n',
    '- 如果需要执行动作，优先走 MCP allow-list 与 Skill 开关校验。\n',
    '\n建议下一步：\n',
    '1. 进入资产画像确认受影响入口。\n',
    '2. 打开 RAG 知识库验证历史处置文档。\n',
    '3. 在运行观测中核对相关 session 与 run。\n',
  ]
}

export async function streamChatMessage(options: {
  sessionId: string
  message: string
  modelId: string | null
  onChunk: (chunk: string) => void
}) {
  const modelName =
    previewModels.models.find((model) => model.id === options.modelId)?.name ??
    'SecOps Analyst'

  if (!(await isBackendOnline())) {
    const chunks = buildPreviewResponse(options.message, modelName)
    for (const chunk of chunks) {
      await new Promise((resolve) => window.setTimeout(resolve, 90))
      options.onChunk(chunk)
    }

    const history = previewMessagesBySession[options.sessionId] ?? [
      {
        role: 'assistant' as const,
        content:
          '你好，我已经接入当前中台的知识、Trace 和 MCP 配置。请直接描述需要研判的目标。',
        final: true,
      },
    ]
    const answer = chunks.join('')
    previewMessagesBySession[options.sessionId] = [
      ...history,
      { role: 'user', content: options.message, final: true },
      { role: 'assistant', content: answer, final: true },
    ]

    const existing = previewChatSessions.find(
      (session) => session.session_id === options.sessionId,
    )
    if (existing) {
      existing.preview = options.message
      existing.updated_at = nowSeconds()
    } else {
      previewChatSessions = [
        {
          session_id: options.sessionId,
          preview: options.message,
          created_at: nowSeconds(),
          updated_at: nowSeconds(),
        },
        ...previewChatSessions,
      ]
    }
    return
  }

  const response = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      message: options.message,
      session_id: options.sessionId,
      model_id: options.modelId,
    }),
  })

  if (!response.ok || !response.body) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''

    for (const part of parts) {
      const lines = part.split('\n')
      const dataLines = lines
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))

      if (!dataLines.length) continue
      const data = dataLines.join('\n')
      if (data === '[DONE]') return
      options.onChunk(data)
    }
  }
}

export async function searchCves(options: {
  query: string
  source?: string
  page: number
  size: number
}) {
  if (!(await isBackendOnline())) {
    const matches = previewCves.filter((item) => {
      const query = options.query.toLowerCase()
      const haystack =
        `${item.cve_id} ${item.description} ${item.source}`.toLowerCase()
      return haystack.includes(query)
    })
    const filtered = options.source
      ? matches.filter((item) => item.source === options.source)
      : matches

    return {
      items: filtered.slice(
        (options.page - 1) * options.size,
        options.page * options.size,
      ),
      total: filtered.length,
    } satisfies CveSearchResponse
  }

  return await requestJson<CveSearchResponse>(
    '/api/cve/search',
    {
      method: 'POST',
      body: JSON.stringify({
        query: options.query,
        source: options.source || null,
        page: options.page,
        size: options.size,
      }),
    },
    'CVE 搜索失败',
  )
}

export async function refreshCveCatalog() {
  if (!(await isBackendOnline())) {
    return {
      status: 1,
      add_count: 3,
      del_count: 0,
      message: '本地情报数据已刷新。',
    }
  }

  return await requestJson<{
    status: number
    add_count?: number
    del_count?: number
    message?: string
  }>('/api/cve/update', { method: 'POST' }, '刷新 CVE 数据失败')
}

export async function searchAssets(options: {
  mode: 'fingerprint' | 'ip'
  query: string
  page: number
  size: number
}) {
  if (!(await isBackendOnline())) {
    const filtered = previewAssets.filter((item) => {
      const query = options.query.toLowerCase()
      if (options.mode === 'ip') {
        return [item.ip, ...item.domain, item.hostname].some((value) =>
          value.toLowerCase().includes(query),
        )
      }
      return [item.title, item.http_server, ...item.finger, ...item.tag].some(
        (value) => value.toLowerCase().includes(query),
      )
    })
    return {
      status: 1,
      items: filtered.slice(
        (options.page - 1) * options.size,
        options.page * options.size,
      ),
      total: filtered.length,
    } satisfies AssetSearchResponse
  }

  return await requestJson<AssetSearchResponse>(
    '/api/asset/search',
    {
      method: 'POST',
      body: JSON.stringify({
        page: options.page,
        size: options.size,
        fingerprint: options.mode === 'fingerprint' ? options.query : undefined,
        ip: options.mode === 'ip' ? options.query : undefined,
      }),
    },
    '资产搜索失败',
  )
}

export async function parseUrlToMarkdown(url: string) {
  if (!(await isBackendOnline())) {
    return {
      markdown: [
        `# ${url}`,
        '',
        '## 页面摘要',
        '这是本地生成的 Markdown，用于验证工作台里的 URL 解析流转。',
        '',
        '## 建议提取字段',
        '- 标题与站点信息',
        '- 关键 IOC 与链接',
        '- 可沉淀到知识库的原始文本',
      ].join('\n'),
    }
  }

  return await requestJson<{ markdown?: string | string[] }>(
    '/api/url2md/parse',
    {
      method: 'POST',
      body: JSON.stringify({ url }),
    },
    'URL 解析失败',
  )
}

export async function listTraces(filters: {
  page?: number
  limit?: number
  status?: string
  session_id?: string
  start_time?: string
  end_time?: string
}) {
  if (!(await isBackendOnline())) {
    const page = filters.page ?? 1
    const limit = filters.limit ?? 20
    let items = previewTraces
    if (filters.status) {
      items = items.filter((trace) => trace.status === filters.status)
    }
    if (filters.session_id) {
      items = items.filter((trace) =>
        (trace.session_id ?? '').includes(filters.session_id ?? ''),
      )
    }
    if (filters.start_time) {
      const startTime = Date.parse(filters.start_time)
      items = items.filter((trace) => Date.parse(trace.start_time) >= startTime)
    }
    if (filters.end_time) {
      const endTime = Date.parse(filters.end_time)
      items = items.filter((trace) => Date.parse(trace.start_time) <= endTime)
    }
    return {
      items: clone(items.slice((page - 1) * limit, page * limit)),
      total_count: items.length,
      page,
      limit,
    } satisfies TraceListResponse
  }

  const search = new URLSearchParams()
  if (filters.page) search.set('page', String(filters.page))
  if (filters.limit) search.set('limit', String(filters.limit))
  if (filters.status) search.set('status', filters.status)
  if (filters.session_id) search.set('session_id', filters.session_id)
  if (filters.start_time) search.set('start_time', filters.start_time)
  if (filters.end_time) search.set('end_time', filters.end_time)

  return await requestJson<TraceListResponse>(
    `/api/traces?${search.toString()}`,
    {},
    '加载 Trace 列表失败',
  )
}

export async function getTraceDetail(traceId: string) {
  if (!(await isBackendOnline())) {
    const detail = previewTraceDetails[traceId]
    if (!detail) {
      throw new Error('未找到对应 Trace')
    }
    return clone(detail)
  }

  return await requestJson<TraceDetailResponse>(
    `/api/traces/${encodeURIComponent(traceId)}`,
    {},
    '加载 Trace 详情失败',
  )
}

export function getPreviewWelcomeMessage() {
  return '你好，我已经接入当前中台的知识、Trace 和 MCP 配置。请直接描述需要研判的目标。'
}

export function createPreviewSession() {
  return createSessionId()
}
