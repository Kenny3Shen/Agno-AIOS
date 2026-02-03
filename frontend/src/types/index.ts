// LLM 聊天相关类型
export interface Message {
  role: "user" | "assistant"
  content: string
  final?: boolean
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
