<template>
  <div class="agent-chat h-full min-h-0 overflow-hidden">
    <main class="flex h-full min-h-0 min-w-0 flex-col">
        <div
          ref="chatContainer"
          class="agent-stream min-h-0 flex-1 overflow-y-auto p-4"
          @scroll="handleChatScroll"
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
                  <span v-else>{{ userAvatarLabel }}</span>
                </div>
                <span v-if="msg.role === 'assistant'" class="rail-line" />
              </div>

              <article :class="['message-card', msg.role === 'user' ? 'user' : 'agent']">
                <div class="message-card-head mb-2 flex items-center justify-between gap-3">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold">
                      {{ msg.role === 'user' ? t("chat.roles.operator") : t("chat.roles.agent") }}
                    </span>
                    <span v-if="msg.role === 'assistant' && !msg.final" class="agent-pill">{{ t("chat.roles.streaming") }}</span>
                  </div>
                  <div class="message-actions">
                    <span class="message-index font-mono text-[10px]">#{{ index + 1 }}</span>
                    <el-tooltip v-if="msg.role === 'user'" :content="copySuccessIndex === index ? t('chat.actions.copied') : t('chat.actions.copyMessage')" placement="top">
                      <button
                        type="button"
                        class="message-action-button"
                        :aria-label="t('chat.actions.copyMessage')"
                        @click="copyMessage(index, msg)"
                      >
                        <el-icon>
                          <Check v-if="copySuccessIndex === index" />
                          <CopyDocument v-else />
                        </el-icon>
                      </button>
                    </el-tooltip>
                  </div>
                </div>
                <div
                  v-if="msg.role === 'assistant' && (!msg.content && !msg.final)"
                  class="markdown-skeleton"
                  :aria-label="t('chat.loading.markdown')"
                >
                  <span />
                  <span />
                  <span />
                </div>
                <div
                  v-else-if="msg.role === 'assistant'"
                  class="markdown-body prose prose-sm max-w-none dark:prose-invert"
                  v-html="renderMarkdown(parsedAssistantMessage(msg.content).body)"
                ></div>
                <p v-else class="whitespace-pre-wrap break-words text-sm leading-relaxed">{{ msg.content }}</p>
                <span v-if="msg.role === 'assistant' && !msg.final" class="stream-cursor" aria-hidden="true" />

                <div v-if="msg.role === 'assistant' && parsedAssistantMessage(msg.content).thinking" class="thinking-collapse">
                  <button type="button" @click="toggleCollapsed(collapsedThinking, index)">
                    {{ isCollapsed(collapsedThinking, index) ? t("chat.collapse.expandThinking") : t("chat.collapse.collapseThinking") }}
                  </button>
                  <pre v-if="!isCollapsed(collapsedThinking, index)">{{ parsedAssistantMessage(msg.content).thinking }}</pre>
                </div>

                <div v-if="msg.role === 'assistant' && parsedAssistantMessage(msg.content).sources.length" class="source-collapse">
                  <button type="button" @click="toggleCollapsed(collapsedSources, index)">
                    {{ isCollapsed(collapsedSources, index) ? t("chat.collapse.expandSources") : t("chat.collapse.collapseSources") }}
                  </button>
                  <ul v-if="!isCollapsed(collapsedSources, index)">
                    <li v-for="source in parsedAssistantMessage(msg.content).sources" :key="source">{{ source }}</li>
                  </ul>
                </div>

                <ol v-if="msg.role === 'assistant' && parsedAssistantMessage(msg.content).toolEvents.length" class="tool-timeline">
                  <li v-for="event in parsedAssistantMessage(msg.content).toolEvents" :key="event">
                    <span class="tool-call-pulse" />
                    <span>{{ event }}</span>
                  </li>
                </ol>

                <div v-if="msg.role === 'assistant' && runMetaLine(msg)" class="message-run-strip">
                  <span class="message-run-line">{{ runMetaLine(msg) }}</span>
                </div>

                <div v-if="msg.role === 'assistant'" class="message-result-actions">
                  <el-tooltip :content="copySuccessIndex === index ? t('chat.actions.copied') : t('chat.actions.copyMessage')" placement="top">
                    <button
                      type="button"
                      class="message-action-button"
                      :aria-label="t('chat.actions.copyMessage')"
                      @click="copyMessage(index, msg)"
                    >
                      <el-icon>
                        <Check v-if="copySuccessIndex === index" />
                        <CopyDocument v-else />
                      </el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip v-if="msg.raw_run" :content="copyRunSuccessIndex === index ? t('chat.actions.copied') : t('chat.actions.copyRun')" placement="top">
                    <button
                      type="button"
                      class="message-action-button"
                      :aria-label="t('chat.actions.copyRun')"
                      @click="copyRun(index, msg)"
                    >
                      <el-icon>
                        <Check v-if="copyRunSuccessIndex === index" />
                        <CopyDocument v-else />
                      </el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip v-if="messageSessionId(msg)" :content="t('chat.actions.viewTrace')" placement="top">
                    <button
                      type="button"
                      class="message-action-button"
                      :aria-label="t('chat.actions.viewTrace')"
                      @click="openTraceForSession(msg)"
                    >
                      <el-icon><DataAnalysis /></el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip v-if="msg.final && hasUserPromptBefore(index)" :content="t('chat.actions.retryAnswer')" placement="top">
                    <button
                      type="button"
                      class="message-action-button"
                      :aria-label="t('chat.actions.retryAnswer')"
                      :disabled="loading"
                      @click="retryAnswer(index)"
                    >
                      <el-icon><RefreshRight /></el-icon>
                    </button>
                  </el-tooltip>
                </div>
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
                  {{ t("chat.loading.planning") }}
                </div>
              </article>
            </div>
          </transition>

          <div class="chat-scroll-actions" aria-live="polite">
            <el-tooltip v-if="showBackToTop" :content="t('chat.actions.backToTop')" placement="left">
              <button
                type="button"
                class="chat-scroll-button"
                :aria-label="t('chat.actions.backToTop')"
                @click="scrollToTop"
              >
                <el-icon><Top /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip v-if="showScrollToBottom" :content="pendingNewMessages ? t('chat.actions.newMessages', { count: pendingNewMessages }) : t('chat.actions.scrollToBottom')" placement="left">
              <button
                type="button"
                class="chat-scroll-button is-bottom"
                :aria-label="t('chat.actions.scrollToBottom')"
                @click="scrollToBottomAndClear"
              >
                <span v-if="pendingNewMessages" class="new-message-count">{{ pendingNewMessages }}</span>
                <el-icon><Bottom /></el-icon>
              </button>
            </el-tooltip>
          </div>
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

        <footer class="agent-chat-footer p-3">
          <div v-if="showQuickPrompts" class="mb-2 flex flex-wrap gap-2">
            <button
              v-for="prompt in quickPrompts"
              :key="prompt"
              type="button"
              class="quick-prompt cursor-pointer px-2.5 py-1.5 text-xs transition-colors duration-200"
              @click="inputMessage = prompt"
            >
              {{ prompt }}
            </button>
          </div>
          <div
            v-if="modelConfigNotice"
            class="model-config-notice mb-2 px-3 py-2 text-xs"
          >
            {{ modelConfigNotice }}
          </div>
          <div class="chat-composer">
            <div class="chat-composer-row">
              <el-input
                v-model="inputMessage"
                :placeholder="t('chat.composer.placeholder')"
                @keyup.enter.exact="sendMessage"
                :disabled="loading"
                :autosize="{ minRows: 1, maxRows: 4 }"
                type="textarea"
                class="chat-input"
              />
              <el-select
                v-model="selectedModelId"
                :loading="modelLoading"
                :placeholder="t('chat.composer.modelPlaceholder')"
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
                        {{ model.model_id || t("chat.composer.missingModelId") }}
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
              <el-tooltip :content="t('chat.composer.send')" placement="top">
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

    <button v-if="zoomedImage" type="button" class="image-zoom-backdrop" @click="zoomedImage = null">
      <img :src="zoomedImage" :alt="t('chat.image.zoomPreview')" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, nextTick, onMounted, onUnmounted, watch } from "vue"
import { storeToRefs } from "pinia"
import MarkdownIt from "markdown-it"
import hljs from "highlight.js"
import { useChatApi, useChatHistory, useSettingsApi } from "../composables/useApi"
import { copyToClipboard } from "../lib/clipboard"
import { useSessionStore } from "../stores/sessions"
import type { ChatRunMetrics, Message, ModelConfig } from "../types"
import { useI18n } from "vue-i18n"
import {
  Bottom,
  Check,
  CopyDocument,
  Cpu,
  DataAnalysis,
  Loading,
  Promotion,
  RefreshRight,
  Top,
} from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"

// ── Markdown ──────────────────────────────────────────────────────
const md: MarkdownIt = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: (str: string, lang: string): string => {
    const safeLang = md.utils.escapeHtml(lang || "")
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs" data-lang="${safeLang}"><code class="language-${safeLang}">` +
               hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
               '</code></pre>'
      } catch {}
    }
    return `<pre class="hljs" data-lang="${safeLang}"><code class="language-${safeLang}">` + md.utils.escapeHtml(str) + '</code></pre>'
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

const props = defineProps<{
  currentUserId?: string | null
  currentUserInitials?: string | null
}>()

// ── State ─────────────────────────────────────────────────────────
const { t } = useI18n()
const inputMessage = ref("")
const MODEL_STORAGE_KEY = "agno-aios-chat-model-id"

interface ChatMessage extends Message {}

interface ParsedAssistantMessage {
  body: string
  thinking: string
  sources: string[]
  toolEvents: string[]
}

const createWelcomeMessage = (): ChatMessage => ({ role: "assistant", content: t("chat.welcome"), final: true })
const messages = ref<ChatMessage[]>([createWelcomeMessage()])
const chatContainer = ref<HTMLElement | null>(null)
const zoomedImage = ref<string | null>(null)
const copySuccessIndex = ref<number | null>(null)
const copyRunSuccessIndex = ref<number | null>(null)
const pendingNewMessages = ref(0)
const showScrollToBottom = ref(false)
const showBackToTop = ref(false)
const collapsedSources = reactive(new Set<number>())
const collapsedThinking = reactive(new Set<number>())
const sessionStore = useSessionStore()
const { currentChatSessionId: currentSessionId } = storeToRefs(sessionStore)
const modelLoading = ref(false)
const modelOptions = ref<ModelConfig[]>([])
const selectedModelId = ref<string | null>(null)

const { loading, error, sendMessageStream } = useChatApi()
const { getSessionHistory } = useChatHistory()
const { fetchModels } = useSettingsApi()

const userAvatarLabel = computed(() => (props.currentUserInitials || "AI").slice(0, 2).toUpperCase())

const selectedModel = computed(() => {
  return modelOptions.value.find((model) => model.id === selectedModelId.value)
    ?? modelOptions.value.find((model) => model.enabled)
    ?? null
})

const selectedModelReady = computed(() => Boolean(selectedModel.value?.enabled && selectedModel.value.configured))
const currentModelName = computed(() => selectedModel.value?.name ?? t("chat.status.unselected"))
const modelConfigNotice = computed(() => {
  if (modelLoading.value) return ""
  if (!modelOptions.value.length) return t("chat.notices.noModels")
  if (!selectedModel.value) return t("chat.notices.noSelectedModel")
  if (!selectedModel.value.enabled) return t("chat.notices.disabledModel", { name: selectedModel.value.name })
  if (!selectedModel.value.configured) return t("chat.notices.unconfiguredModel", { name: selectedModel.value.name })
  return ""
})

const quickPrompts = computed(() => [
  t("chat.prompts.cveImpact"),
  t("chat.prompts.exposurePlan"),
  t("chat.prompts.alertRunbook"),
])

const showQuickPrompts = computed(() => messages.value.length <= 1 && !loading.value)

const notifyModelChange = () => {
  const model = selectedModel.value
  window.dispatchEvent(new CustomEvent("agno-aios-model-change", {
    detail: {
      id: model?.id ?? selectedModelId.value,
      name: model?.name ?? t("chat.status.unselected"),
    },
  }))
}

const persistSelectedModel = () => {
  if (selectedModelId.value) {
    localStorage.setItem(MODEL_STORAGE_KEY, selectedModelId.value)
  }
  notifyModelChange()
}

const loadModels = async () => {
  modelLoading.value = true
  try {
    const config = await fetchModels()
    const models = Array.isArray(config.models) ? config.models : []
    modelOptions.value = models
    const savedId = localStorage.getItem(MODEL_STORAGE_KEY)
    const enabledIds = new Set(models.filter((model) => model.enabled).map((model) => model.id))
    if (savedId && enabledIds.has(savedId)) {
      selectedModelId.value = savedId
    } else if (enabledIds.has(config.active_model_id)) {
      selectedModelId.value = config.active_model_id
    } else {
      selectedModelId.value = models.find((model) => model.enabled)?.id ?? models[0]?.id ?? null
    }
    persistSelectedModel()
  } catch {
    ElMessage.warning(t("chat.notices.modelLoadFailed"))
  } finally {
    modelLoading.value = false
  }
}

// ── Helpers ───────────────────────────────────────────────────────
const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
  pendingNewMessages.value = 0
  updateScrollState()
}

const isNearBottom = () => {
  const container = chatContainer.value
  if (!container) return true
  return container.scrollHeight - container.clientHeight - container.scrollTop < 120
}

const updateScrollState = () => {
  const container = chatContainer.value
  if (!container) {
    showScrollToBottom.value = false
    showBackToTop.value = false
    return
  }
  showScrollToBottom.value = !isNearBottom()
  showBackToTop.value = container.scrollTop > 360
  if (isNearBottom()) pendingNewMessages.value = 0
}

const handleChatScroll = () => {
  updateScrollState()
}

const scrollToBottomAndClear = () => {
  void scrollToBottom()
}

const scrollToTop = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTo({ top: 0, behavior: "smooth" })
  }
  updateScrollState()
}

const copyMessage = async (index: number, message: ChatMessage) => {
  const content = message.role === "assistant" ? parsedAssistantMessage(message.content).body : message.content
  if (!content.trim()) return
  if (await copyToClipboard(content.trim())) {
    markCopied(copySuccessIndex, index)
    ElMessage.success(t("common.clipboard.copied"))
  } else {
    ElMessage.warning(t("common.clipboard.failed"))
  }
}

const markCopied = (target: typeof copySuccessIndex, index: number) => {
  target.value = index
  window.setTimeout(() => {
    if (target.value === index) target.value = null
  }, 1400)
}

const copyRun = async (index: number, message: ChatMessage) => {
  const run = message.raw_run || {
    run_id: message.run_id,
    session_id: message.session_id,
    user_id: message.user_id,
    model: message.model,
    model_provider: message.model_provider,
    metrics: message.metrics,
    tools: message.tools,
    content: message.content,
  }
  if (await copyToClipboard(JSON.stringify(run, null, 2))) {
    markCopied(copyRunSuccessIndex, index)
    ElMessage.success(t("common.clipboard.copied"))
  } else {
    ElMessage.warning(t("common.clipboard.failed"))
  }
}

const asNumber = (value: unknown) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

const formatMetricSeconds = (value: unknown) => {
  const seconds = asNumber(value)
  if (seconds === null || seconds < 0) return "-"
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
  if (seconds < 10) return `${seconds.toFixed(2)} s`
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  return `${minutes}m ${remainingSeconds}s`
}

const formatTokenCount = (value: unknown) => {
  const count = asNumber(value)
  if (count === null) return "-"
  return Math.round(count).toLocaleString()
}

const rawStringField = (message: ChatMessage, key: string) => {
  const value = message.raw_run?.[key]
  return typeof value === "string" && value.trim() ? value.trim() : null
}

const messageSessionId = (message: ChatMessage) => {
  return message.session_id || rawStringField(message, "session_id")
}

const messageRunId = (message: ChatMessage) => {
  return message.run_id || rawStringField(message, "run_id")
}

const runMetaLine = (message: ChatMessage) => {
  const metrics: ChatRunMetrics = message.metrics || {}
  const parts: string[] = []
  if (metrics.duration !== undefined && metrics.duration !== null) {
    parts.push(t("chat.metrics.durationValue", { value: formatMetricSeconds(metrics.duration) }))
  }
  if (metrics.total_tokens !== undefined && metrics.total_tokens !== null) {
    parts.push(t("chat.metrics.tokensValue", { value: formatTokenCount(metrics.total_tokens) }))
  }
  if (metrics.input_tokens !== undefined && metrics.input_tokens !== null && metrics.output_tokens !== undefined && metrics.output_tokens !== null) {
    parts.push(t("chat.metrics.tokenBreakdown", {
      input: formatTokenCount(metrics.input_tokens),
      output: formatTokenCount(metrics.output_tokens),
    }))
  }
  const runId = messageRunId(message)
  if (runId) parts.push(t("chat.metrics.runValue", { value: compactId(runId) }))
  return parts.join(" · ")
}

const compactId = (value?: string | null) => {
  const text = (value || "").trim()
  if (!text) return "-"
  if (text.length <= 18) return text
  return `${text.slice(0, 8)}...${text.slice(-4)}`
}

const openTraceForSession = (message: ChatMessage) => {
  const sessionId = messageSessionId(message)
  if (!sessionId) return
  window.dispatchEvent(new CustomEvent("agno-aios-trace-session-open", {
    detail: {
      sessionId,
      userId: message.user_id || rawStringField(message, "user_id"),
      runId: messageRunId(message),
    },
  }))
}

const userPromptBefore = (index: number) => {
  for (let i = index - 1; i >= 0; i -= 1) {
    const message = messages.value[i]
    if (message?.role === "user" && message.content.trim()) return message.content.trim()
  }
  return ""
}

const hasUserPromptBefore = (index: number) => Boolean(userPromptBefore(index))

const mergeAssistantRunMetadata = async (sessionId: string, assistantIndex: number, assistantContent: string) => {
  const content = assistantContent.trim()
  if (!content) return
  try {
    const history = await getSessionHistory(sessionId)
    const persistedMessage = [...history]
      .reverse()
      .find((message) => message.role === "assistant" && message.content.trim() === content)
    const currentMessage = messages.value[assistantIndex]
    if (
      !persistedMessage
      || !currentMessage
      || currentMessage.role !== "assistant"
      || currentMessage.content.trim() !== content
      || currentSessionId.value !== sessionId
    ) return
    messages.value[assistantIndex] = {
      ...currentMessage,
      ...persistedMessage,
      content: currentMessage.content,
      final: true,
      session_id: persistedMessage.session_id || currentMessage.session_id || sessionId,
      user_id: persistedMessage.user_id || currentMessage.user_id || props.currentUserId || null,
    }
  } catch {
    // Metadata is an enhancement; keep the streamed answer even when history is late.
  }
}

const followStreamPosition = (shouldStick: boolean) => {
  if (shouldStick) {
    void scrollToBottom()
  } else {
    pendingNewMessages.value = Math.max(1, pendingNewMessages.value)
    updateScrollState()
  }
}

const generateSessionId = () => crypto.randomUUID()

const toggleCollapsed = (set: Set<number>, index: number) => {
  if (set.has(index)) {
    set.delete(index)
  } else {
    set.add(index)
  }
}

const isCollapsed = (set: Set<number>, index: number) => set.has(index)

const parsedAssistantMessage = (content: string): ParsedAssistantMessage => {
  const sources: string[] = []
  const toolEvents: string[] = []
  let thinking = ""
  let body = content

  body = body.replace(/<think>([\s\S]*?)(?:<\/think>|$)/gi, (_match, value: string) => {
    thinking = [thinking, value.trim()].filter(Boolean).join("\n\n")
    return ""
  })

  const bodyLines: string[] = []
  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim()
    if (/^(思考过程|Thinking)\s*[:：]/i.test(line)) {
      thinking = [thinking, line.replace(/^(思考过程|Thinking)\s*[:：]\s*/i, "").trim() || t("chat.notices.thinkingFallback")]
        .filter(Boolean)
        .join("\n\n")
      continue
    }
    if (/^(来源|Source|Sources|References|引用)\s*[:：]/i.test(line)) {
      sources.push(line)
      continue
    }
    if (/^(tool|工具调用|MCP|function call)\b/i.test(line) || /\b(tool|MCP|function call)\b/i.test(line)) {
      toolEvents.push(line)
      continue
    }
    bodyLines.push(rawLine)
  }

  return {
    body: bodyLines.join("\n").trim(),
    thinking,
    sources,
    toolEvents: toolEvents.slice(0, 8),
  }
}

const enhanceRenderedMarkdown = async () => {
  await nextTick()
  const stickToBottom = isNearBottom()
  document.querySelectorAll<HTMLElement>(".agent-chat pre").forEach((pre) => {
    if (pre.querySelector(".code-copy")) return
    const code = pre.querySelector("code")
    if (!code) return
    const button = document.createElement("button")
    button.type = "button"
    button.className = "code-copy"
    button.textContent = t("chat.code.copy")
    button.addEventListener("click", async () => {
      if (await copyToClipboard(code.textContent || "")) {
        ElMessage.success(t("common.clipboard.copied"))
      } else {
        ElMessage.warning(t("common.clipboard.failed"))
      }
    })
    pre.appendChild(button)
  })

  document.querySelectorAll<HTMLImageElement>(".agent-chat .markdown-body img").forEach((image) => {
    if (image.dataset.zoomBound === "true") return
    image.dataset.zoomBound = "true"
    image.addEventListener("click", () => {
      zoomedImage.value = image.currentSrc || image.src
    })
    image.addEventListener("load", () => {
      if (stickToBottom) void scrollToBottom()
    }, { once: true })
  })

  if (stickToBottom) void scrollToBottom()
}

// ── Sessions ──────────────────────────────────────────────────────
const notifySessionChange = () => {
  window.dispatchEvent(new CustomEvent("agno-aios-chat-sessions-change", {
    detail: { sessionId: currentSessionId.value },
  }))
}

const handleExternalSessionSelect = (event: Event) => {
  const detail = (event as CustomEvent<{ sessionId?: string }>).detail
  if (detail?.sessionId) void selectSession(detail.sessionId)
}

const handleExternalNewChat = () => {
  createNewChat()
}

const selectSession = async (sessionId: string) => {
  currentSessionId.value = sessionId
  try {
    const history: Message[] = await getSessionHistory(sessionId)
    if (history.length > 0) {
      messages.value = history.map(m => ({ ...m, final: true }))
    } else {
      messages.value = [createWelcomeMessage()]
    }
  } catch {
    messages.value = [createWelcomeMessage()]
  }
  notifySessionChange()
  void scrollToBottom()
  void enhanceRenderedMarkdown()
}

const createNewChat = () => {
  currentSessionId.value = null
  messages.value = [createWelcomeMessage()]
  notifySessionChange()
  void scrollToBottom()
}

// ── Chat ──────────────────────────────────────────────────────────
const submitPrompt = async (userMsg: string, options: { appendUser: boolean }) => {
  if (!userMsg.trim() || loading.value) return
  if (!selectedModelReady.value) {
    ElMessage.warning(modelConfigNotice.value || t("chat.notices.modelUnavailable"))
    return
  }

  let sessionId = currentSessionId.value
  if (!sessionId) {
    sessionId = generateSessionId()
    currentSessionId.value = sessionId
    notifySessionChange()
  }

  if (options.appendUser) {
    messages.value.push({ role: "user", content: userMsg, session_id: sessionId, user_id: props.currentUserId || null })
    void scrollToBottom()
  }

  try {
    const idx = messages.value.push({ role: "assistant", content: "", final: false, session_id: sessionId, user_id: props.currentUserId || null }) - 1
    const shouldStickToBottom = isNearBottom()

    await sendMessageStream(userMsg, sessionId, selectedModelId.value, (chunk) => {
      const m = messages.value[idx]
      if (m) m.content += chunk
      followStreamPosition(shouldStickToBottom)
      void enhanceRenderedMarkdown()
    })

    const m = messages.value[idx]
    if (m) {
      m.final = true
      m.session_id = m.session_id || sessionId
      await mergeAssistantRunMetadata(sessionId, idx, m.content)
    }
    void enhanceRenderedMarkdown()

    notifySessionChange()
  } catch {
    messages.value.push({ role: "assistant", content: t("chat.notices.requestFailed"), final: true, session_id: sessionId })
  } finally {
    followStreamPosition(isNearBottom())
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) return
  const userMsg = inputMessage.value.trim()
  inputMessage.value = ""
  await submitPrompt(userMsg, { appendUser: true })
}

const retryAnswer = async (index: number) => {
  const prompt = userPromptBefore(index)
  if (!prompt || loading.value) return
  messages.value = messages.value.slice(0, index)
  await submitPrompt(prompt, { appendUser: false })
}

const clearError = () => { if (error.value) error.value = null }

watch(currentModelName, notifyModelChange)
watch(
  () => messages.value.map((message) => `${message.content}:${message.final}`).join("\n---\n"),
  () => {
    void enhanceRenderedMarkdown()
    updateScrollState()
  },
  { flush: "post" },
)

onMounted(async () => {
  window.addEventListener("agno-aios-chat-session-select", handleExternalSessionSelect)
  window.addEventListener("agno-aios-chat-new", handleExternalNewChat)
  await loadModels()
  notifySessionChange()
  void scrollToBottom()
  void enhanceRenderedMarkdown()
})

onUnmounted(() => {
  window.removeEventListener("agno-aios-chat-session-select", handleExternalSessionSelect)
  window.removeEventListener("agno-aios-chat-new", handleExternalNewChat)
})
</script>

<style>
.agent-chat {
  background: var(--ag-frame);
  color: var(--ag-text);
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.agent-chat-footer {
  border-color: var(--ag-panel-border);
  background: var(--ag-panel-bg);
}

.agent-chat-footer {
  border-top: 1px solid var(--ag-panel-border);
}

.message-index {
  color: var(--ag-muted);
}

.agent-pill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  border: 1px solid rgba(84, 211, 138, 0.35);
  border-radius: 999px;
  padding: 0 8px;
  background: rgba(84, 211, 138, 0.1);
  color: var(--ag-green);
  font-size: 10px;
  font-weight: 700;
}

.agent-stream {
  position: relative;
  background: var(--ag-frame);
}

.message-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  margin-bottom: 16px;
  animation: message-rise 0.24s ease both;
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
  background: var(--ag-border);
}

.message-avatar {
  z-index: 1;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: var(--ag-radius-panel);
  font-size: 12px;
  font-weight: 700;
}

.message-avatar.agent {
  border: 1px solid rgba(47, 143, 237, 0.35);
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
}

.message-avatar.user {
  background: var(--ag-sidebar-item-hover);
  color: var(--ag-sidebar-strong);
}

.message-card {
  max-width: min(860px, 100%);
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  padding: 12px 14px;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.message-card:hover {
  border-color: color-mix(in srgb, var(--ag-blue) 28%, var(--ag-border));
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.message-card.agent {
  background: var(--ag-panel);
}

.message-card.user {
  width: min(720px, 100%);
  background: var(--ag-user-message-bg);
  color: var(--ag-user-message-text);
}

.message-card-head {
  min-height: 24px;
}

.message-actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
}

.message-action-button {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: color-mix(in srgb, var(--ag-panel) 82%, transparent);
  color: var(--ag-muted);
  opacity: 0;
  transition:
    opacity 0.16s ease,
    border-color 0.16s ease,
    background 0.16s ease,
    color 0.16s ease,
    transform 0.16s ease;
}

.message-card:hover .message-action-button,
.message-result-actions .message-action-button,
.message-action-button:focus-visible {
  opacity: 1;
}

.message-action-button:hover {
  border-color: var(--ag-blue);
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
  transform: translateY(-1px);
}

.agent-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--ag-green);
  box-shadow: 0 0 0 6px rgba(84, 211, 138, 0.15);
}

.markdown-skeleton {
  display: grid;
  gap: 8px;
  padding: 4px 0;
}

.markdown-skeleton span {
  display: block;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--ag-panel-soft) 0%, var(--ag-panel) 48%, var(--ag-panel-soft) 100%);
  background-size: 220% 100%;
  animation: skeleton-scan 1.25s ease-in-out infinite;
}

.markdown-skeleton span:nth-child(2) {
  width: 78%;
}

.markdown-skeleton span:nth-child(3) {
  width: 54%;
}

.stream-cursor {
  display: inline-block;
  width: 7px;
  height: 16px;
  margin-left: 3px;
  vertical-align: -2px;
  border-radius: 2px;
  background: var(--ag-blue);
  animation: stream-cursor-blink 0.9s steps(2, start) infinite;
}

.message-card pre {
  position: relative;
}

.code-copy {
  position: absolute;
  top: 8px;
  right: 8px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel);
  color: var(--ag-muted-strong);
  cursor: pointer;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  padding: 5px 7px;
}

.thinking-collapse,
.source-collapse,
.tool-timeline {
  margin-top: 10px;
  border-top: 1px solid var(--ag-border);
  padding-top: 10px;
}

.thinking-collapse button,
.source-collapse button {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  color: var(--ag-muted-strong);
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
}

.thinking-collapse pre {
  margin: 8px 0 0;
  white-space: pre-wrap;
  color: var(--ag-muted-strong);
  font-size: 12px;
}

.source-collapse ul,
.tool-timeline {
  margin-bottom: 0;
  color: var(--ag-muted-strong);
  font-size: 12px;
}

.tool-timeline {
  list-style: none;
  padding-left: 0;
}

.tool-timeline li {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-left: 0;
  animation: tool-call-enter 0.28s ease both;
}

.tool-call-pulse {
  position: relative;
  top: 0.45em;
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--ag-blue);
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--ag-blue) 30%, transparent);
  animation: tool-call-pulse 1.2s ease-out infinite;
}

.message-run-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  border-top: 1px solid var(--ag-border);
  padding-top: 8px;
}

.message-run-line {
  color: var(--ag-muted);
  font-size: 11px;
  line-height: 1.4;
}

.message-result-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  border-top: 1px solid var(--ag-border);
  padding-top: 8px;
}

.message-result-actions .message-action-button {
  background: color-mix(in srgb, var(--ag-panel-soft) 86%, transparent);
}

.markdown-body img {
  cursor: zoom-in;
  max-height: 420px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
}

.quick-prompt {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  color: var(--ag-muted-strong);
}

.quick-prompt:hover {
  border-color: color-mix(in srgb, var(--ag-blue) 50%, var(--ag-border));
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
}

.model-config-notice {
  border: 1px solid color-mix(in srgb, var(--ag-yellow) 50%, var(--ag-border));
  border-radius: var(--ag-radius-control);
  background: var(--ag-yellow-soft);
  color: var(--ag-yellow);
}

.image-zoom-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  border: 0;
  background: rgba(3, 7, 18, 0.78);
  cursor: zoom-out;
  padding: 24px;
}

.image-zoom-backdrop img {
  max-width: min(1100px, 96vw);
  max-height: 92vh;
  border-radius: var(--ag-radius-panel);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
}

.chat-scroll-actions {
  position: sticky;
  right: 12px;
  bottom: 12px;
  z-index: 8;
  display: grid;
  justify-content: end;
  gap: 8px;
  pointer-events: none;
}

.chat-scroll-button {
  position: relative;
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel);
  color: var(--ag-muted-strong);
  box-shadow: var(--ag-shadow-popover);
  pointer-events: auto;
  transition:
    border-color 0.16s ease,
    color 0.16s ease,
    transform 0.16s ease,
    background 0.16s ease;
}

.chat-scroll-button:hover {
  border-color: var(--ag-blue);
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
  transform: translateY(-2px);
}

.new-message-count {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 18px;
  height: 18px;
  border: 1px solid var(--ag-panel);
  border-radius: 999px;
  background: var(--ag-accent);
  color: #fff;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
  line-height: 16px;
  text-align: center;
}

/* 过渡动画 */
.msg-fade-enter-active,
.msg-fade-leave-active { transition: all 0.3s ease; }
.msg-fade-enter-from { opacity: 0; transform: translateY(8px); }
.msg-fade-leave-to { opacity: 0; }

.chat-composer {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 10px;
  box-shadow: var(--ag-shadow-panel);
}

.chat-composer-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.chat-input {
  flex: 1 1 auto;
  min-width: 0;
}

.agent-model-select {
  flex: 0 0 220px;
  width: 220px;
}

.agent-model-select .el-select__wrapper {
  min-height: 32px;
  border: 1px solid transparent;
  border-radius: var(--ag-radius-panel);
  background: var(--ag-blue-soft);
  box-shadow: none;
  padding: 0 10px;
}

.agent-model-select .el-select__selected-item {
  color: var(--ag-blue);
  font-size: 13px;
  font-weight: 650;
}

.agent-model-select .el-select__caret {
  color: var(--ag-muted);
}

.agent-model-select-popper {
  border: 1px solid var(--ag-border) !important;
  border-radius: var(--ag-radius-panel) !important;
  background: var(--ag-panel) !important;
  box-shadow: var(--ag-shadow-popover) !important;
}

.agent-model-select-popper .el-select-dropdown {
  padding: 4px;
}

.agent-model-select-popper .el-select-dropdown__item {
  height: auto;
  min-height: 54px;
  padding: 7px 9px;
  border-radius: var(--ag-radius-control);
  line-height: 1.25;
}

.agent-model-select-popper .el-select-dropdown__item.is-selected {
  background: var(--ag-blue-soft);
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
  color: var(--ag-heading);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.model-option-subtitle {
  margin-top: 4px;
  color: var(--ag-muted);
  font-size: 11px;
  line-height: 1.2;
}

.model-option-status {
  flex: 0 0 auto;
  border: 1px solid;
  border-radius: var(--ag-radius-control);
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.model-option-status.is-ready {
  border-color: rgba(84, 211, 138, 0.4);
  color: var(--ag-green);
}

.model-option-status.is-pending {
  border-color: rgba(246, 195, 67, 0.5);
  color: var(--ag-yellow);
}

.send-button {
  flex: 0 0 38px;
  width: 38px;
  height: 34px;
  padding: 0;
  border-radius: var(--ag-radius-panel);
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

html.dark .agent-model-select-popper .el-select-dropdown__item.is-selected,
html.dark .agent-model-select-popper .el-select-dropdown__item.hover,
html.dark .agent-model-select-popper .el-select-dropdown__item:hover {
  background: var(--ag-blue-soft);
}

html.dark .chat-input .el-textarea__inner {
  color: var(--ag-text);
}

@keyframes skeleton-scan {
  from { background-position: 100% 0; }
  to { background-position: -100% 0; }
}

@keyframes message-rise {
  from { opacity: 0; transform: translateY(10px) scale(0.99); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes stream-cursor-blink {
  0%, 46% { opacity: 1; }
  47%, 100% { opacity: 0; }
}

@keyframes tool-call-enter {
  from { opacity: 0; transform: translateX(-6px); }
  to { opacity: 1; transform: translateX(0); }
}

@keyframes tool-call-pulse {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--ag-blue) 34%, transparent); }
  72%, 100% { box-shadow: 0 0 0 8px transparent; }
}

@media (prefers-reduced-motion: reduce) {
  .message-row,
  .tool-timeline li,
  .markdown-skeleton span,
  .stream-cursor,
  .tool-call-pulse {
    animation: none;
  }

  .message-card,
  .message-action-button,
  .chat-scroll-button {
    transition: none;
  }
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

  .chat-composer-row {
    flex-wrap: wrap;
  }

  .agent-model-select {
    flex: 1 1 calc(100% - 48px);
    width: auto;
  }

  .send-button {
    flex: 0 0 38px;
    width: 38px;
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
  color: var(--ag-code-text);
  padding: 1em;
  border-radius: var(--ag-radius-panel);
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
