import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App, Button, Card, Empty, Input, Pagination, Select, Space, Splitter, Tag, Typography } from 'antd'
import { Markdown } from '@/shared/ui/Markdown'
import {
  CloudDownloadOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import {
  crawlSources,
  listSources,
  parseUrl,
  searchArticles,
  type CollectArticle,
} from './api'
import { useTranslation } from 'react-i18next'
import { useFormatDate } from '@/shared/lib/format'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'

export function CollectPage() {
  const { t } = useTranslation('collect')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'

  const [url, setUrl] = useState('')
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query, 300)
  const [sourceDomain, setSourceDomain] = useState<string>()
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<CollectArticle | null>(null)

  const sourcesQuery = useQuery({
    queryKey: ['collect', 'sources'],
    queryFn: listSources,
  })

  useEffect(() => {
    setPage(1)
  }, [debouncedQuery, sourceDomain])

  const articlesQuery = useQuery({
    queryKey: ['collect', 'articles', debouncedQuery, sourceDomain, page],
    queryFn: () =>
      searchArticles({
        query: debouncedQuery,
        source_domain: sourceDomain,
        page,
        size: 20,
      }),
  })

  const parseMutation = useMutation({
    mutationFn: () => parseUrl(url),
    onSuccess: async (data) => {
      message.success(t('parseOk'))
      setUrl('')
      await articlesQuery.refetch()
      const markdown = Array.isArray(data.markdown)
        ? data.markdown.join('\n\n')
        : data.markdown || ''
      if (data.id) {
        setSelected({
          id: data.id,
          url,
          source_domain: data.source_domain || '',
          title: data.title || url,
          markdown,
          summary: '',
          status: 'ok',
        })
      }
    },
    onError: (err: Error) => message.error(err.message || t('parseFailed')),
  })

  const crawlMutation = useMutation({
    mutationFn: () => crawlSources({ max_links_per_source: 15, max_articles_total: 60 }),
    onSuccess: async (data) => {
      message.success(
        t('crawlOk', {
          ok: data.ok ?? 0,
          saved: data.saved ?? 0,
          discovered: data.discovered ?? 0,
        })
      )
      await Promise.all([articlesQuery.refetch(), sourcesQuery.refetch()])
    },
    onError: (err: Error) => message.error(err.message || t('crawlFailed')),
  })

  const items = articlesQuery.data?.data ?? []
  const total = articlesQuery.data?.meta.total_count ?? 0
  const sourceOptions = useMemo(
    () =>
      (sourcesQuery.data?.data ?? []).map((item) => ({
        value: item.domain,
        label: item.has_articles ? item.domain : `${item.domain}`,
      })),
    [sourcesQuery.data?.data]
  )

  const activeMarkdown = selected?.markdown ?? ''

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
          {isAdmin ? (
            <Button
              icon={<ReloadOutlined />}
              loading={crawlMutation.isPending}
              onClick={() => crawlMutation.mutate()}
            >
              {t('crawlSources')}
            </Button>
          ) : null}
        </Space>

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
                      </Space>
                      <Typography.Paragraph
                        type="secondary"
                        ellipsis={{ rows: 2 }}
                        style={{ marginBottom: 4, fontSize: 12, textAlign: 'left' }}
                      >
                        {item.summary || item.url}
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
                selected?.url ? (
                  <Typography.Link href={selected.url} target="_blank" rel="noreferrer">
                    {t('openSource')}
                  </Typography.Link>
                ) : null
              }
            >
              {activeMarkdown ? (
                <div className="payload-viewer collect-preview">
                  <Markdown content={activeMarkdown} openLinksInNewTab escapeRawHtml />
                </div>
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
