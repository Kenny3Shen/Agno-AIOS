// LLM 聊天相关类型
export interface Message {
  role: "user" | "assistant"
  content: string
  final?: boolean
  run_id?: string | null
  agent_id?: string | null
  agent_name?: string | null
  session_id?: string | null
  workflow_id?: string | null
  user_id?: string | null
  model?: string | null
  model_provider?: string | null
  metrics?: ChatRunMetrics | null
  tools?: unknown[] | null
  created_at?: number | string | null
  status?: string | null
  raw_run?: Record<string, unknown> | null
}

export interface ChatRunMetrics {
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  reasoning_tokens?: number | null
  cache_read_tokens?: number | null
  cache_write_tokens?: number | null
  cost?: number | null
  duration?: number | null
  time_to_first_token?: number | null
  details?: Record<string, unknown>
  additional_metrics?: Record<string, unknown>
}

// Skills 管理相关类型
export type ResourceVisibility = "private" | "public"

export interface SkillInfo {
  name: string
  description: string
  enabled: boolean
  has_scripts: boolean
  scripts: string[]
  skill_markdown: string
  visibility: ResourceVisibility
  owner_user_id: string
  can_manage: boolean
}

export interface SkillListResponse {
  skills: SkillInfo[]
}

export interface SkillToggleResponse {
  name: string
  enabled: boolean
}

export interface UploadResultResponse {
  success: boolean
  name: string
  description?: string
  path?: string
  kind?: string
  visibility?: ResourceVisibility
  restart_required?: boolean
}

// MCP 管理相关类型
export type McpServiceId = "playbook" | "basic"

export interface McpServiceStatusResponse {
  services: Record<McpServiceId, boolean>
  mcp_servers?: McpServerInfo[]
  control_mode?: string
  fastmcp?: string
  mcp_url?: string
  config_path?: string
  tokens_db_path?: string
}

export interface McpServerInfo {
  name: string
  description: string
  kind: string
  enabled: boolean
  visibility: ResourceVisibility
  owner_user_id: string
  can_manage: boolean
  manifest: Record<string, unknown>
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

export interface ChatSession {
  session_id: string
  user_id?: string | null
  preview: string
  created_at: number
  updated_at: number
  archived?: boolean
  archived_at?: string | null
  runs?: ChatSessionRun[]
}

export interface ChatSessionRun {
  run_id?: string | null
  session_id?: string | null
  user_id?: string | null
  agent_id?: string | null
  agent_name?: string | null
  team_id?: string | null
  workflow_id?: string | null
  model?: string | null
  model_provider?: string | null
  status?: string | null
  input?: unknown
  content?: unknown
  metrics?: ChatRunMetrics | null
  tools?: unknown[] | null
  created_at?: number | string | null
  updated_at?: number | string | null
  [key: string]: unknown
}

export interface WorkbenchMetric {
  label: string
  value: string | number
  hint?: string
  tone?: "red" | "blue" | "green" | "yellow" | string
}

export interface WorkbenchRecord {
  id: string
  title: string
  subtitle?: string
  status: string
  meta?: Record<string, unknown>
  updated_at?: string
}

export interface ApprovalRecord {
  id: string
  run_id?: string | null
  session_id?: string | null
  status: string
  source_type?: string | null
  approval_type?: string | null
  pause_type?: string | null
  tool_name?: string | null
  tool_args?: Record<string, unknown>
  expires_at?: number | string | null
  agent_id?: string | null
  team_id?: string | null
  workflow_id?: string | null
  user_id?: string | null
  schedule_id?: string | null
  schedule_run_id?: string | null
  source_name?: string | null
  requirements?: Record<string, unknown>[]
  context?: Record<string, unknown>
  resolution_data?: Record<string, unknown> | null
  resolved_by?: string | null
  resolved_at?: number | string | null
  created_at?: number | string | null
  updated_at?: number | string | null
  run_status?: string | null
}

export interface ApprovalFilters {
  status?: string | null
  source_type?: string | null
  approval_type?: string | null
  pause_type?: string | null
  agent_id?: string | null
  team_id?: string | null
  workflow_id?: string | null
  user_id?: string | null
  schedule_id?: string | null
  run_id?: string | null
  page: number
  limit: number
}

export interface ApprovalMeta {
  page: number
  limit: number
  total: number
  pending: number
}

export interface ApprovalListResponse {
  module: "approvals"
  title: string
  description: string
  status: string
  metrics: WorkbenchMetric[]
  records: WorkbenchRecord[]
  generated_at: string
  approvals: ApprovalRecord[]
  approval_filters: ApprovalFilters
  approval_meta: ApprovalMeta
}

export interface ApprovalListParams {
  status?: string
  source_type?: string
  approval_type?: string
  pause_type?: string
  agent_id?: string
  team_id?: string
  workflow_id?: string
  user_id?: string
  schedule_id?: string
  run_id?: string
  page?: number
  limit?: number
}

export interface ApprovalResolveRequest {
  status: "approved" | "rejected"
  resolution_data?: Record<string, unknown> | null
}

export interface MemoryItem {
  id: string
  memory: string
  topics: string[]
  input: string
  user_id: string
  agent_id: string
  team_id: string
  feedback: string
  created_at: string
  updated_at: string
  status: string
}

export interface MemoryUserSummary {
  user_id: string
  total_memories: number
  last_memory_updated_at: string
  status: "healthy" | "review" | "risk" | string
}

export interface MemoryFilters {
  user_id: string
  topic: string
  search: string
  page: number
  limit: number
  total: number
}

export interface MemoryThresholds {
  optimization_review: number
  abnormal_growth: number
}

export interface MemoryMode {
  type: "automatic" | string
  update_memory_on_run: boolean
  enable_agentic_memory: boolean
  enable_session_summaries: boolean
  readonly: boolean
}

export interface MemoryPayloadResponse {
  module: "memory"
  title: string
  description: string
  status: string
  metrics: WorkbenchMetric[]
  records: WorkbenchRecord[]
  generated_at: string
  memories: MemoryItem[]
  memory_users: MemoryUserSummary[]
  memory_topics: string[]
  memory_filters: MemoryFilters
  memory_thresholds: MemoryThresholds
  memory_mode: MemoryMode
}

export interface MemoryQueryParams {
  user_id?: string
  topic?: string
  search?: string
  page?: number
  limit?: number
}

export interface MemoryDeleteResponse {
  memory_id: string
  user_id: string
  deleted: boolean
}

export interface MemoryUpdateRequest {
  user_id?: string
  memory: string
  topics: string[]
}

export interface MemoryUpdateResponse {
  memory_id: string
  user_id: string
  memory: string
  topics: string[]
  input: string
  agent_id: string
  team_id: string
  feedback: string
  created_at: string
  updated_at: string
}

export type ScheduleTargetType = "agent" | "team" | "workflow"

export interface SchedulerSchedule {
  id: string
  name: string
  description?: string | null
  method: string
  endpoint: string
  target_type: ScheduleTargetType | ""
  target_id: string
  payload: Record<string, unknown>
  cron_expr: string
  timezone: string
  timeout_seconds: number
  max_retries: number
  retry_delay_seconds: number
  enabled: boolean
  next_run_at?: number | null
  next_run_at_iso?: string
  created_at?: number | null
  created_at_iso?: string
  updated_at?: number | null
  updated_at_iso?: string
}

export interface SchedulerPayloadResponse {
  module: "scheduler"
  title: string
  description: string
  status: string
  metrics: WorkbenchMetric[]
  records: WorkbenchRecord[]
  generated_at: string
  schedules: SchedulerSchedule[]
}

export interface SchedulerRun {
  id: string
  schedule_id: string
  attempt: number
  triggered_at?: number | null
  triggered_at_iso?: string
  completed_at?: number | null
  completed_at_iso?: string
  status: string
  status_code?: number | null
  run_id?: string | null
  session_id?: string | null
  error?: string | null
  input?: Record<string, unknown> | null
  output?: Record<string, unknown> | null
  requirements?: Record<string, unknown>[] | null
  created_at?: number | null
  created_at_iso?: string
}

export interface ScheduleCreateRequest {
  name: string
  target_type: ScheduleTargetType
  target_id: string
  cron_expr: string
  description?: string
  payload?: Record<string, unknown>
  timezone?: string
  timeout_seconds?: number
  max_retries?: number
  retry_delay_seconds?: number
  enabled?: boolean
}

export type ScheduleUpdateRequest = Partial<ScheduleCreateRequest>

export interface ScheduleCreateResponse extends SchedulerSchedule {}

export interface ScheduleRunsResponse {
  items: SchedulerRun[]
  page: number
  limit: number
}

// Agent Eval 相关类型
export type AgentEvalType = "accuracy" | "agent_as_judge" | "reliability" | "performance"

export interface AgentEvalSuite {
  id: string
  name: string
  description: string
  target_agent_id: string
  enabled: boolean
  tags: string[]
  created_by: string
  created_at?: string | number | null
  updated_at?: string | number | null
}

export interface AgentEvalCase {
  id: string
  suite_id: string
  name: string
  description: string
  target_agent_id: string
  input: string
  expected_output: string
  criteria: string
  threshold: number
  eval_types: AgentEvalType[]
  expected_tool_calls: string[]
  expected_tool_call_arguments: Record<string, unknown>
  allow_additional_tool_calls: boolean
  performance_config: Record<string, unknown>
  metadata: Record<string, unknown>
  enabled: boolean
  latest_status?: string | null
  created_at?: string | number | null
  updated_at?: string | number | null
}

export interface AgentEvalSuiteRun {
  id: string
  suite_id: string
  status: string
  started_by: string
  error_summary: string
  summary: Record<string, unknown>
  started_at?: string | number | null
  completed_at?: string | number | null
}

export interface AgentEvalCaseRun {
  id: string
  suite_run_id: string
  case_id: string
  status: string
  agent_run_id: string
  session_id: string
  trace_id: string
  agno_eval_run_ids: string[]
  error_type: string
  error_summary: string
  replay_of_case_run_id: string
  started_at?: string | number | null
  completed_at?: string | number | null
}

export interface AgentEvalAgnoRun {
  id: string
  run_id: string
  name: string
  eval_type: AgentEvalType | string
  case_run_id?: string | null
  case_id?: string | null
  suite_run_id?: string | null
  agent_id?: string | null
  team_id?: string | null
  workflow_id?: string | null
  model_id?: string | null
  model_provider?: string | null
  passed?: boolean | null
  score?: number | null
  data: Record<string, unknown>
  eval_input: Record<string, unknown>
  created_at?: string | number | null
  updated_at?: string | number | null
}

export interface AgentEvalTrendResponse {
  by_date: Array<{ date: string; total: number; passed: number; failed: number }>
  by_eval_type: Array<{ eval_type: string; total: number; passed: number; failed: number }>
  by_status: { passed: number; failed: number; unknown: number }
}

export type AgentEvalFailureResponse = AgentEvalAgnoRun[]

export interface AgentEvalSuiteCreateRequest {
  name: string
  description?: string
  target_agent_id?: string
  enabled?: boolean
  tags?: string[]
}

export interface AgentEvalCaseCreateRequest {
  suite_id: string
  name: string
  description?: string
  target_agent_id?: string
  input: string
  expected_output?: string
  criteria?: string
  threshold?: number
  eval_types?: AgentEvalType[]
  expected_tool_calls?: string[]
  expected_tool_call_arguments?: Record<string, unknown>
  allow_additional_tool_calls?: boolean
  performance_config?: Record<string, unknown>
  metadata?: Record<string, unknown>
  enabled?: boolean
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

// URL2MD 相关类型
export interface Url2MdParseResponse {
  markdown?: string | string[]
}

export type MessageType = {
  type: 'success' | 'warning' | 'info' | 'error'
  title: string
  description?: string
}

// 认证相关类型
export interface AuthTokenResponse {
  access_token: string
  token_type: string
}

export interface AuthUser {
  id: string
  email: string
  role?: "admin" | "user" | "guest"
  scopes?: string[]
  is_active: boolean
  is_superuser?: boolean
  is_verified?: boolean
}

export interface AuthCredentials {
  email: string
  password: string
}

export type OAuthProvider = 'github' | 'google' | 'microsoft' | string

export interface OAuthProvidersResponse {
  providers: OAuthProvider[]
}

export interface OAuthAuthorizationResponse {
  authorization_url: string
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

export interface ModelConnectivityTestResponse {
  success: boolean
  latency_ms?: number | null
  message: string
  status_code?: number | null
}

// RAG 知识库相关类型
export interface KnowledgeStatus {
  collection: string
  storage?: string
  path?: string
  index_file?: string
  database?: string
  contents_db?: string
  postgres_schema?: string
  documents: number
  chunks: number
  embedding: string
  embedding_dimensions?: number | null
  rerank?: string
  device?: string
  rerank_enabled: boolean
  top_k?: number
  retrieval_candidates?: number
  rerank_candidate_multiplier?: number
  rerank_min_candidates?: number
  search_type?: "vector" | "keyword" | "hybrid" | string
  vector_score_weight?: number
  bm25_score_weight?: number
  prefix_match?: boolean
  content_language?: string
  chunk_size?: number
  chunk_overlap?: number
  code_chunk_size?: number
  semantic_threshold?: number
  rag_settings?: KnowledgeRagSettings
  supported_suffixes?: string[]
  chunk_profiles?: KnowledgeChunkProfile[]
  cold_start_note?: string
  torch_runtime_ok?: boolean
}

export interface KnowledgeRagSettings {
  embedding_model?: string
  embedding_dimensions?: number
  rerank_model?: string
  query_prompt?: string
  top_k?: number
  chunk_size?: number
  chunk_overlap?: number
  code_chunk_size?: number
  semantic_threshold?: number
  vector_score_weight?: number
  bm25_score_weight?: number
  content_language?: string
  prefix_match?: boolean
  rerank_enabled?: boolean
  rerank_candidate_multiplier?: number
  rerank_min_candidates?: number
  device?: string
  search_type?: "vector" | "keyword" | "hybrid" | string
}

export interface KnowledgeChunkProfile {
  label: string
  strategy: string
  reader: string
  suffixes: string[]
  description: string
}

export interface KnowledgeDocument {
  id: string
  title: string
  source: string
  chunks: number
  created_at: string
  status?: string
  status_message?: string
  type?: string | null
  size?: number | string | null
  visibility?: ResourceVisibility
  owner_user_id?: string
  can_manage?: boolean
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
  visibility?: ResourceVisibility
}

export interface KnowledgeFileRequest {
  path: string
  title?: string | null
  visibility?: ResourceVisibility
}

export interface KnowledgeSourceReplacementRequest {
  content: string
  file_name: string
  title?: string | null
  source?: string | null
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

export interface KnowledgeSearchResponse {
  results: KnowledgeSearchResult[]
}

export interface KnowledgeRagSettingsResponse {
  settings: KnowledgeRagSettings
  status: KnowledgeStatus
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
  parsed?: ParsedSpanDisplay | null
}

export interface ParsedSpanPayload {
  format: "empty" | "json" | "markdown" | "text" | string
  text: string
  data?: unknown
}

export interface ParsedSpanEvent {
  name: string
  message: string
  attributes?: Record<string, unknown>
}

export interface ParsedSpanDisplay {
  input: ParsedSpanPayload
  output: ParsedSpanPayload
  metadata: {
    model?: string | null
    provider?: string | null
    tool?: string | null
    operation?: string | null
    tokens?: {
      prompt?: number | null
      completion?: number | null
      total?: number | null
    }
  }
  events: ParsedSpanEvent[]
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
