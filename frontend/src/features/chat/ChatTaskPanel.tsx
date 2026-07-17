import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { Conversations } from '@ant-design/x'
import { App, Button, Empty, Flex, Form, Input, Modal, Skeleton } from 'antd'
import {
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  FieldTimeOutlined,
  HistoryOutlined,
  ReloadOutlined,
  RightOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useTranslation } from 'react-i18next'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { archiveSession, cancelRun, renameSession, unarchiveSession, type SessionListResult } from './api'
import { abortActiveChatStream, getActiveChatStream } from './activeChatStream'
import { chatKeys, sessionsQuery } from './queries'
import type { ChatSession } from './types'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'
import { buildTraceSearch, emptyTraceFilters } from '@/features/trace/utils'
import { ApiError } from '@/shared/api/client'

export type ConversationGroupKey = 'today' | 'yesterday' | 'earlier'

export interface ChatTaskPanelProps {
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  variant: 'sider' | 'drawer'
  onNavigate?: () => void
}

export interface ConversationListItem {
  key: string
  label: string
  group: ConversationGroupKey
  title: string
}

export function buildConversationItems(sessions: ChatSession[], now = Date.now()): ConversationListItem[] {
  const today = dayjs(now).startOf('day')
  return [...sessions]
    .sort((left, right) => right.updated_at - left.updated_at)
    .map((session) => {
      const daysAgo = today.diff(dayjs.unix(session.updated_at).startOf('day'), 'day')
      const base = session.title || session.preview || ''
      const isWorkflow = String(session.session_type || '').toLowerCase() === 'workflow'
      const label = isWorkflow ? (base.startsWith('[WF]') ? base : `[WF] ${base}`) : base
      return {
        key: session.session_id,
        label,
        group: daysAgo <= 0 ? 'today' : daysAgo === 1 ? 'yesterday' : 'earlier',
        title: label,
      }
    })
}

export function filterConversationItems(items: ConversationListItem[], query: string): ConversationListItem[] {
  const q = query.trim().toLowerCase()
  if (!q) return items
  return items.filter((item) => {
    const label = item.label.toLowerCase()
    const title = item.title.toLowerCase()
    const id = item.key.toLowerCase()
    return label.includes(q) || title.includes(q) || id.includes(q)
  })
}

function bestEffortCancelRun(runId: string | null | undefined) {
  if (!runId) return
  void cancelRun(runId).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) return
    const detail = error instanceof Error ? error.message : String(error)
    console.warn(`[chat] cancel on session switch failed for ${runId}: ${detail}`)
  })
}

/** Sidebar/drawer recents list — session list only, no live stream state. */
export function ChatTaskPanel({ expanded, onExpandedChange, variant, onNavigate }: ChatTaskPanelProps) {
  const { message: toast, modal } = App.useApp()
  const { t } = useTranslation()
  const router = useRouter()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const sessionId = new URLSearchParams(searchStr).get('session')
  const queryClient = useQueryClient()
  const contentId = useId()
  const [sessionSearch, setSessionSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const debouncedSessionSearch = useDebouncedValue(sessionSearch, 300)
  const [renameTarget, setRenameTarget] = useState<ChatSession | null>(null)
  const [renameForm] = Form.useForm<{ title: string }>()
  const [renaming, setRenaming] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<string[]>([])
  const expandedGroupsInitialized = useRef(false)

  const sessionsQueryResult = useInfiniteQuery(
    sessionsQuery({
      archivedOnly: showArchived,
      q: debouncedSessionSearch.trim(),
    }),
  )
  const sessionItems = useMemo(
    () => sessionsQueryResult.data?.pages.flatMap((page) => page.data) ?? [],
    [sessionsQueryResult.data],
  )
  const sessions = {
    ...sessionsQueryResult,
    data: sessionItems,
  }

  const conversations = useMemo(
    () =>
      buildConversationItems(sessionItems).map((item) => ({
        ...item,
        label: item.label || t('shell:conversations.unnamed'),
        title: item.title || t('shell:conversations.unnamed'),
      })),
    [sessionItems, t],
  )
  // Only client-filter once the server query has caught up (avoid empty flash while typing).
  const filteredConversations = useMemo(() => {
    if (sessionSearch.trim() !== debouncedSessionSearch.trim()) {
      return conversations
    }
    return filterConversationItems(conversations, sessionSearch)
  }, [conversations, sessionSearch, debouncedSessionSearch])
  const conversationGroups = useMemo(
    () => Array.from(new Set(filteredConversations.map((item) => item.group))),
    [filteredConversations],
  )

  useEffect(() => {
    if (expandedGroupsInitialized.current || !conversationGroups.length) return
    setExpandedGroups([conversationGroups.includes('today') ? 'today' : conversationGroups[0]!])
    expandedGroupsInitialized.current = true
  }, [conversationGroups])

  // When searching, expand every group so matches are visible without clicking.
  useEffect(() => {
    if (!sessionSearch.trim() || !conversationGroups.length) return
    setExpandedGroups(conversationGroups)
    expandedGroupsInitialized.current = true
  }, [sessionSearch, conversationGroups])

  const navigateToChatSession = (next: string | null) => {
    const same = (next == null && !sessionId) || (next != null && next === sessionId)
    if (!same) {
      const { runId } = abortActiveChatStream()
      bestEffortCancelRun(runId)
    }
    if (same) return
    void router.history.push(next ? `/chat?session=${encodeURIComponent(next)}` : '/chat')
  }

  const startRename = (session: ChatSession) => {
    renameForm.setFieldsValue({ title: session.title || session.preview || '' })
    setRenameTarget(session)
  }
  const copySessionId = (id: string) => {
    void copyToClipboard(id).then((copied) =>
      copied ? toast.success(t('shell:conversations.copied')) : toast.error(t('shell:conversations.copyFailed')),
    )
  }
  const archive = async (id: string) => {
    const live = getActiveChatStream()
    const archivingActive = sessionId === id && Boolean(live)
    const run = async () => {
      try {
        // Stop any live stream for this session before archive.
        if (archivingActive) {
          const { runId } = abortActiveChatStream()
          bestEffortCancelRun(runId)
        }
        await archiveSession(id)
        if (sessionId === id) navigateToChatSession(null)
        await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
        toast.success(t('shell:conversations.archived'))
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('shell:conversations.archiveFailed'))
      }
    }
    if (!archivingActive) {
      await run()
      return
    }
    modal.confirm({
      title: t('chat:archiveWhileGeneratingTitle'),
      content: t('chat:archiveWhileGeneratingContent'),
      okText: t('chat:archiveAndStop'),
      cancelText: t('common:cancel'),
      okButtonProps: { danger: true },
      onOk: () => run(),
    })
  }
  const unarchive = async (id: string) => {
    try {
      await unarchiveSession(id)
      await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
      toast.success(t('shell:conversations.unarchived'))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('shell:conversations.unarchiveFailed'))
    }
  }
  const confirmRename = async () => {
    const { title } = await renameForm.validateFields()
    if (!renameTarget) return
    setRenaming(true)
    try {
      const updated = await renameSession(renameTarget.session_id, title.trim())
      queryClient.setQueriesData<{ pages: SessionListResult[]; pageParams: number[] }>(
        { queryKey: chatKeys.sessionLists },
        (current) => {
          if (!current?.pages?.length) return current
          return {
            ...current,
            pages: current.pages.map((page) => ({
              ...page,
              data: page.data.map((item) =>
                item.session_id === renameTarget.session_id
                  ? { ...item, ...updated, title: updated.title ?? title.trim() }
                  : item,
              ),
            })),
          }
        },
      )
      queryClient.setQueryData(chatKeys.sessionMeta(renameTarget.session_id), (current: ChatSession | null | undefined) => {
        const titleValue = updated.title ?? title.trim()
        if (current) return { ...current, ...updated, title: titleValue }
        return {
          ...renameTarget,
          ...updated,
          title: titleValue,
        }
      })
      toast.success(t('shell:conversations.renamed'))
      setRenameTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('shell:conversations.renameFailed'))
    } finally {
      setRenaming(false)
    }
  }
  const openSession = (id: string) => {
    const session = sessionItems.find((item) => item.session_id === id)
    const isWorkflow = String(session?.session_type || '').toLowerCase() === 'workflow'
    if (isWorkflow) {
      // Prefer Studio when workflow_id is known; otherwise open Trace for this session.
      const workflowId = String(session?.workflow_id || '').trim()
      if (workflowId) {
        void router.history.push(`/workflow?workflow_id=${encodeURIComponent(workflowId)}`)
        onNavigate?.()
        return
      }
      const filters = {
        ...emptyTraceFilters(),
        session_id: id,
      }
      const search = buildTraceSearch(filters, id, '')
      void router.history.push(`/trace${search ? `?${search}` : ''}`)
      onNavigate?.()
      return
    }
    navigateToChatSession(id)
    onNavigate?.()
  }

  return (
    <>
      <section
        className={`chat-task-panel chat-task-panel-${variant} ${expanded ? 'chat-task-panel-expanded' : 'chat-task-panel-collapsed'}`}
        aria-label={
          showArchived ? t('shell:conversations.archivedTitle') : t('shell:conversations.title')
        }
      >
        <button
          type="button"
          className="chat-task-panel-toggle"
          aria-expanded={expanded}
          aria-controls={contentId}
          aria-label={
            showArchived ? t('shell:conversations.archivedTitle') : t('shell:conversations.title')
          }
          onClick={() => onExpandedChange(!expanded)}
        >
          <span className="chat-task-panel-toggle-label">
            <HistoryOutlined />
            {showArchived
              ? t('shell:conversations.archivedTitle')
              : t('shell:conversations.title')}
          </span>
          {expanded ? <DownOutlined /> : <RightOutlined />}
        </button>
        {expanded ? (
          <div id={contentId} className="chat-task-panel-content">
            {sessions.isLoading && !sessionItems.length && !sessionSearch ? (
              <div className="chat-task-panel-loading" aria-label={t('common:loading')}>
                <Skeleton active title={false} paragraph={{ rows: 3 }} />
              </div>
            ) : sessions.isError ? (
              <div className="chat-task-panel-state" role="alert">
                <span>{t('shell:conversations.loadFailed')}</span>
                <Button
                  size="small"
                  type="text"
                  icon={<ReloadOutlined />}
                  aria-label={t('shell:conversations.retry')}
                  onClick={() => void sessions.refetch()}
                >
                  {t('shell:conversations.retry')}
                </Button>
              </div>
            ) : (
              <>
                <div className="chat-task-panel-mode">
                  <Button
                    size="small"
                    type={showArchived ? 'default' : 'primary'}
                    onClick={() => {
                      if (showArchived) setShowArchived(false)
                    }}
                  >
                    {t('shell:conversations.recents')}
                  </Button>
                  <Button
                    size="small"
                    type={showArchived ? 'primary' : 'default'}
                    onClick={() => {
                      if (!showArchived) setShowArchived(true)
                    }}
                  >
                    {t('shell:conversations.archivedInbox')}
                  </Button>
                </div>
                {sessionItems.length || sessionSearch.trim() ? (
                  <Input.Search
                    allowClear
                    className="chat-task-panel-search"
                    placeholder={t('shell:conversations.searchPlaceholder')}
                    value={sessionSearch}
                    onChange={(event) => setSessionSearch(event.target.value)}
                    loading={Boolean(sessions.isFetching && !sessions.isFetchingNextPage)}
                    aria-label={t('shell:conversations.searchPlaceholder')}
                  />
                ) : null}
                <Conversations
                  items={filteredConversations}
                  activeKey={sessionId ?? undefined}
                  onActiveChange={openSession}
                  groupable={{
                    label: (group) => (
                      <Flex gap="small">
                        <FieldTimeOutlined />
                        {t(`shell:conversations.${group}`)}
                      </Flex>
                    ),
                    collapsible: (group) => group !== 'today',
                    expandedKeys: expandedGroups,
                    onExpand: (keys) => {
                      expandedGroupsInitialized.current = true
                      setExpandedGroups(keys)
                    },
                  }}
                  menu={(item) => ({
                    items: [
                      {
                        key: 'rename',
                        icon: <EditOutlined />,
                        label: t('shell:conversations.rename'),
                        onClick: () => {
                          const session = sessionItems.find((value) => value.session_id === item.key)
                          if (session) startRename(session)
                        },
                      },
                      {
                        key: 'copy-session-id',
                        icon: <CopyOutlined />,
                        label: t('shell:conversations.copySessionId'),
                        onClick: () => copySessionId(item.key),
                      },
                      showArchived
                        ? {
                            key: 'unarchive',
                            icon: <UndoOutlined />,
                            label: t('shell:conversations.unarchive'),
                            onClick: () => void unarchive(item.key),
                          }
                        : {
                            key: 'archive',
                            danger: true,
                            icon: <DeleteOutlined />,
                            label: t('shell:conversations.archive'),
                            onClick: () => void archive(item.key),
                          },
                    ],
                  })}
                />
                {sessions.hasNextPage ? (
                  <div className="chat-task-panel-load-more">
                    <Button
                      size="small"
                      type="link"
                      loading={Boolean(sessions.isFetchingNextPage)}
                      disabled={Boolean(sessions.isFetchingNextPage)}
                      onClick={() => void sessions.fetchNextPage()}
                    >
                      {t('shell:conversations.loadMore')}
                    </Button>
                  </div>
                ) : null}
                {!conversations.length && !sessionSearch.trim() ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      showArchived
                        ? t('shell:conversations.emptyArchived')
                        : t('shell:conversations.empty')
                    }
                    className="chat-task-panel-empty"
                  />
                ) : !filteredConversations.length ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('shell:conversations.emptySearch')}
                    className="chat-task-panel-empty"
                  />
                ) : null}
              </>
            )}
          </div>
        ) : null}
      </section>
      <Modal
        title={t('shell:conversations.renameTitle')}
        open={Boolean(renameTarget)}
        confirmLoading={renaming}
        okText={t('common:save')}
        onOk={() => void confirmRename()}
        onCancel={() => setRenameTarget(null)}
      >
        <Form form={renameForm} layout="vertical">
          <Form.Item
            name="title"
            label={t('shell:conversations.sessionTitle')}
            rules={[
              { required: true, whitespace: true, message: t('shell:conversations.titleRequired') },
              { max: 120, message: t('shell:conversations.titleTooLong') },
            ]}
          >
            <Input maxLength={120} onPressEnter={() => void confirmRename()} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
