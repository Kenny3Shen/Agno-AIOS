<template>
  <div class="flex flex-col h-[520px] sm:h-[640px] rounded-2xl border bg-white/80 shadow-sm backdrop-blur">
    <div class="flex items-center justify-between px-4 py-3 border-b bg-white/70 rounded-t-2xl">
      <div class="flex items-center gap-2">
        <span class="inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
        <div class="text-sm font-semibold text-slate-800">AgentOS 安全双Agent</div>
        <div class="text-xs text-slate-500">任务编排 + 剧本执行（流式 Markdown）</div>
      </div>
      <div class="text-xs text-slate-400">支持 MCP 工具</div>
    </div>
    <!-- 聊天消息区域 -->
    <div
      ref="chatContainer"
      class="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 bg-gradient-to-b from-slate-50 to-white"
    >
      <transition-group name="el-fade-in">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="[
            'flex gap-3 items-start',
            msg.role === 'user' ? 'justify-end' : 'justify-start'
          ]"
        >
          <div
            v-if="msg.role === 'assistant'"
            class="h-8 w-8 rounded-full bg-slate-900 text-white text-xs flex items-center justify-center shadow-sm"
          >
            AI
          </div>
          <div
            :class="[
              'max-w-[85%] sm:max-w-[78%] rounded-xl px-4 py-3 shadow-sm transition-all border',
              msg.role === 'user'
                ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white border-blue-400/40'
                : 'bg-white text-slate-800 border-slate-200'
            ]"
          >
            <div
              v-if="msg.role === 'assistant'"
              class="markdown-body prose prose-sm max-w-none"
              v-html="renderMarkdown(msg.content)"
            ></div>
            <p v-else class="whitespace-pre-wrap text-sm sm:text-base break-words">{{ msg.content }}</p>
          </div>
          <div
            v-if="msg.role === 'user'"
            class="h-8 w-8 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center shadow-sm"
          >
            你
          </div>
        </div>
      </transition-group>

      <!-- 加载状态 -->
      <transition name="el-fade-in">
        <div v-if="loading" class="flex justify-start">
          <div class="bg-white border shadow-sm rounded-lg px-3 py-2 text-gray-500 flex items-center gap-2">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span class="text-sm">思考中...</span>
          </div>
        </div>
      </transition>
    </div>

    <!-- 错误提示 -->
    <transition name="el-fade-in">
      <el-alert
        v-if="error"
        type="error"
        :title="error"
        show-icon
        class="mb-3"
        closable
        @close="clearError"
      />
    </transition>

    <!-- 输入区域 -->
    <div class="flex gap-2 px-4 pb-4">
      <el-input
        v-model="inputMessage"
        placeholder="描述你的安全任务或问题（双Agent协作）..."
        @keyup.enter="sendMessage"
        :disabled="loading"
        :rows="1"
        type="textarea"
        autosize
        class="flex-1"
      />
      <el-button
        type="primary"
        @click="sendMessage"
        :loading="loading"
        :disabled="!inputMessage.trim() || loading"
        class="self-end"
      >
        <el-icon><Promotion /></el-icon>
      </el-button>
      <el-button
        @click="clearChat"
        :disabled="loading || messages.length === 0"
        class="self-end"
      >
        清空
      </el-button>
    </div>
    <div class="text-xs text-gray-400 px-4 pb-4">提示：Enter 发送，Shift+Enter 换行｜可先让编排Agent出计划</div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from "vue"
import MarkdownIt from "markdown-it"
import hljs from "highlight.js"
import { useChatApi } from "../composables/useApi"
import { Promotion, Loading } from "@element-plus/icons-vue"

// 配置 markdown-it，默认支持表格
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

// 查询状态
const inputMessage = ref("")
const initialContent = "你好！我是 AgentOS 安全双Agent：任务编排Agent负责拆解与规划，剧本执行Agent负责调用技能与工具执行。请告诉我你的目标或问题。"

interface ChatMessage {
  role: "user" | "assistant"
  content: string
  final?: boolean
}

const messages = ref<ChatMessage[]>([
  {
    role: "assistant",
    content: initialContent,
    final: true
  }
])
const chatContainer = ref<HTMLElement | null>(null)

// API hooks
const { loading, error, sendMessageStream } = useChatApi()

// 自动滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior: 'smooth'
    })
  }
}

const buildTableSeparator = (headerLine: string) => {
  const cols = headerLine
    .split("|")
    .map((cell) => cell.trim())
    .filter((cell) => cell.length > 0)
  if (cols.length === 0) return ""
  return `| ${cols.map(() => "---").join(" | ")} |`
}

const normalizeInlineTable = (content: string) => {
  if (!content.includes("||")) return content

  const normalized = content.replace(/\|\|/g, "|\n|")
  const lines = normalized.split("\n")
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line) {
      i += 1
      continue
    }
    if (line.trim().startsWith("|")) {
      const headerLine = line
      const nextLine = lines[i + 1] ?? ""
      const hasSeparator = /^\s*\|?\s*:?[-]+:?\s*(\|\s*:?[-]+:?\s*)+\|?\s*$/.test(nextLine)
      if (!hasSeparator) {
        const separator = buildTableSeparator(headerLine)
        if (separator) {
          lines.splice(i + 1, 0, separator)
        }
      }
      break
    }
    i += 1
  }
  return lines.join("\n")
}

// 渲染 Markdown 为 HTML
const renderMarkdown = (content: string) => {
  return md.render(normalizeInlineTable(content))
}

// 发送消息
const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) return

  const userMsg = inputMessage.value
  messages.value.push({ role: "user", content: userMsg })
  inputMessage.value = ""
  scrollToBottom()

  try {
    const assistantIndex = messages.value.push({
      role: "assistant",
      content: "",
      final: false
    }) - 1
    
    await sendMessageStream(userMsg, (chunk) => {
      const assistant = messages.value[assistantIndex]
      if (assistant) {
        assistant.content += chunk
      }
      scrollToBottom()
    })
    
    const assistant = messages.value[assistantIndex]
    if (assistant) {
      assistant.final = true
    }
  } catch (err) {
    messages.value.push({
      role: "assistant",
      content: "抱歉，处理你的请求时遇到错误。请稍后再试。"
    })
  } finally {
    scrollToBottom()
  }
}

const clearChat = () => {
  messages.value = []
  inputMessage.value = ""
}

const clearError = () => {
  if (error.value) error.value = null
}

// 初始化时滚动到底部
onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
/* 响应式优化 */
@media (max-width: 640px) {
  :deep(.el-textarea__inner) {
    font-size: 14px;
  }
}

/* 过渡动画 */
.message-enter-active,
.message-leave-active {
  transition: all 0.3s ease;
}

.message-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

/* 滚动条美化 */
:deep(.overflow-y-auto) {
  scrollbar-width: thin;
  scrollbar-color: rgba(156, 163, 175, 0.5) transparent;
}

:deep(.overflow-y-auto::-webkit-scrollbar) {
  width: 6px;
}

:deep(.overflow-y-auto::-webkit-scrollbar-track) {
  background: transparent;
}

:deep(.overflow-y-auto::-webkit-scrollbar-thumb) {
  background-color: rgba(156, 163, 175, 0.5);
  border-radius: 3px;
}

:deep(.overflow-y-auto::-webkit-scrollbar-thumb:hover) {
  background-color: rgba(156, 163, 175, 0.7);
}

/* Markdown 内容样式 */
.markdown-body {
  color: inherit;
  line-height: 1.6;
}

.markdown-body :deep(p) {
  margin: 0.5em 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.5em;
}

.markdown-body :deep(code) {
  background: rgba(148, 163, 184, 0.1);
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-size: 0.9em;
  font-family: 'Courier New', monospace;
}

.markdown-body :deep(pre) {
  background: rgba(15, 23, 42, 0.95);
  color: #e2e8f0;
  padding: 1em;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.8em 0;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

/* 表格样式 */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
  font-size: 0.9em;
  overflow-x: auto;
  display: block;
}

.markdown-body :deep(thead) {
  display: table;
  width: 100%;
  table-layout: fixed;
}

.markdown-body :deep(tbody) {
  display: table;
  width: 100%;
  table-layout: fixed;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid rgba(148, 163, 184, 0.3);
  padding: 0.6em 0.8em;
  text-align: left;
}

.markdown-body :deep(th) {
  background: rgba(241, 245, 249, 0.95);
  font-weight: 600;
  color: rgba(51, 65, 85, 1);
}

.markdown-body :deep(tbody tr:nth-child(even)) {
  background: rgba(248, 250, 252, 0.5);
}

.markdown-body :deep(tbody tr:hover) {
  background: rgba(241, 245, 249, 0.7);
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid rgba(148, 163, 184, 0.4);
  padding-left: 1em;
  margin: 0.8em 0;
  color: rgba(100, 116, 139, 1);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 1em 0 0.5em;
  font-weight: 600;
  line-height: 1.3;
}

.markdown-body :deep(h1) { font-size: 1.5em; }
.markdown-body :deep(h2) { font-size: 1.3em; }
.markdown-body :deep(h3) { font-size: 1.1em; }
</style>
