/** Collect (安全情报) client: article library search, parse, crawl SSE. */
import { ApiError, apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { consumeSse } from '@/features/chat/utils'
import { normalizePaginatedList } from '@/shared/lib/pagination'

export interface CollectArticle {
  id: number
  url: string
  source_domain: string
  title: string
  markdown: string
  summary: string
  status: string
  error_message?: string
  /** CVE-YYYY-NNNN ids extracted from title/summary/body. */
  cve_ids?: string[]
  fetched_at?: string
  created_at?: string
  updated_at?: string
}

export interface CollectSource {
  domain: string
  has_rule: boolean
  has_articles: boolean
  ok_count?: number
  error_count?: number
  total_count?: number
}

export interface CollectLibraryStats {
  ok: number
  error: number
  total: number
}

export const parseUrl = (url: string) =>
  requestJson<{
    markdown?: string
    title?: string
    source_domain?: string
    id?: number
    url?: string
    summary?: string
    cve_ids?: string[]
  }>('/url2md/parse', jsonInit('POST', { url }))

export const searchArticles = async (payload: {
  query?: string
  source_domain?: string
  status?: 'ok' | 'error' | 'all'
  page?: number
  size?: number
}) => {
  const page = payload.page ?? 1
  const size = payload.size ?? 20
  const raw = await requestJson<unknown>(
    '/url2md/articles/search',
    jsonInit('POST', {
      query: payload.query ?? '',
      source_domain: payload.source_domain,
      status: payload.status ?? 'ok',
      page,
      size,
    }),
  )
  return normalizePaginatedList(raw, {
    page,
    limit: size,
    mapItem: (row) => {
      if (!row || typeof row !== 'object') return null
      return row as CollectArticle
    },
  })
}

export const listSources = async () => {
  const raw = await requestJson<unknown>('/url2md/sources')
  return normalizePaginatedList(raw, {
    mapItem: (row) => {
      if (!row || typeof row !== 'object') return null
      return row as CollectSource
    },
  })
}

export type CollectCrawlStats = {
  message?: string
  sources?: number
  discovered?: number
  skipped_existing?: number
  selected?: number
  fetched?: number
  saved?: number
  ok?: number
  error?: number
}

export type CollectCrawlProgress = {
  stage?: string
  status?: string
  message?: string
  source?: string
  source_index?: number
  source_total?: number
  discovered?: number
  selected?: number
  skipped_existing?: number
  fetched?: number
  ok?: number
  /** Fetch failure count while crawling, or error string on terminal failure. */
  error?: number | string
  saved?: number
  sources?: number
  code?: number
}

export const crawlSources = (payload?: {
  domains?: string[]
  max_links_per_source?: number
  max_articles_total?: number
}) =>
  requestJson<CollectCrawlStats>('/url2md/crawl', jsonInit('POST', payload ?? {}))

export const crawlSourcesStream = async (
  payload: {
    domains?: string[]
    max_links_per_source?: number
    max_articles_total?: number
  } | undefined,
  onProgress: (event: CollectCrawlProgress) => void,
  signal?: AbortSignal,
): Promise<CollectCrawlStats> => {
  const init = jsonInit('POST', payload ?? {})
  const response = await apiFetch('/url2md/crawl?stream=true', {
    ...init,
    signal,
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      Accept: 'text/event-stream',
    },
  })
  if (!response.ok) {
    let message = `Collect crawl failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string; message?: string }
      message = body.detail || body.message || message
    } catch {
      // ignore non-json bodies
    }
    throw new ApiError(message, response.status)
  }
  if (!response.body) {
    throw new Error('Collect crawl stream has no body')
  }
  let stats: CollectCrawlStats = {}
  let failed: string | null = null
  await consumeSse(
    response.body,
    ({ event, data }) => {
      let payloadEvent: CollectCrawlProgress = {}
      try {
        payloadEvent = data ? (JSON.parse(data) as CollectCrawlProgress) : {}
      } catch {
        payloadEvent = { message: data }
      }
      onProgress(payloadEvent)
      if (typeof payloadEvent.discovered === 'number') stats.discovered = payloadEvent.discovered
      if (typeof payloadEvent.selected === 'number') stats.selected = payloadEvent.selected
      if (typeof payloadEvent.skipped_existing === 'number') {
        stats.skipped_existing = payloadEvent.skipped_existing
      }
      if (typeof payloadEvent.fetched === 'number') stats.fetched = payloadEvent.fetched
      if (typeof payloadEvent.ok === 'number') stats.ok = payloadEvent.ok
      if (typeof payloadEvent.error === 'number') stats.error = payloadEvent.error
      if (typeof payloadEvent.saved === 'number') stats.saved = payloadEvent.saved
      if (typeof payloadEvent.sources === 'number') stats.sources = payloadEvent.sources
      if (event === 'progress.failed' || payloadEvent.status === 'failed') {
        failed =
          (typeof payloadEvent.error === 'string' ? payloadEvent.error : null) ||
          payloadEvent.message ||
          'Collect crawl failed'
      }
    },
    signal,
  )
  if (failed) throw new Error(failed)
  return stats
}


export const getArticle = (articleId: number) =>
  requestJson<CollectArticle>(`/url2md/articles/${articleId}`)

export const reparseArticle = (articleId: number) =>
  requestJson<CollectArticle>(`/url2md/articles/${articleId}/reparse`, jsonInit('POST', {}))


export const reparseFailedArticles = (payload?: {
  source_domain?: string
  limit?: number
}) =>
  requestJson<{
    message?: string
    requested?: number
    ok?: number
    error?: number
  }>('/url2md/articles/reparse-failed', jsonInit('POST', payload ?? {}))

export const getLibraryStats = (sourceDomain?: string) => {
  const q = sourceDomain ? `?source_domain=${encodeURIComponent(sourceDomain)}` : ''
  return requestJson<CollectLibraryStats>(`/url2md/stats${q}`)
}
