import { jsonInit, requestJson } from '@/shared/api/client'

export interface CollectArticle {
  id: number
  url: string
  source_domain: string
  title: string
  markdown: string
  summary: string
  status: string
  error_message?: string
  fetched_at?: string
  created_at?: string
  updated_at?: string
}

export interface CollectSource {
  domain: string
  has_rule: boolean
  has_articles: boolean
}

export const parseUrl = (url: string) =>
  requestJson<{
    markdown?: string | string[]
    title?: string
    source_domain?: string
    id?: number
    url?: string
  }>('/url2md/parse', jsonInit('POST', { url }))

export interface CollectListMeta {
  page: number
  limit: number
  total_pages: number
  total_count: number
  search_time_ms?: number
}

export const searchArticles = (payload: {
  query?: string
  source_domain?: string
  page?: number
  size?: number
}) =>
  requestJson<{ data: CollectArticle[]; meta: CollectListMeta }>(
    '/url2md/articles/search',
    jsonInit('POST', {
      query: payload.query ?? '',
      source_domain: payload.source_domain,
      page: payload.page ?? 1,
      size: payload.size ?? 20,
    })
  )

export const listSources = () =>
  requestJson<{ data: CollectSource[]; meta: CollectListMeta }>('/url2md/sources')

export const crawlSources = (payload?: {
  domains?: string[]
  max_links_per_source?: number
  max_articles_total?: number
}) =>
  requestJson<{
    message?: string
    sources?: number
    discovered?: number
    fetched?: number
    saved?: number
    ok?: number
    error?: number
  }>('/url2md/crawl', jsonInit('POST', payload ?? {}))
