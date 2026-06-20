// LLM 聊天相关类型
export interface Message {
  role: "user" | "assistant"
  content: string
  final?: boolean
}

// Skills 管理相关类型
export interface SkillInfo {
  name: string
  description: string
  enabled: boolean
  has_scripts: boolean
  scripts: string[]
}

export interface SkillListResponse {
  skills: SkillInfo[]
}

export interface SkillToggleResponse {
  name: string
  enabled: boolean
}

// MCP 管理相关类型
export type McpServiceId = "playbook" | "agent" | "basic"

export interface McpServiceStatusResponse {
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

export interface McpTokenIssueResponse {
  token: string
}

export interface HiAgentEntry {
  name: string
  url: string
  description: string
  enabled: boolean
}

export interface ChatSession {
  session_id: string
  preview: string
  created_at: number
  updated_at: number
}

// CVE 相关类型
export interface CveResult {
  id: number
  cve_id: string
  github_url: string
  description: string
  source: string
  create_time: string
}

export interface CveSearchParams {
  query: string
  source?: string | null
  page: number
  size: number
}

export interface CveSearchResponse {
  items: CveResult[]
  total: number
}

// 资产相关类型
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

export interface AssetSearchParams {
  fingerprint?: string
  ip?: string
  page: number
  size: number
}

export interface AssetSearchResponse {
  status: number
  items: AssetResult[]
  total: number
  message?: string
}

// URL2MD 相关类型
export interface Url2MdParseResponse {
  markdown?: string | string[]
}

export type MessageType = {
  type: 'success' | 'warning' | 'info' | 'error'
  title: string
  description?: string
}

// 更新响应类型
export interface UpdateResponse {
  status: number
  add_count?: number
  del_count?: number
  message?: string
}

// Settings 相关类型
export interface SettingsResponse {
  settings: Record<string, string>
}

export interface SettingsUpdate {
  settings: Record<string, string>
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

export interface ModelConfigResponse {
  active_model_id: string
  models: ModelConfig[]
}

// RAG 知识库相关类型
export interface KnowledgeStatus {
  collection: string
  storage?: string
  path?: string
  index_file?: string
  documents: number
  chunks: number
  embedding: string
  rerank?: string
  device?: string
  rerank_enabled?: boolean
  retrieval_candidates?: number
}

export interface KnowledgeDocument {
  id: string
  title: string
  source: string
  chunks: number
  created_at: string
  metadata?: Record<string, string>
}

export interface KnowledgeStatusResponse {
  status: KnowledgeStatus
  documents: KnowledgeDocument[]
}

export interface KnowledgeTextRequest {
  title: string
  content: string
  source?: string
  metadata?: Record<string, string>
}

export interface KnowledgeFileRequest {
  path: string
  title?: string | null
}

export interface KnowledgeSearchResult {
  content: string
  score: number
  distance: number
  doc_id: string
  title: string
  source: string
  chunk_index: number
}

export interface KnowledgeSearchResponse {
  results: KnowledgeSearchResult[]
}

// Tracing 相关类型（Agno Tracing）
export type TraceStatus = "OK" | "ERROR" | "UNSET" | string
export type SpanStatus = "OK" | "ERROR" | "UNSET" | string

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
  created_at?: string
}

export interface SpanItem {
  span_id: string
  trace_id: string
  parent_span_id?: string | null
  name: string
  status_code: SpanStatus
  status_message?: string | null
  duration_ms: number
  start_time: string
  end_time: string
  attributes?: Record<string, unknown> | null
  events?: unknown[] | null
  kind?: string | null
}

export interface SpanTreeNode {
  span: SpanItem
  children: SpanTreeNode[]
}

export interface TraceListResponse {
  items: TraceItem[]
  total_count: number
  page: number
  limit: number
}

export interface TraceDetailResponse {
  trace: TraceItem
  spans: SpanItem[]
  tree: SpanTreeNode[]
}
