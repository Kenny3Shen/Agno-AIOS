<template>
  <div class="flex flex-col h-[500px]">
    <div class="flex-1 overflow-y-auto p-4 space-y-4 border rounded-lg bg-gray-50 mb-4" ref="chatContainer">
      <div v-for="(msg, index) in messages" :key="index" 
           :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']">
        <div :class="['max-w-[80%] rounded-lg p-3', 
                      msg.role === 'user' ? 'bg-blue-500 text-white' : 'bg-white border shadow-sm text-gray-800']">
          <p class="whitespace-pre-wrap">{{ msg.content }}</p>
          <div v-if="msg.sources && msg.sources.length" class="mt-2 pt-2 border-t border-gray-200 text-xs">
            <p class="font-semibold mb-1">来源:</p>
            <ul class="list-disc list-inside">
              <li v-for="(source, idx) in msg.sources" :key="idx" class="truncate">
                <a :href="source" target="_blank" class="text-blue-400 hover:underline">{{ source }}</a>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div v-if="loading" class="flex justify-start">
        <div class="bg-white border shadow-sm rounded-lg p-3 text-gray-500">
          思考中...
        </div>
      </div>
    </div>

    <div class="flex gap-2">
      <el-input
        v-model="inputMessage"
        placeholder="请输入 CVE 或安全相关问题..."
        @keyup.enter="sendMessage"
        :disabled="loading"
      />
      <el-button type="primary" @click="sendMessage" :loading="loading">发送</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from "vue"
import axios from "axios"
import { ElMessage } from "element-plus"

interface Message {
  role: "user" | "assistant"
  content: string
  sources?: string[]
}

const inputMessage = ref("")
const messages = ref<Message[]>([
  { role: "assistant", content: "你好！我可以帮助你查找 CVE 和安全威胁相关信息。请问有什么需要帮助的吗？" }
])
const loading = ref(false)
const chatContainer = ref<HTMLElement | null>(null)

const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) return

  const userMsg = inputMessage.value
  messages.value.push({ role: "user", content: userMsg })
  inputMessage.value = ""
  loading.value = true
  scrollToBottom()

  try {
    const response = await axios.post("/api/chat", {
      message: userMsg
    })
    
    messages.value.push({
      role: "assistant",
      content: response.data.response,
      sources: response.data.sources
    })
  } catch (error) {
    console.error(error)
    ElMessage.error("获取响应失败")
    messages.value.push({
      role: "assistant",
      content: "抱歉，处理你的请求时遇到错误。"
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}
</script>
