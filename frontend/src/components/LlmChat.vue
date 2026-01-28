<template>
  <div class="flex flex-col h-[520px] sm:h-[640px] rounded-2xl border bg-white/80 shadow-sm backdrop-blur">
    <div class="flex items-center justify-between px-4 py-3 border-b bg-white/70 rounded-t-2xl">
      <div class="flex items-center gap-2">
        <span class="inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
        <div class="text-sm font-semibold text-slate-800">安全助手</div>
        <div class="text-xs text-slate-500">实时流式 Markdown</div>
      </div>
      <div class="text-xs text-slate-400">可调用 MCP 工具</div>
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
            <MarkdownRender
              v-if="msg.role === 'assistant'"
              custom-id="chat"
              :nodes="msg.nodes"
              :final="msg.final"
              :max-live-nodes="0"
              :batch-rendering="true"
              :render-batch-size="16"
              :render-batch-delay="8"
              :render-code-blocks-as-pre="true"
            />
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
        placeholder="输入 CVE 编号或安全问题（支持关键字与工具检索）..."
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
    <div class="text-xs text-gray-400 px-4 pb-4">提示：Enter 发送，Shift+Enter 换行</div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from "vue"
import MarkdownRender, { getMarkdown, parseMarkdownToStructure } from "markstream-vue"
import { useChatApi } from "../composables/useApi"
import { Promotion, Loading } from "@element-plus/icons-vue"
import type { Message } from "../types"

const md = getMarkdown()

// 查询状态
const inputMessage = ref("")
const initialContent = "你好！我可以帮助你查找 CVE 和安全威胁相关信息。请问有什么需要帮助的吗？"
const messages = ref<Message[]>([
  {
    role: "assistant",
    content: initialContent,
    nodes: parseMarkdownToStructure(initialContent, md),
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
      nodes: [],
      final: false
    }) - 1
    await sendMessageStream(userMsg, (chunk) => {
      const assistant = messages.value[assistantIndex]
      if (assistant) {
        assistant.content += chunk
        assistant.nodes = parseMarkdownToStructure(assistant.content, md)
      }
      scrollToBottom()
    })
    const assistant = messages.value[assistantIndex]
    if (assistant) {
      assistant.final = true
      assistant.nodes = parseMarkdownToStructure(assistant.content, md)
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
</style>
