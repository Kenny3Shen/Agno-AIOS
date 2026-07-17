import { jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'

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

export type CollectListMeta = ListPaginationMeta

export const searchArticles = async (payload: {
  query?: string
  source_domain?: string
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

export const crawlSources = (payload?: {
  domains?: string[]
  max_links_per_source?: number
  max_articles_total?: number
}) =>
  requestJson<{
    message?: string
    sources?: number
    discovered?: number
    skipped_existing?: number
    selected?: number
    fetched?: number
    saved?: number
    ok?: number
    error?: number
  }>('/url2md/crawl', jsonInit('POST', payload ?? {}))
