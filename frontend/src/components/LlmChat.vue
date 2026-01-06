<template>
  <div class="flex flex-col h-[500px] sm:h-[600px]">
    <!-- 聊天消息区域 -->
    <div
      ref="chatContainer"
      class="flex-1 overflow-y-auto p-3 sm:p-4 space-y-3 sm:space-y-4 border rounded-lg bg-gray-50 mb-4"
    >
      <transition-group name="el-fade-in">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
        >
          <div
            :class="[
              'max-w-[85%] sm:max-w-[80%] rounded-lg p-3 shadow-sm transition-all',
              msg.role === 'user'
                ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white'
                : 'bg-white border text-gray-800'
            ]"
          >
            <p class="whitespace-pre-wrap text-sm sm:text-base break-words">{{ msg.content }}</p>
            <div
              v-if="msg.sources && msg.sources.length"
              class="mt-2 pt-2 border-t border-gray-200/50 text-xs"
            >
              <p class="font-semibold mb-1 opacity-90">来源:</p>
              <ul class="list-disc list-inside space-y-1">
                <li v-for="(source, idx) in msg.sources" :key="idx" class="truncate">
                  <a
                    :href="source"
                    target="_blank"
                    rel="noopener noreferrer"
                    :class="[
                      'hover:underline',
                      msg.role === 'user' ? 'text-blue-100' : 'text-blue-600 hover:text-blue-800'
                    ]"
                  >
                    {{ source }}
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </transition-group>

      <!-- 加载状态 -->
      <transition name="el-fade-in">
        <div v-if="loading" class="flex justify-start">
          <div class="bg-white border shadow-sm rounded-lg p-3 text-gray-500 flex items-center gap-2">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span class="text-sm">思考中...</span>
          </div>
        </div>
      </transition>
    </div>

    <!-- 输入区域 -->
    <div class="flex gap-2">
      <el-input
        v-model="inputMessage"
        placeholder="请输入 CVE 或安全相关问题..."
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from "vue"
import { useChatApi } from "../composables/useApi"
import { Promotion, Loading } from "@element-plus/icons-vue"
import type { Message } from "../types"

// 查询状态
const inputMessage = ref("")
const messages = ref<Message[]>([
  {
    role: "assistant",
    content: "你好！我可以帮助你查找 CVE 和安全威胁相关信息。请问有什么需要帮助的吗？"
  }
])
const chatContainer = ref<HTMLElement | null>(null)

// API hooks
const { loading, sendMessage: apiSendMessage } = useChatApi()

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
    const response = await apiSendMessage(userMsg)

    messages.value.push({
      role: "assistant",
      content: response.response,
      sources: response.sources
    })
  } catch (error) {
    messages.value.push({
      role: "assistant",
      content: "抱歉，处理你的请求时遇到错误。请稍后再试。"
    })
  } finally {
    scrollToBottom()
  }
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
