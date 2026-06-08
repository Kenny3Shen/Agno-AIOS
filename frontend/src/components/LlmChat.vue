<template>
  <div class="agent-chat h-full min-h-0 overflow-hidden bg-[#F7FAFC] text-[#15202B] dark:bg-[#071014] dark:text-[#DCE7EF]">
    <div class="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[236px_minmax(0,1fr)]">
      <aside class="hidden min-h-0 border-r border-[#CBD6E2] bg-[#F1F5F9] lg:flex lg:flex-col dark:border-[#22313A] dark:bg-[#0A151B]">
        <div class="border-b border-[#CBD6E2] p-3 dark:border-[#22313A]">
          <el-button type="primary" class="!w-full cursor-pointer" @click="createNewChat" :icon="Plus">
            新建对话
          </el-button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-2">
          <div class="mb-2 flex items-center justify-between px-2 text-[11px] font-semibold uppercase tracking-wide text-[#526170] dark:text-[#758998]">
            <span>Sessions</span>
            <span class="font-mono">{{ sessions.length }}</span>
          </div>
          <button
            v-for="s in sessions"
            :key="s.session_id"
            type="button"
            :class="[
              'group mb-1 flex w-full cursor-pointer items-start gap-2 rounded-lg border p-2 text-left transition-colors duration-200',
              currentSessionId === s.session_id
                ? 'border-[#2F8FED]/50 bg-[#EAF5FF] text-[#0F4F8F] dark:bg-[#102638] dark:text-[#8BD9FF]'
                : 'border-transparent text-[#334155] hover:border-[#B8C8D8] hover:bg-white dark:text-[#91A4B3] dark:hover:border-[#22313A] dark:hover:bg-[#101C23]',
            ]"
            @click="selectSession(s.session_id)"
          >
            <span class="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md border border-[#D8E0E7] bg-white dark:border-[#22313A] dark:bg-[#071014]">
              <el-icon size="14"><ChatDotRound /></el-icon>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-xs font-semibold">{{ s.preview || '新对话' }}</span>
              <span class="mt-1 block truncate font-mono text-[10px] opacity-70">{{ formatTime(s.updated_at) }}</span>
            </span>
            <span class="flex shrink-0 gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
              <button
                type="button"
                class="grid h-6 w-6 cursor-pointer place-items-center rounded hover:bg-black/5 dark:hover:bg-white/10"
                title="复制 session_id"
                @click.stop="copySessionId(s.session_id)"
              >
                <el-icon size="13"><CopyDocument /></el-icon>
              </button>
              <button
                type="button"
                class="grid h-6 w-6 cursor-pointer place-items-center rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                title="删除会话"
                @click.stop="confirmDeleteSession(s.session_id)"
              >
                <el-icon size="13"><Delete /></el-icon>
              </button>
            </span>
          </button>
          <div v-if="!sessions.length && !loadingSessions" class="rounded-lg border border-dashed border-[#D8E0E7] p-6 text-center text-xs text-[#6B7C8A] dark:border-[#22313A] dark:text-[#758998]">
            暂无历史会话
          </div>
        </div>
      </aside>

      <main class="flex min-h-0 min-w-0 flex-col">
        <header class="border-b border-[#CBD6E2] bg-white px-4 py-3 dark:border-[#22313A] dark:bg-[#0A151B]">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex min-w-0 items-center gap-2.5">
              <el-button
                v-if="isMobile"
                type="primary"
                plain
                size="small"
                class="lg:hidden cursor-pointer"
                @click="showMobileSidebar = !showMobileSidebar"
              >
                <el-icon><ChatDotRound /></el-icon>
              </el-button>
              <div class="agent-core" :class="{ 'is-running': loading }">
                <el-icon><Cpu /></el-icon>
              </div>
              <div class="min-w-0">
                <h3 class="truncate text-sm font-semibold text-[#15202B] dark:text-white">Agent 对话</h3>
                <p class="mt-1 truncate text-xs text-[#6B7C8A] dark:text-[#91A4B3]">
                  {{ loading ? '执行中' : '待命' }} · {{ currentModelName }} · {{ compactSessionId }}
                </p>
              </div>
            </div>

            <div class="hidden items-center gap-2 rounded-md border border-[#CBD6E2] bg-[#F8FAFC] px-2.5 py-1.5 text-xs text-[#526170] dark:border-[#22313A] dark:bg-[#0F1B22] dark:text-[#91A4B3] sm:flex">
              <span class="h-1.5 w-1.5 rounded-full" :class="selectedModelReady ? 'bg-[#22C55E]' : 'bg-[#F6C343]'" />
              <span class="max-w-[180px] truncate">{{ currentModelName }}</span>
            </div>
          </div>
        </header>

        <div
          ref="chatContainer"
          class="agent-stream min-h-0 flex-1 overflow-y-auto p-4"
        >
          <transition-group name="msg-fade">
            <div
              v-for="(msg, index) in messages"
              :key="index"
              :class="[
                'message-row',
                msg.role === 'user' ? 'is-user' : 'is-agent',
              ]"
            >
              <div class="message-rail">
                <div :class="['message-avatar', msg.role === 'user' ? 'user' : 'agent']">
                  <el-icon v-if="msg.role === 'assistant'"><Cpu /></el-icon>
                  <span v-else>U</span>
                </div>
                <span v-if="msg.role === 'assistant'" class="rail-line" />
              </div>

              <article :class="['message-card', msg.role === 'user' ? 'user' : 'agent']">
                <div class="mb-2 flex items-center justify-between gap-3">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold">
                      {{ msg.role === 'user' ? 'Operator' : 'Security Agent' }}
                    </span>
                    <span v-if="msg.role === 'assistant' && !msg.final" class="agent-pill">Streaming</span>
                  </div>
                  <span class="font-mono text-[10px] text-[#7D8D9A]">#{{ index + 1 }}</span>
                </div>
                <div
                  v-if="msg.role === 'assistant'"
                  class="markdown-body prose prose-sm max-w-none dark:prose-invert"
                  v-html="renderMarkdown(msg.content)"
                ></div>
                <p v-else class="whitespace-pre-wrap break-words text-sm leading-relaxed">{{ msg.content }}</p>
              </article>
            </div>
          </transition-group>

          <transition name="msg-fade">
            <div v-if="loading" class="message-row is-agent">
              <div class="message-rail">
                <div class="message-avatar agent">
                  <el-icon class="is-loading"><Loading /></el-icon>
                </div>
              </div>
              <article class="message-card agent">
                <div class="flex items-center gap-2 text-sm font-semibold">
                  <span class="agent-pulse" />
                  Agent 正在规划下一步
                </div>
              </article>
            </div>
          </transition>
        </div>

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

        <footer class="border-t border-[#D8E0E7] bg-white/95 p-3 dark:border-[#22313A] dark:bg-[#0A151B]">
          <div v-if="showQuickPrompts" class="mb-2 flex flex-wrap gap-2">
            <button
              v-for="prompt in quickPrompts"
              :key="prompt"
              type="button"
              class="cursor-pointer rounded-md border border-[#D8E0E7] px-2.5 py-1.5 text-xs text-[#526170] transition-colors duration-200 hover:border-[#2F8FED]/50 hover:bg-[#EAF5FF] hover:text-[#0F4F8F] dark:border-[#22313A] dark:text-[#91A4B3] dark:hover:bg-[#102638] dark:hover:text-[#8BD9FF]"
              @click="inputMessage = prompt"
            >
              {{ prompt }}
            </button>
          </div>
          <div
            v-if="modelConfigNotice"
            class="mb-2 rounded-md border border-[#F6C343]/50 bg-[#FFF8E1] px-3 py-2 text-xs text-[#7A5200] dark:bg-[#2A2413] dark:text-[#FFD166]"
          >
            {{ modelConfigNotice }}
          </div>
          <div class="chat-composer">
            <el-input
              v-model="inputMessage"
              placeholder="描述目标，例如：分析这个 CVE 对我资产面的影响"
              @keyup.enter.exact="sendMessage"
              :disabled="loading"
              :autosize="{ minRows: 1, maxRows: 6 }"
              type="textarea"
              class="chat-input"
            />
            <div class="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <el-select
                v-model="selectedModelId"
                :loading="modelLoading"
                placeholder="选择模型"
                class="agent-model-select"
                popper-class="agent-model-select-popper"
                placement="top-start"
                @change="persistSelectedModel"
              >
                <el-option
                  v-for="model in modelOptions"
                  :key="model.id"
                  :label="model.name"
                  :value="model.id"
                  :disabled="!model.enabled"
                >
                  <div class="model-option">
                    <span class="min-w-0">
                      <span class="model-option-title">{{ model.name }}</span>
                      <span class="model-option-subtitle">
                        {{ model.model_id || '未填写模型 ID' }}
                      </span>
                    </span>
                    <span
                      class="model-option-status"
                      :class="model.configured
                        ? 'is-ready'
                        : 'is-pending'"
                    >
                      {{ model.configured ? 'Ready' : 'Config' }}
                    </span>
                  </div>
                </el-option>
              </el-select>
              <el-tooltip content="发送任务" placement="top">
                <el-button
                  type="primary"
                  @click="sendMessage"
                  :loading="loading"
                  :disabled="!inputMessage.trim() || loading || !selectedModelReady"
                  class="send-button cursor-pointer"
                >
                  <el-icon><Promotion /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </div>
        </footer>
      </main>
    </div>

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
        class="fixed bottom-0 left-0 top-0 z-50 flex w-72 flex-col border-r border-[#D8E0E7] bg-white dark:border-[#22313A] dark:bg-[#0A151B] lg:hidden"
      >
        <div class="flex items-center justify-between border-b border-[#D8E0E7] p-3 dark:border-[#22313A]">
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
              @click.stop="copySessionId(s.session_id)"
              class="absolute right-7 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 p-1 hover:bg-slate-100 dark:hover:bg-[#21262D] rounded cursor-pointer"
              title="复制 session_id"
            >
              <el-icon class="text-slate-600 dark:text-[#8B949E]" size="14"><CopyDocument /></el-icon>
            </button>
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
import { computed, ref, nextTick, onMounted, onUnmounted } from "vue"
import MarkdownIt from "markdown-it"
import hljs from "highlight.js"
import { useChatApi, useChatHistory, useSettingsApi } from "../composables/useApi"
import type { ChatSession, Message, ModelConfig } from "../types"
import {
  ChatDotRound,
  Close,
  CopyDocument,
  Cpu,
  Delete,
  Loading,
  Plus,
  Promotion,
} from "@element-plus/icons-vue"
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
const MODEL_STORAGE_KEY = "agno-aios-chat-model-id"

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
const modelLoading = ref(false)
const modelOptions = ref<ModelConfig[]>([])
const selectedModelId = ref<string | null>(null)

const { loading, error, sendMessageStream } = useChatApi()
const { loadingSessions, listSessions, getSessionHistory, deleteSession } = useChatHistory()
const { fetchModels } = useSettingsApi()

const compactSessionId = computed(() => {
  if (!currentSessionId.value) return "New task"
  return `${currentSessionId.value.slice(0, 8)}...${currentSessionId.value.slice(-4)}`
})

const selectedModel = computed(() => {
  return modelOptions.value.find((model) => model.id === selectedModelId.value)
    ?? modelOptions.value.find((model) => model.enabled)
    ?? null
})

const selectedModelReady = computed(() => Boolean(selectedModel.value?.enabled && selectedModel.value.configured))
const currentModelName = computed(() => selectedModel.value?.name ?? "未选择")
const modelConfigNotice = computed(() => {
  if (modelLoading.value) return ""
  if (!modelOptions.value.length) return "未加载到模型配置，请先在系统配置中添加模型。"
  if (!selectedModel.value) return "请选择一个可用模型。"
  if (!selectedModel.value.enabled) return `当前模型 ${selectedModel.value.name} 已禁用，请切换模型。`
  if (!selectedModel.value.configured) return `当前模型 ${selectedModel.value.name} 未完成参数配置，请在系统配置中补全 API Key、Base URL 和 Model ID。`
  return ""
})

const quickPrompts = [
  "帮我评估 CVE 对当前资产的影响",
  "生成一次外部暴露面排查计划",
  "把这段告警整理成处置步骤",
]

const showQuickPrompts = computed(() => messages.value.length <= 1 && !loading.value)

const persistSelectedModel = () => {
  if (selectedModelId.value) {
    localStorage.setItem(MODEL_STORAGE_KEY, selectedModelId.value)
  }
}

const loadModels = async () => {
  modelLoading.value = true
  try {
    const config = await fetchModels()
    modelOptions.value = config.models
    const savedId = localStorage.getItem(MODEL_STORAGE_KEY)
    const enabledIds = new Set(config.models.filter((model) => model.enabled).map((model) => model.id))
    if (savedId && enabledIds.has(savedId)) {
      selectedModelId.value = savedId
    } else if (enabledIds.has(config.active_model_id)) {
      selectedModelId.value = config.active_model_id
    } else {
      selectedModelId.value = config.models.find((model) => model.enabled)?.id ?? config.models[0]?.id ?? null
    }
    persistSelectedModel()
  } catch {
    ElMessage.warning("模型配置加载失败")
  } finally {
    modelLoading.value = false
  }
}

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

const copySessionId = async (sessionId: string) => {
  try {
    await navigator.clipboard.writeText(sessionId)
    ElMessage.success("session_id 已复制")
  } catch {
    ElMessage.warning("复制失败（请检查浏览器权限）")
  }
}

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
  } catch (err: unknown) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// ── Chat ──────────────────────────────────────────────────────────
const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) return
  if (!selectedModelReady.value) {
    ElMessage.warning(modelConfigNotice.value || "模型不可用")
    return
  }
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

    await sendMessageStream(userMsg, currentSessionId.value, selectedModelId.value, (chunk) => {
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

const clearError = () => { if (error.value) error.value = null }

// ── Lifecycle ─────────────────────────────────────────────────────
const checkMobile = () => { isMobile.value = window.innerWidth < 640 }

onMounted(async () => {
  checkMobile()
  window.addEventListener("resize", checkMobile)
  await Promise.all([loadSessionList(), loadModels()])
  scrollToBottom()
})

onUnmounted(() => { window.removeEventListener("resize", checkMobile) })
</script>

<style>
.agent-chat {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.agent-core {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(47, 143, 237, 0.35);
  border-radius: 8px;
  background: #eaf5ff;
  color: #0969da;
}

.agent-core.is-running {
  animation: agent-glow 1.4s ease-in-out infinite;
}

.agent-pill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  border: 1px solid rgba(84, 211, 138, 0.35);
  border-radius: 999px;
  padding: 0 8px;
  background: rgba(84, 211, 138, 0.1);
  color: #14824a;
  font-size: 10px;
  font-weight: 700;
}

.agent-stream {
  background: #f7fafc;
}

.message-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}

.message-row.is-user {
  grid-template-columns: minmax(0, 1fr) 34px;
}

.message-row.is-user .message-rail {
  grid-column: 2;
  grid-row: 1;
}

.message-row.is-user .message-card {
  grid-column: 1;
  grid-row: 1;
  justify-self: end;
}

.message-rail {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  position: relative;
}

.rail-line {
  position: absolute;
  top: 38px;
  bottom: -18px;
  width: 1px;
  background: #cbd6e2;
}

.message-avatar {
  z-index: 1;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.message-avatar.agent {
  border: 1px solid rgba(47, 143, 237, 0.35);
  background: #eaf5ff;
  color: #0969da;
}

.message-avatar.user {
  background: #15202b;
  color: #ffffff;
}

.message-card {
  max-width: min(860px, 100%);
  border: 1px solid #cbd6e2;
  border-radius: 8px;
  padding: 12px 14px;
}

.message-card.agent {
  background: #ffffff;
}

.message-card.user {
  width: min(720px, 100%);
  background: #15202b;
  color: #ffffff;
}

.agent-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #54d38a;
  box-shadow: 0 0 0 6px rgba(84, 211, 138, 0.15);
}

/* 过渡动画 */
.msg-fade-enter-active,
.msg-fade-leave-active { transition: all 0.3s ease; }
.msg-fade-enter-from { opacity: 0; transform: translateY(8px); }
.msg-fade-leave-to { opacity: 0; }

.slide-left-enter-active,
.slide-left-leave-active { transition: transform 0.3s ease; }
.slide-left-enter-from,
.slide-left-leave-to { transform: translateX(-100%); }

.chat-composer {
  border: 1px solid #cbd6e2;
  border-radius: 10px;
  background: #f8fafc;
  padding: 10px;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
}

.agent-model-select {
  width: min(210px, 100%);
}

.agent-model-select .el-select__wrapper {
  min-height: 32px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: rgba(47, 143, 237, 0.08);
  box-shadow: none;
  padding: 0 10px;
}

.agent-model-select .el-select__selected-item {
  color: #0f4f8f;
  font-size: 13px;
  font-weight: 650;
}

.agent-model-select .el-select__caret {
  color: #5f7484;
}

.agent-model-select-popper {
  border: 1px solid #cbd6e2 !important;
  border-radius: 8px !important;
  background: #ffffff !important;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.16) !important;
}

.agent-model-select-popper .el-select-dropdown {
  padding: 4px;
}

.agent-model-select-popper .el-select-dropdown__item {
  height: auto;
  min-height: 54px;
  padding: 7px 9px;
  border-radius: 6px;
  line-height: 1.25;
}

.agent-model-select-popper .el-select-dropdown__item.is-selected {
  background: #eaf5ff;
}

.model-option {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.model-option-title,
.model-option-subtitle {
  display: block;
  max-width: 148px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-option-title {
  color: #15202b;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.model-option-subtitle {
  margin-top: 4px;
  color: #6b7c8a;
  font-size: 11px;
  line-height: 1.2;
}

.model-option-status {
  flex: 0 0 auto;
  border: 1px solid;
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.model-option-status.is-ready {
  border-color: rgba(84, 211, 138, 0.4);
  color: #14824a;
}

.model-option-status.is-pending {
  border-color: rgba(246, 195, 67, 0.5);
  color: #9a6400;
}

.send-button {
  width: 38px;
  height: 34px;
  padding: 0;
  border-radius: 8px;
}

.chat-input .el-textarea__inner {
  min-height: 38px !important;
  background: transparent;
  border: 0;
  box-shadow: none;
  padding: 4px 2px;
  resize: none;
  font-size: 14px;
}

html.dark .agent-core,
html.dark .message-avatar.agent {
  border-color: rgba(139, 217, 255, 0.28);
  background: #102638;
  color: #8bd9ff;
}

html.dark .chat-composer {
  border-color: #22313a;
  background: #0f1b22;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
}

html.dark .agent-model-select .el-select__wrapper {
  border-color: transparent;
  background: rgba(139, 217, 255, 0.09);
  box-shadow: none;
}

html.dark .agent-model-select .el-select__selected-item {
  color: #c8f0ff;
}

html.dark .agent-model-select .el-select__caret {
  color: #8ea0ae;
}

html.dark .agent-model-select-popper {
  border-color: #22313a !important;
  background: #0f1b22 !important;
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.4) !important;
}

html.dark .agent-model-select-popper .el-popper__arrow::before {
  border-color: #22313a !important;
  background: #0f1b22 !important;
}

html.dark .agent-model-select-popper .el-select-dropdown__item {
  color: #dce7ef;
}

html.dark .agent-model-select-popper .el-select-dropdown__item.is-selected,
html.dark .agent-model-select-popper .el-select-dropdown__item.hover,
html.dark .agent-model-select-popper .el-select-dropdown__item:hover {
  background: #102638;
}

html.dark .model-option-title {
  color: #ffffff;
}

html.dark .model-option-subtitle {
  color: #91a4b3;
}

html.dark .model-option-status.is-ready {
  color: #7cf0a7;
}

html.dark .model-option-status.is-pending {
  color: #ffd166;
}

html.dark .agent-pill {
  color: #7cf0a7;
}

html.dark .agent-stream {
  background: #071014;
}

html.dark .rail-line {
  background: #22313a;
}

html.dark .message-card {
  border-color: #22313a;
}

html.dark .message-card.agent {
  background: #0f1b22;
  border-color: #22313a;
}

html.dark .chat-input .el-textarea__inner {
  color: #dce7ef;
}

html.dark .message-card.user {
  background: #17334a;
}

@keyframes agent-glow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(47, 143, 237, 0.2); }
  50% { box-shadow: 0 0 0 8px rgba(47, 143, 237, 0.08); }
}

@media (max-width: 640px) {
  .message-row,
  .message-row.is-user {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .message-row.is-user .message-rail {
    grid-column: 1;
  }

  .message-row.is-user .message-card {
    grid-column: 2;
  }

  .agent-model-select,
  .send-button {
    width: 100%;
  }
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
.markdown-body p { margin: 0.5em 0; }
.markdown-body ul,
.markdown-body ol { margin: 0.5em 0; padding-left: 1.5em; }

.markdown-body code {
  background: rgba(148, 163, 184, 0.15);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'Courier New', monospace;
}
html.dark .markdown-body code { background: rgba(110, 118, 129, 0.2); }

.markdown-body pre {
  background: rgba(15, 23, 42, 0.95);
  color: #e2e8f0;
  padding: 1em;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0.8em 0;
}
.markdown-body pre code { background: none; padding: 0; color: inherit; }

/* 表格 */
.markdown-body table {
  width: 100%; border-collapse: collapse; margin: 1em 0;
  font-size: 0.9em; overflow-x: auto; display: block;
}
.markdown-body thead,
.markdown-body tbody { display: table; width: 100%; table-layout: fixed; }
.markdown-body th,
.markdown-body td {
  border: 1px solid rgba(148, 163, 184, 0.25);
  padding: 0.6em 0.8em; text-align: left;
}
.markdown-body th {
  background: rgba(241, 245, 249, 0.95); font-weight: 600; color: rgba(51, 65, 85, 1);
}
html.dark .markdown-body th { background: rgba(22, 27, 34, 0.95); color: rgba(201, 209, 217, 1); }
.markdown-body tbody tr:nth-child(even) { background: rgba(248, 250, 252, 0.4); }
html.dark .markdown-body tbody tr:nth-child(even) { background: rgba(22, 27, 34, 0.3); }
.markdown-body tbody tr:hover { background: rgba(241, 245, 249, 0.6); }
html.dark .markdown-body tbody tr:hover { background: rgba(22, 27, 34, 0.5); }

.markdown-body blockquote {
  border-left: 4px solid rgba(148, 163, 184, 0.4);
  padding-left: 1em; margin: 0.8em 0; color: rgba(100, 116, 139, 1);
}
html.dark .markdown-body blockquote { color: rgba(139, 148, 158, 1); }

.markdown-body h1,
.markdown-body h2,
.markdown-body h3 { margin: 1em 0 0.5em; font-weight: 600; line-height: 1.3; }
.markdown-body h1 { font-size: 1.5em; }
.markdown-body h2 { font-size: 1.3em; }
.markdown-body h3 { font-size: 1.1em; }
</style>
