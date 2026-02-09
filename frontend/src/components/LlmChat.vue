<template>
  <div class="flex flex-row h-full min-h-0 bg-white dark:bg-[#0D1117] overflow-hidden">
    <!-- 会话列表侧边栏 -->
    <div class="w-56 border-r border-[#D0D7DE] dark:border-[#30363D] flex-col hidden sm:flex flex-shrink-0 min-h-0">
      <div class="p-3 border-b border-[#D0D7DE] dark:border-[#30363D] flex-shrink-0">
        <el-button class="w-full cursor-pointer" @click="createNewChat" :icon="Plus">新对话</el-button>
      </div>
      <div class="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          :class="[
            'group relative p-2.5 rounded-lg cursor-pointer text-sm transition-colors duration-200',
            currentSessionId === s.session_id
              ? 'bg-[#0969DA]/10 text-[#0969DA] dark:bg-[#1F6FEB]/20 dark:text-[#58A6FF]'
              : 'hover:bg-slate-100 dark:hover:bg-[#161B22] text-slate-600 dark:text-[#8B949E]'
          ]"
        >
          <div @click="selectSession(s.session_id)" class="pr-6">
            <div class="font-medium truncate text-xs">{{ s.preview || '新对话' }}</div>
            <div class="text-[10px] opacity-60 mt-1">{{ formatTime(s.updated_at) }}</div>
          </div>
          <button
            @click.stop="confirmDeleteSession(s.session_id)"
            class="absolute right-1.5 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded cursor-pointer"
            title="删除会话"
          >
            <el-icon class="text-red-500 dark:text-red-400" size="14"><Delete /></el-icon>
          </button>
        </div>
        <div v-if="!sessions.length && !loadingSessions" class="text-center text-xs text-slate-400 dark:text-[#484F58] py-6">
          暂无历史会话
        </div>
      </div>
    </div>

    <!-- 主聊天区域 -->
    <div class="flex-1 flex flex-col min-w-0 min-h-0">
      <!-- 顶部栏 -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-[#D0D7DE] dark:border-[#30363D] flex-shrink-0">
        <div class="flex items-center gap-2">
          <!-- 移动端会话列表按钮 -->
          <el-button
            v-if="isMobile"
            type="text"
            size="small"
            class="sm:hidden cursor-pointer"
            @click="showMobileSidebar = !showMobileSidebar"
          >
            <el-icon><ChatDotRound /></el-icon>
          </el-button>
          <span class="inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span class="text-sm font-semibold text-slate-800 dark:text-[#C9D1D9]">AgentOS 安全智能体</span>
          <span class="text-xs text-slate-500 dark:text-[#8B949E] hidden sm:inline">技能驱动 · 流式对话</span>
        </div>
        <span class="text-xs text-slate-400 dark:text-[#484F58]">支持 MCP 工具</span>
      </div>

      <!-- 聊天消息区域 - flex-1 + min-h-0 确保滚动不溢出 -->
      <div
        ref="chatContainer"
        class="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 bg-gradient-to-b from-slate-50/50 to-white dark:from-[#0D1117]/50 dark:to-[#0D1117] min-h-0"
      >
        <transition-group name="msg-fade">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            :class="[
              'flex gap-3 items-start',
              msg.role === 'user' ? 'justify-end' : 'justify-start'
            ]"
          >
            <!-- AI 头像 -->
            <div
              v-if="msg.role === 'assistant'"
              class="h-8 w-8 rounded-lg bg-slate-900 dark:bg-[#1F6FEB] text-white text-xs flex items-center justify-center shadow-sm flex-shrink-0"
            >
              AI
            </div>

            <!-- 消息气泡 -->
            <div
              :class="[
                'max-w-[85%] sm:max-w-[78%] rounded-xl px-4 py-3 shadow-sm transition-all border',
                msg.role === 'user'
                  ? 'bg-[#0969DA] text-white border-[#0969DA]/40 dark:bg-[#1F6FEB] dark:border-[#1F6FEB]/40'
                  : 'bg-white dark:bg-[#161B22] text-slate-800 dark:text-[#C9D1D9] border-[#D0D7DE] dark:border-[#30363D]'
              ]"
            >
              <div
                v-if="msg.role === 'assistant'"
                class="markdown-body prose prose-sm max-w-none dark:prose-invert"
                v-html="renderMarkdown(msg.content)"
              ></div>
              <p v-else class="whitespace-pre-wrap text-sm sm:text-base break-words">{{ msg.content }}</p>
            </div>

            <!-- 用户头像 -->
            <div
              v-if="msg.role === 'user'"
              class="h-8 w-8 rounded-lg bg-[#0969DA] dark:bg-[#1F6FEB] text-white text-xs flex items-center justify-center shadow-sm flex-shrink-0"
            >
              U
            </div>
          </div>
        </transition-group>

        <!-- 加载状态 -->
        <transition name="msg-fade">
          <div v-if="loading" class="flex justify-start gap-3 items-start">
            <div class="h-8 w-8 rounded-lg bg-slate-900 dark:bg-[#1F6FEB] text-white text-xs flex items-center justify-center shadow-sm flex-shrink-0">
              AI
            </div>
            <div class="bg-white dark:bg-[#161B22] border border-[#D0D7DE] dark:border-[#30363D] shadow-sm rounded-xl px-4 py-3 text-slate-500 dark:text-[#8B949E] flex items-center gap-2">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span class="text-sm">思考中...</span>
            </div>
          </div>
        </transition>
      </div>

      <!-- 错误提示 -->
      <transition name="msg-fade">
        <el-alert
          v-if="error"
          type="error"
          :title="error"
          show-icon
          class="mx-4 mb-2 flex-shrink-0"
          closable
          @close="clearError"
        />
      </transition>

      <!-- 输入区域 -->
      <div class="border-t border-[#D0D7DE] dark:border-[#30363D] px-4 pt-3 pb-4 space-y-2 flex-shrink-0">
        <div class="flex gap-2">
          <el-input
            v-model="inputMessage"
            placeholder="描述你的安全任务或问题..."
            @keyup.enter.exact="sendMessage"
            :disabled="loading"
            :rows="1"
            type="textarea"
            autosize
            class="flex-1 chat-input"
          />
          <el-button
            type="primary"
            @click="sendMessage"
            :loading="loading"
            :disabled="!inputMessage.trim() || loading"
            class="self-end cursor-pointer"
          >
            <el-icon><Promotion /></el-icon>
          </el-button>
          <el-button
            @click="clearChat"
            :disabled="loading || messages.length === 0"
            class="self-end cursor-pointer"
          >
            清空
          </el-button>
        </div>
        <div class="text-xs text-slate-400 dark:text-[#484F58]">
          Enter 发送 · Shift+Enter 换行
        </div>
      </div>
    </div>

    <!-- 移动端会话侧边栏遮罩 -->
    <transition name="el-fade-in">
      <div
        v-if="isMobile && showMobileSidebar"
        class="fixed inset-0 bg-black/40 z-40 sm:hidden"
        @click="showMobileSidebar = false"
      />
    </transition>
    <!-- 移动端会话侧边栏 -->
    <transition name="slide-left">
      <div
        v-if="isMobile && showMobileSidebar"
        class="fixed left-0 top-0 bottom-0 w-64 bg-white dark:bg-[#0D1117] border-r border-[#D0D7DE] dark:border-[#30363D] z-50 flex flex-col sm:hidden"
      >
        <div class="p-3 border-b border-[#D0D7DE] dark:border-[#30363D] flex items-center justify-between">
          <el-button size="small" class="cursor-pointer" @click="createNewChat" :icon="Plus">新对话</el-button>
          <el-button type="text" @click="showMobileSidebar = false" class="cursor-pointer">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
        <div class="flex-1 overflow-y-auto p-2 space-y-1">
          <div
            v-for="s in sessions"
            :key="s.session_id"
            :class="[
              'group relative p-2.5 rounded-lg cursor-pointer text-sm transition-colors duration-200',
              currentSessionId === s.session_id
                ? 'bg-[#0969DA]/10 text-[#0969DA] dark:bg-[#1F6FEB]/20 dark:text-[#58A6FF]'
                : 'hover:bg-slate-100 dark:hover:bg-[#161B22] text-slate-600 dark:text-[#8B949E]'
            ]"
          >
            <div @click="selectSession(s.session_id); showMobileSidebar = false" class="pr-6">
              <div class="font-medium truncate text-xs">{{ s.preview || '新对话' }}</div>
              <div class="text-[10px] opacity-60 mt-1">{{ formatTime(s.updated_at) }}</div>
            </div>
            <button
              @click.stop="confirmDeleteSession(s.session_id)"
              class="absolute right-1.5 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded cursor-pointer"
              title="删除会话"
            >
              <el-icon class="text-red-500 dark:text-red-400" size="14"><Delete /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from "vue"
import MarkdownIt from "markdown-it"
import hljs from "highlight.js"
import { useChatApi, useChatHistory } from "../composables/useApi"
import type { ChatSession, Message } from "../types"
import { Promotion, Loading, ChatDotRound, Plus, Close, Delete } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"

// ── Markdown ──────────────────────────────────────────────────────
const md: MarkdownIt = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: (str: string, lang: string): string => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return '<pre class="hljs"><code>' +
               hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
               '</code></pre>'
      } catch {}
    }
    return '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>'
  }
})

const buildTableSeparator = (headerLine: string) => {
  const cols = headerLine.split("|").map(c => c.trim()).filter(c => c.length > 0)
  return cols.length ? `| ${cols.map(() => "---").join(" | ")} |` : ""
}

const normalizeInlineTable = (content: string) => {
  if (!content.includes("||")) return content
  const normalized = content.replace(/\|\|/g, "|\n|")
  const lines = normalized.split("\n")
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (!line || !line.trim().startsWith("|")) continue
    const nextLine = lines[i + 1] ?? ""
    if (!/^\s*\|?\s*:?[-]+:?\s*(\|\s*:?[-]+:?\s*)+\|?\s*$/.test(nextLine)) {
      const sep = buildTableSeparator(line)
      if (sep) lines.splice(i + 1, 0, sep)
    }
    break
  }
  return lines.join("\n")
}

const renderMarkdown = (content: string) => md.render(normalizeInlineTable(content))

// ── State ─────────────────────────────────────────────────────────
const inputMessage = ref("")
const WELCOME = "你好！我是 AgentOS 安全智能体，集成了威胁追踪和剧本执行技能。请告诉我你的目标或问题。"

interface ChatMessage {
  role: "user" | "assistant"
  content: string
  final?: boolean
}

const messages = ref<ChatMessage[]>([
  { role: "assistant", content: WELCOME, final: true }
])
const chatContainer = ref<HTMLElement | null>(null)
const currentSessionId = ref<string | null>(null)
const sessions = ref<ChatSession[]>([])
const showMobileSidebar = ref(false)
const isMobile = ref(false)

const { loading, error, sendMessageStream } = useChatApi()
const { loadingSessions, listSessions, getSessionHistory, deleteSession } = useChatHistory()

// ── Helpers ───────────────────────────────────────────────────────
const scrollToBottom = async () => {
  await nextTick()
  chatContainer.value?.scrollTo({ top: chatContainer.value.scrollHeight, behavior: 'smooth' })
}

const formatTime = (ts: number) => {
  if (!ts) return ""
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
  })
}

const generateSessionId = () => crypto.randomUUID()

// ── Sessions ──────────────────────────────────────────────────────
const loadSessionList = async () => {
  try {
    sessions.value = await listSessions()
  } catch {
    // ignore
  }
}

const selectSession = async (sessionId: string) => {
  currentSessionId.value = sessionId
  try {
    const history: Message[] = await getSessionHistory(sessionId)
    if (history.length > 0) {
      messages.value = history.map(m => ({ ...m, final: true }))
    } else {
      messages.value = [{ role: "assistant", content: WELCOME, final: true }]
    }
  } catch {
    messages.value = [{ role: "assistant", content: WELCOME, final: true }]
  }
  scrollToBottom()
}

const createNewChat = () => {
  currentSessionId.value = null
  messages.value = [{ role: "assistant", content: WELCOME, final: true }]
}

const confirmDeleteSession = async (sessionId: string) => {
  try {
    await ElMessageBox.confirm('确定要删除这个对话吗？', '警告', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteSession(sessionId)
    if (currentSessionId.value === sessionId) {
      createNewChat()
    }
    await loadSessionList()
    ElMessage.success('已删除')
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// ── Chat ──────────────────────────────────────────────────────────
const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) return
  const userMsg = inputMessage.value
  messages.value.push({ role: "user", content: userMsg })
  inputMessage.value = ""
  scrollToBottom()

  // 如果没有 session_id，生成一个新的
  if (!currentSessionId.value) {
    currentSessionId.value = generateSessionId()
  }

  try {
    const idx = messages.value.push({ role: "assistant", content: "", final: false }) - 1

    await sendMessageStream(userMsg, currentSessionId.value, (chunk) => {
      const m = messages.value[idx]
      if (m) m.content += chunk
      scrollToBottom()
    })

    const m = messages.value[idx]
    if (m) m.final = true

    // 刷新会话列表
    await loadSessionList()
  } catch {
    messages.value.push({ role: "assistant", content: "抱歉，处理请求时遇到错误。请稍后再试。" })
  } finally {
    scrollToBottom()
  }
}

const clearChat = () => {
  messages.value = []
  inputMessage.value = ""
}

const clearError = () => { if (error.value) error.value = null }

// ── Lifecycle ─────────────────────────────────────────────────────
const checkMobile = () => { isMobile.value = window.innerWidth < 640 }

onMounted(async () => {
  checkMobile()
  window.addEventListener("resize", checkMobile)
  await loadSessionList()
  scrollToBottom()
})

onUnmounted(() => { window.removeEventListener("resize", checkMobile) })
</script>

<style scoped>
/* 过渡动画 */
.msg-fade-enter-active,
.msg-fade-leave-active { transition: all 0.3s ease; }
.msg-fade-enter-from { opacity: 0; transform: translateY(8px); }
.msg-fade-leave-to { opacity: 0; }

.slide-left-enter-active,
.slide-left-leave-active { transition: transform 0.3s ease; }
.slide-left-enter-from,
.slide-left-leave-to { transform: translateX(-100%); }

/* 输入框 */
.chat-input :deep(.el-textarea__inner) {
  background: transparent;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  resize: none;
  font-size: 14px;
}

/* 滚动条 */
.overflow-y-auto {
  scrollbar-width: thin;
  scrollbar-color: rgba(156, 163, 175, 0.4) transparent;
}
.overflow-y-auto::-webkit-scrollbar { width: 6px; }
.overflow-y-auto::-webkit-scrollbar-track { background: transparent; }
.overflow-y-auto::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.4);
  border-radius: 3px;
}

/* Markdown 内容 */
.markdown-body { color: inherit; line-height: 1.6; }
.markdown-body :deep(p) { margin: 0.5em 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0.5em 0; padding-left: 1.5em; }

.markdown-body :deep(code) {
  background: rgba(148, 163, 184, 0.15);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'Courier New', monospace;
}
html.dark .markdown-body :deep(code) { background: rgba(110, 118, 129, 0.2); }

.markdown-body :deep(pre) {
  background: rgba(15, 23, 42, 0.95);
  color: #e2e8f0;
  padding: 1em;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0.8em 0;
}
.markdown-body :deep(pre code) { background: none; padding: 0; color: inherit; }

/* 表格 */
.markdown-body :deep(table) {
  width: 100%; border-collapse: collapse; margin: 1em 0;
  font-size: 0.9em; overflow-x: auto; display: block;
}
.markdown-body :deep(thead),
.markdown-body :deep(tbody) { display: table; width: 100%; table-layout: fixed; }
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid rgba(148, 163, 184, 0.25);
  padding: 0.6em 0.8em; text-align: left;
}
.markdown-body :deep(th) {
  background: rgba(241, 245, 249, 0.95); font-weight: 600; color: rgba(51, 65, 85, 1);
}
html.dark .markdown-body :deep(th) { background: rgba(22, 27, 34, 0.95); color: rgba(201, 209, 217, 1); }
.markdown-body :deep(tbody tr:nth-child(even)) { background: rgba(248, 250, 252, 0.4); }
html.dark .markdown-body :deep(tbody tr:nth-child(even)) { background: rgba(22, 27, 34, 0.3); }
.markdown-body :deep(tbody tr:hover) { background: rgba(241, 245, 249, 0.6); }
html.dark .markdown-body :deep(tbody tr:hover) { background: rgba(22, 27, 34, 0.5); }

.markdown-body :deep(blockquote) {
  border-left: 4px solid rgba(148, 163, 184, 0.4);
  padding-left: 1em; margin: 0.8em 0; color: rgba(100, 116, 139, 1);
}
html.dark .markdown-body :deep(blockquote) { color: rgba(139, 148, 158, 1); }

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) { margin: 1em 0 0.5em; font-weight: 600; line-height: 1.3; }
.markdown-body :deep(h1) { font-size: 1.5em; }
.markdown-body :deep(h2) { font-size: 1.3em; }
.markdown-body :deep(h3) { font-size: 1.1em; }
</style>
