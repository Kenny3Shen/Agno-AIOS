/**
 * Collect / 安全情报 page: search the article library, sync sources, parse URLs.
 * CVE tags deep-link to the CVE workspace when ids are present on a row.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from '@tanstack/react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App, Button, Card, Empty, Input, Pagination, Progress, Select, Space, Splitter, Tag, Typography } from 'antd'
import { Markdown } from '@/shared/ui/Markdown'
import {
  CloudDownloadOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { hasScope, roleOf } from '@/shared/auth/permissions'
import {
  crawlSourcesStream,
  getArticle,
  getLibraryStats,
  listSources,
  parseUrl,
  reparseArticle,
  reparseFailedArticles,
  searchArticles,
  type CollectArticle,
  type CollectCrawlProgress,
} from './api'
import { useTranslation } from 'react-i18next'
import { useFormatDate } from '@/shared/lib/format'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'


function crawlProgressPercent(event: CollectCrawlProgress | null): number {
  if (!event) return 0
  if (event.stage === 'done' && event.status === 'completed') return 100
  if (event.stage === 'database') return 90
  if (event.stage === 'fetch' && event.selected) {
    const fetched = Math.max(0, Number(event.fetched || 0))
    const total = Math.max(1, Number(event.selected || 1))
    return Math.min(88, 45 + Math.round((fetched / total) * 40))
  }
  if (event.stage === 'select') return 40
  if (event.stage === 'discover' && event.source_total) {
    const index = Math.max(0, Number(event.source_index || 0))
    const total = Math.max(1, Number(event.source_total || 1))
    return Math.min(35, Math.round((index / total) * 30) + 5)
  }
  if (event.stage === 'start') return 3
  return 10
}

/** Prefer structured stage fields so EN/ZH UI does not show server-hardcoded Chinese. */
function formatCrawlProgressMessage(
  event: CollectCrawlProgress | null,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!event) return t('crawlStarting')
  if (event.status === 'cancelled') {
    return event.message || t('crawlCancelled')
  }
  if (event.status === 'failed') {
    return (
      (typeof event.error === 'string' && event.error) ||
      event.message ||
      t('crawlFailed')
    )
  }
  const stage = event.stage || ''
  if (stage === 'start') return t('crawlStageStart')
  if (stage === 'discover') {
    if (event.source) {
      return t('crawlStageDiscoverSource', {
        source: event.source,
        links: event.discovered ?? 0,
        index: event.source_index ?? 0,
        total: event.source_total ?? 0,
      })
    }
    return t('crawlStageDiscover')
  }
  if (stage === 'select') {
    if (event.status === 'completed' || typeof event.selected === 'number') {
      return t('crawlStageSelectDone', {
        selected: event.selected ?? 0,
        skipped: event.skipped_existing ?? 0,
        discovered: event.discovered ?? 0,
      })
    }
    return t('crawlStageSelect', { discovered: event.discovered ?? 0 })
  }
  if (stage === 'fetch') {
    return t('crawlStageFetch', {
      fetched: event.fetched ?? 0,
      selected: event.selected ?? 0,
      ok: event.ok ?? 0,
      error: typeof event.error === 'number' ? event.error : 0,
    })
  }
  if (stage === 'database') {
    return t('crawlStageDatabase', {
      ok: event.ok ?? 0,
      error: typeof event.error === 'number' ? event.error : 0,
    })
  }
  if (stage === 'done' && event.status === 'completed') {
    return t('crawlStageDone', {
      discovered: event.discovered ?? 0,
      selected: event.selected ?? 0,
      ok: event.ok ?? 0,
      saved: event.saved ?? 0,
    })
  }
  return event.message || t('crawlStarting')
}

export function CollectPage() {
  const { t } = useTranslation('collect')
  const router = useRouter()
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const canWrite = hasScope(currentUser.data, 'collect:write')

  const [url, setUrl] = useState('')
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query, 300)
  const [sourceDomain, setSourceDomain] = useState<string>()
  const [statusFilter, setStatusFilter] = useState<'ok' | 'error' | 'all'>('ok')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<CollectArticle | null>(null)
  const [previewMarkdown, setPreviewMarkdown] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewReloadToken, setPreviewReloadToken] = useState(0)
  const [crawlProgress, setCrawlProgress] = useState<CollectCrawlProgress | null>(null)
  const crawlAbortRef = useRef<AbortController | null>(null)

  const sourcesQuery = useQuery({
    queryKey: ['collect', 'sources'],
    queryFn: listSources,
  })
  const statsQuery = useQuery({
    queryKey: ['collect', 'stats', sourceDomain],
    queryFn: () => getLibraryStats(sourceDomain),
  })

  useEffect(() => {
    setPage(1)
  }, [debouncedQuery, sourceDomain, statusFilter])

  useEffect(() => {
    return () => {
      crawlAbortRef.current?.abort()
    }
  }, [])

  const articlesQuery = useQuery({
    queryKey: ['collect', 'articles', debouncedQuery, sourceDomain, statusFilter, page],
    queryFn: () =>
      searchArticles({
        query: debouncedQuery,
        source_domain: sourceDomain,
        status: statusFilter,
        page,
        size: 20,
      }),
  })

  // List payloads omit markdown; load body when selection changes.
  useEffect(() => {
    let cancelled = false
    if (!selected?.id) {
      setPreviewMarkdown('')
      setPreviewError(null)
      setPreviewLoading(false)
      return
    }
    if (selected.markdown) {
      setPreviewMarkdown(selected.markdown)
      setPreviewError(null)
      setPreviewLoading(false)
      return
    }
    setPreviewLoading(true)
    setPreviewError(null)
    void getArticle(selected.id)
      .then((row) => {
        if (cancelled) return
        setPreviewMarkdown(row.markdown || '')
        setPreviewError(null)
        setSelected((prev) =>
          prev && prev.id === row.id ? { ...prev, ...row, markdown: row.markdown || '' } : prev,
        )
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setPreviewMarkdown('')
        setPreviewError(error instanceof Error ? error.message : t('previewLoadFailed'))
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected?.id, selected?.markdown, previewReloadToken, t])

  const parseMutation = useMutation({
    mutationFn: () => parseUrl(url),
    onSuccess: async (data) => {
      message.success(t('parseOk'))
      setUrl('')
      await Promise.all([articlesQuery.refetch(), statsQuery.refetch(), sourcesQuery.refetch()])
      const markdown = data.markdown || ''
      if (data.id) {
        setSelected({
          id: data.id,
          url,
          source_domain: data.source_domain || '',
          title: data.title || url,
          markdown,
          summary: data.summary || '',
          status: 'ok',
          cve_ids: data.cve_ids || [],
        })
      }
    },
    onError: (err: Error) => message.error(err.message || t('parseFailed')),
  })

  const crawlMutation = useMutation({
    mutationFn: async () => {
      const scoped = Boolean(sourceDomain)
      crawlAbortRef.current?.abort()
      const controller = new AbortController()
      crawlAbortRef.current = controller
      setCrawlProgress({
        stage: 'start',
        status: 'running',
        message: scoped
          ? t('crawlStartingSource', { source: sourceDomain })
          : t('crawlStarting'),
      })
      try {
        return await crawlSourcesStream(
          {
            // When a source filter is active, only sync that domain (faster ops).
            domains: sourceDomain ? [sourceDomain] : undefined,
            max_links_per_source: scoped ? 20 : 15,
            max_articles_total: scoped ? 30 : 60,
          },
          (event) => {
            setCrawlProgress(event)
          },
          controller.signal,
        )
      } finally {
        if (crawlAbortRef.current === controller) {
          crawlAbortRef.current = null
        }
      }
    },
    onSuccess: async (data) => {
      message.success(
        t('crawlOk', {
          ok: data.ok ?? 0,
          saved: data.saved ?? 0,
          discovered: data.discovered ?? 0,
          selected: data.selected ?? data.fetched ?? 0,
          skipped: data.skipped_existing ?? 0,
        }),
      )
      setCrawlProgress((prev) =>
        prev
          ? {
              ...prev,
              stage: 'done',
              status: 'completed',
              ok: data.ok,
              saved: data.saved,
              discovered: data.discovered,
              selected: data.selected ?? data.fetched,
              skipped_existing: data.skipped_existing,
            }
          : prev,
      )
      await Promise.all([articlesQuery.refetch(), sourcesQuery.refetch(), statsQuery.refetch()])
    },
    onError: (err: Error) => {
      if (err.name === 'AbortError') {
        message.info(t('crawlCancelled'))
        setCrawlProgress((prev) =>
          prev
            ? {
                ...prev,
                stage: 'done',
                status: 'cancelled',
                message: t('crawlCancelled'),
              }
            : { stage: 'done', status: 'cancelled', message: t('crawlCancelled') },
        )
        void Promise.all([articlesQuery.refetch(), sourcesQuery.refetch(), statsQuery.refetch()])
        return
      }
      message.error(err.message || t('crawlFailed'))
      setCrawlProgress((prev) =>
        prev
          ? {
              ...prev,
              stage: 'done',
              status: 'failed',
              message: err.message || t('crawlFailed'),
            }
          : { stage: 'done', status: 'failed', message: t('crawlFailed') },
      )
    },
  })

  const stopCrawl = () => {
    crawlAbortRef.current?.abort()
  }

  const reparseMutation = useMutation({
    mutationFn: (articleId: number) => reparseArticle(articleId),
    onSuccess: async (row) => {
      message.success(t('reparseOk'))
      await Promise.all([articlesQuery.refetch(), statsQuery.refetch(), sourcesQuery.refetch()])
      setSelected(row)
      setPreviewMarkdown(row.markdown || '')
    },
    onError: (err: Error) => message.error(err.message || t('reparseFailed')),
  })

  const bulkReparseMutation = useMutation({
    mutationFn: () =>
      reparseFailedArticles({
        source_domain: sourceDomain,
        limit: 10,
      }),
    onSuccess: async (data) => {
      message.success(
        t('bulkReparseOk', {
          ok: data.ok ?? 0,
          error: data.error ?? 0,
          requested: data.requested ?? 0,
        }),
      )
      await Promise.all([articlesQuery.refetch(), statsQuery.refetch(), sourcesQuery.refetch()])
    },
    onError: (err: Error) => message.error(err.message || t('bulkReparseFailed')),
  })

  const crawlPercent = crawlProgressPercent(crawlProgress)
  const crawling = crawlMutation.isPending
  const items = articlesQuery.data?.data ?? []
  const total = articlesQuery.data?.meta.total_count ?? 0
  const sourceRows = sourcesQuery.data?.data
  const sourceOptions = useMemo(() => {
    const sources = sourceRows ?? []
    return [...sources]
      .sort((a, b) => {
        const ae = a.error_count ?? 0
        const be = b.error_count ?? 0
        if (be !== ae) return be - ae
        return a.domain.localeCompare(b.domain)
      })
      .map((item) => {
        const err = item.error_count ?? 0
        const ok = item.ok_count ?? 0
        const suffix =
          err > 0 ? ` · ${ok}/${ok + err}` : ok > 0 ? ` · ${ok}` : ''
        return {
          value: item.domain,
          label: `${item.domain}${suffix}`,
        }
      })
  }, [sourceRows])
  const unhealthySources = useMemo(() => {
    const sources = sourceRows ?? []
    return sources
      .filter((item) => (item.error_count ?? 0) > 0)
      .sort((a, b) => (b.error_count ?? 0) - (a.error_count ?? 0))
  }, [sourceRows])
  const errorTotal = statsQuery.data?.error ?? 0

  const activeMarkdown = previewMarkdown

  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card collect-card">
        <Space className="collect-toolbar" wrap style={{ width: '100%', marginBottom: 12 }}>
          <Space.Compact style={{ minWidth: 280, flex: 1 }}>
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onPressEnter={() => {
                setPage(1)
              }}
              placeholder={t('searchPlaceholder')}
              allowClear
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={articlesQuery.isFetching}
              onClick={() => {
                setPage(1)
              }}
            >
              {t('common:search')}
            </Button>
          </Space.Compact>
          <Select
            allowClear
            style={{ minWidth: 200 }}
            value={sourceDomain}
            onChange={(value) => {
              setSourceDomain(value)
              setPage(1)
            }}
            placeholder={t('allSources')}
            options={sourceOptions}
            loading={sourcesQuery.isLoading}
          />
          <Select
            style={{ minWidth: 140 }}
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value)
              setPage(1)
              setSelected(null)
            }}
            options={[
              { value: 'ok', label: t('statusOk') },
              { value: 'error', label: t('statusError') },
              { value: 'all', label: t('statusAll') },
            ]}
          />
          {isAdmin ? (
            crawling ? (
              <Button
                danger
                icon={<StopOutlined />}
                title={t('crawlStopHint')}
                onClick={stopCrawl}
              >
                {t('crawlStop')}
              </Button>
            ) : (
              <Button
                icon={<ReloadOutlined />}
                title={
                  sourceDomain
                    ? t('crawlSourceHint', { source: sourceDomain })
                    : t('crawlAllHint')
                }
                onClick={() => crawlMutation.mutate()}
              >
                {sourceDomain ? t('crawlSelectedSource') : t('crawlSources')}
              </Button>
            )
          ) : null}
          {canWrite && (statusFilter === 'error' || errorTotal > 0) ? (
            <Button
              loading={bulkReparseMutation.isPending}
              onClick={() => bulkReparseMutation.mutate()}
            >
              {t('bulkReparse', { count: Math.min(10, errorTotal || 10) })}
            </Button>
          ) : null}
          {errorTotal > 0 ? (
            <Tag
              color="error"
              style={{ cursor: 'pointer', marginInlineEnd: 0 }}
              onClick={() => {
                setStatusFilter('error')
                setPage(1)
              }}
            >
              {t('errorCountBadge', { count: errorTotal })}
            </Tag>
          ) : null}
        </Space>

        {crawlProgress ? (
          <div style={{ marginBottom: 12, maxWidth: 640 }}>
            <Progress
              percent={crawlPercent}
              status={
                crawlProgress.status === 'failed'
                  ? 'exception'
                  : crawlProgress.status === 'cancelled'
                    ? 'normal'
                    : crawlProgress.status === 'completed' && crawlProgress.stage === 'done'
                      ? 'success'
                      : crawling
                        ? 'active'
                        : 'normal'
              }
              size="small"
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatCrawlProgressMessage(crawlProgress, t)}
            </Typography.Text>
          </div>
        ) : null}

        {unhealthySources.length > 0 ? (
          <div className="collect-source-health" style={{ marginBottom: 12 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12, marginInlineEnd: 8 }}>
              {t('sourceHealthLabel')}
            </Typography.Text>
            <Space size={[4, 4]} wrap>
              {unhealthySources.map((item) => {
                const err = item.error_count ?? 0
                const ok = item.ok_count ?? 0
                const active = sourceDomain === item.domain
                return (
                  <Tag
                    key={item.domain}
                    color={active ? 'error' : 'warning'}
                    style={{ cursor: 'pointer', marginInlineEnd: 0 }}
                    onClick={() => {
                      setSourceDomain(item.domain)
                      setStatusFilter('error')
                      setPage(1)
                      setSelected(null)
                    }}
                  >
                    {t('sourceHealthItem', {
                      source: item.domain,
                      error: err,
                      ok,
                    })}
                  </Tag>
                )
              })}
            </Space>
          </div>
        ) : null}


        <Space.Compact className="collect-toolbar" style={{ width: '100%', marginBottom: 12 }}>
          <Input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            onPressEnter={() => url && parseMutation.mutate()}
            placeholder={t('urlPlaceholder')}
          />
          <Button
            type="default"
            icon={<CloudDownloadOutlined />}
            disabled={!url}
            loading={parseMutation.isPending}
            onClick={() => parseMutation.mutate()}
          >
            {t('action')}
          </Button>
        </Space.Compact>

        <Splitter className="workbench-splitter collect-splitter" orientation="horizontal">
          <Splitter.Panel defaultSize="38%" min="28%">
            <Card
              className="workbench-card splitter-panel-card"
              size="small"
              title={t('library')}
              extra={
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('total', { total })}
                </Typography.Text>
              }
            >
              {items.length ? (
                <div className="collect-article-list">
                  {items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={
                        selected?.id === item.id
                          ? 'collect-article-item is-selected'
                          : 'collect-article-item'
                      }
                      onClick={() => setSelected(item)}
                    >
                      <Space size={6} wrap>
                        <span>{item.title || item.url}</span>
                        {item.source_domain ? (
                          <Tag style={{ margin: 0 }}>{item.source_domain}</Tag>
                        ) : null}
                        {item.status === 'error' ? (
                          <Tag color="error" style={{ margin: 0 }}>
                            {t('statusError')}
                          </Tag>
                        ) : null}
                        {(item.cve_ids ?? []).slice(0, 3).map((cveId) => (
                          <Tag
                            key={cveId}
                            color="purple"
                            style={{ margin: 0, cursor: 'pointer' }}
                            title={t('openCve', { id: cveId })}
                            onClick={(event) => {
                              event.stopPropagation()
                              void router.history.push(
                                `/cve?q=${encodeURIComponent(cveId)}`,
                              )
                            }}
                          >
                            {cveId}
                          </Tag>
                        ))}
                        {(item.cve_ids?.length ?? 0) > 3 ? (
                          <Tag style={{ margin: 0 }}>+{(item.cve_ids?.length ?? 0) - 3}</Tag>
                        ) : null}
                      </Space>
                      <Typography.Paragraph
                        type="secondary"
                        ellipsis={{ rows: 2 }}
                        style={{ marginBottom: 4, fontSize: 12, textAlign: 'left' }}
                      >
                        {item.status === 'error'
                          ? item.error_message || item.summary || item.url
                          : item.summary || item.url}
                      </Typography.Paragraph>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        {item.fetched_at ? formatDate(item.fetched_at) : ''}
                      </Typography.Text>
                    </button>
                  ))}
                  <Pagination
                    size="small"
                    align="center"
                    current={page}
                    pageSize={20}
                    total={total}
                    onChange={setPage}
                    showSizeChanger={false}
                    style={{ marginTop: 8 }}
                  />
                </div>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    articlesQuery.isLoading ? t('loading') : t('emptyLibrary')
                  }
                />
              )}
            </Card>
          </Splitter.Panel>
          <Splitter.Panel defaultSize="62%" min="40%">
            <Card
              className="workbench-card splitter-panel-card"
              size="small"
              title={selected?.title || t('preview')}
              extra={
                selected ? (
                  <Space size={8}>
                    {selected.url ? (
                      <Typography.Link href={selected.url} target="_blank" rel="noreferrer">
                        {t('openSource')}
                      </Typography.Link>
                    ) : null}
                    {canWrite ? (
                      <Button
                        type="link"
                        size="small"
                        loading={reparseMutation.isPending}
                        onClick={() => reparseMutation.mutate(selected.id)}
                      >
                        {t('reparse')}
                      </Button>
                    ) : null}
                  </Space>
                ) : null
              }
            >
              {previewLoading ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('loading')} />
              ) : activeMarkdown ? (
                <div className="payload-viewer collect-preview">
                  {(selected?.cve_ids?.length ?? 0) > 0 ? (
                    <Space size={[4, 4]} wrap style={{ marginBottom: 10 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t('relatedCves')}
                      </Typography.Text>
                      {(selected?.cve_ids ?? []).map((cveId) => (
                        <Tag
                          key={cveId}
                          color="purple"
                          style={{ cursor: 'pointer', marginInlineEnd: 0 }}
                          title={t('openCve', { id: cveId })}
                          onClick={() => {
                            void router.history.push(`/cve?q=${encodeURIComponent(cveId)}`)
                          }}
                        >
                          {cveId}
                        </Tag>
                      ))}
                    </Space>
                  ) : null}
                  <Markdown content={activeMarkdown} openLinksInNewTab escapeRawHtml />
                </div>
              ) : previewError ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <Space orientation="vertical" size={8}>
                      <span>{previewError}</span>
                      <Button size="small" onClick={() => setPreviewReloadToken((n) => n + 1)}>
                        {t('common:retry')}
                      </Button>
                    </Space>
                  }
                />
              ) : selected?.status === 'error' ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={selected.error_message || t('emptyErrorPreview')}
                />
              ) : selected ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('emptyOkPreview')}
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('selectArticle')}
                />
              )}
            </Card>
          </Splitter.Panel>
        </Splitter>
      </Card>
    </main>
  )
}
