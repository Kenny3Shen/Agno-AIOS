import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Conversations } from '@ant-design/x'
import { App, Flex, Form, Input, Modal } from 'antd'
import { CopyOutlined, DeleteOutlined, EditOutlined, FieldTimeOutlined } from '@ant-design/icons'
import { archiveSession, renameSession } from './api'
import { chatKeys } from './queries'
import { useChat } from './useChat'
import type { ChatSession } from './types'
import { copyToClipboard } from '@/shared/lib/clipboard'

export function ChatTaskPanel() {
  const { message: toast } = App.useApp()
  const chat = useChat()
  const queryClient = useQueryClient()
  const [renameTarget, setRenameTarget] = useState<ChatSession | null>(null)
  const [renameForm] = Form.useForm<{ title: string }>()
  const [renaming, setRenaming] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<string[]>([])
  const expandedGroupsInitialized = useRef(false)
  const conversations = useMemo(
    () =>
      (chat.sessions.data ?? []).map((session) => {
        const date = new Date(session.updated_at * 1000)
        const today = new Date()
        today.setHours(0, 0, 0, 0)
        date.setHours(0, 0, 0, 0)
        const daysAgo = Math.round((today.getTime() - date.getTime()) / 86_400_000)
        return {
          key: session.session_id,
          label: session.title || session.preview || '未命名会话',
          group: daysAgo === 0 ? 'Today' : daysAgo === 1 ? 'Yesterday' : 'Historical',
        }
      }),
    [chat.sessions.data]
  )
  const conversationGroups = useMemo(() => Array.from(new Set(conversations.map((item) => item.group))), [conversations])
  useEffect(() => {
    if (expandedGroupsInitialized.current || !conversationGroups.length) return
    setExpandedGroups([conversationGroups[0]])
    expandedGroupsInitialized.current = true
  }, [conversationGroups])
  const startRename = (session: ChatSession) => {
    renameForm.setFieldsValue({ title: session.title || session.preview || '' })
    setRenameTarget(session)
  }
  const copySessionId = (sessionId: string) => {
    void copyToClipboard(sessionId).then((copied) => (copied ? toast.success('Session ID 已复制') : toast.error('Session ID 复制失败')))
  }
  const archive = async (sessionId: string) => {
    try {
      await archiveSession(sessionId)
      if (chat.sessionId === sessionId) chat.newChat()
      await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
      toast.success('会话已归档')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '归档会话失败')
    }
  }
  const confirmRename = async () => {
    const { title } = await renameForm.validateFields()
    if (!renameTarget) return
    setRenaming(true)
    try {
      const updated = await renameSession(renameTarget.session_id, title.trim())
      queryClient.setQueryData<ChatSession[]>(chatKeys.sessions(), (items) =>
        (items ?? []).map((item) =>
          item.session_id === renameTarget.session_id ? { ...item, ...updated, title: updated.title ?? title.trim() } : item
        )
      )
      toast.success('会话已重命名')
      setRenameTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '重命名失败')
    } finally {
      setRenaming(false)
    }
  }

  return (
    <>
      <section className="chat-task-panel" aria-label="对话任务">
        <Conversations
          items={conversations}
          activeKey={chat.sessionId ?? undefined}
          onActiveChange={(key) => chat.setSession(key)}
          groupable={{
            label: (group) => (
              <Flex gap="small">
                <FieldTimeOutlined />
                {group}
              </Flex>
            ),
            collapsible: (group) => group !== 'Today',
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
                label: '重命名',
                onClick: () => {
                  const session = (chat.sessions.data ?? []).find((value) => value.session_id === item.key)
                  if (session) startRename(session)
                },
              },
              { key: 'copy-session-id', icon: <CopyOutlined />, label: '复制 Session ID', onClick: () => copySessionId(item.key) },
              { key: 'archive', danger: true, icon: <DeleteOutlined />, label: '归档', onClick: () => void archive(item.key) },
            ],
          })}
        />
      </section>
      <Modal
        title="重命名会话"
        open={Boolean(renameTarget)}
        confirmLoading={renaming}
        okText="保存"
        onOk={() => void confirmRename()}
        onCancel={() => setRenameTarget(null)}
      >
        <Form form={renameForm} layout="vertical">
          <Form.Item
            name="title"
            label="会话标题"
            rules={[
              { required: true, whitespace: true, message: '请输入会话标题' },
              { max: 120, message: '标题不能超过 120 个字符' },
            ]}
          >
            <Input maxLength={120} onPressEnter={() => void confirmRename()} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
