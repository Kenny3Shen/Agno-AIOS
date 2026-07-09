<template>
  <article :class="['message-card', message.role === 'user' ? 'user' : 'agent']">
    <div class="message-card-head mb-2 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold">
          {{ message.role === "user" ? t("chat.roles.operator") : t("chat.roles.agent") }}
        </span>
        <span v-if="message.role === 'assistant' && !message.final" class="agent-pill">{{ t("chat.roles.streaming") }}</span>
      </div>
      <div class="message-actions">
        <span class="message-index font-mono text-[10px]">#{{ index + 1 }}</span>
        <el-tooltip v-if="message.role === 'user'" :content="copySuccessIndex === index ? t('chat.actions.copied') : t('chat.actions.copyMessage')" placement="top">
          <button
            type="button"
            class="message-action-button"
            :aria-label="t('chat.actions.copyMessage')"
            @click="emit('copy-message', index, message)"
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
      v-if="message.role === 'assistant' && (!message.content && !message.final)"
      class="markdown-skeleton"
      :aria-label="t('chat.loading.markdown')"
    >
      <span />
      <span />
      <span />
    </div>
    <MarkdownViewer
      v-else-if="message.role === 'assistant'"
      class="markdown-body prose prose-sm max-w-none dark:prose-invert"
      :content="parsedAssistantMessage.body"
    />
    <p v-else class="whitespace-pre-wrap break-words text-sm leading-relaxed">{{ message.content }}</p>
    <span v-if="message.role === 'assistant' && !message.final" class="stream-cursor" aria-hidden="true" />

    <div v-if="message.role === 'assistant' && parsedAssistantMessage.thinking" class="thinking-collapse">
      <button type="button" @click="thinkingCollapsed = !thinkingCollapsed">
        {{ thinkingCollapsed ? t("chat.collapse.expandThinking") : t("chat.collapse.collapseThinking") }}
      </button>
      <pre v-if="!thinkingCollapsed">{{ parsedAssistantMessage.thinking }}</pre>
    </div>

    <div v-if="message.role === 'assistant' && parsedAssistantMessage.sources.length" class="source-collapse">
      <button type="button" @click="sourcesCollapsed = !sourcesCollapsed">
        {{ sourcesCollapsed ? t("chat.collapse.expandSources") : t("chat.collapse.collapseSources") }}
      </button>
      <ul v-if="!sourcesCollapsed">
        <li v-for="source in parsedAssistantMessage.sources" :key="source">{{ source }}</li>
      </ul>
    </div>

    <ol v-if="message.role === 'assistant' && parsedAssistantMessage.toolEvents.length" class="tool-timeline">
      <li v-for="event in parsedAssistantMessage.toolEvents" :key="event">
        <span class="tool-call-pulse" />
        <span>{{ event }}</span>
      </li>
    </ol>

    <div v-if="message.role === 'assistant' && runMetaLine" class="message-run-strip">
      <span class="message-run-line">{{ runMetaLine }}</span>
    </div>

    <div v-if="message.role === 'assistant'" class="message-result-actions">
      <el-tooltip :content="copySuccessIndex === index ? t('chat.actions.copied') : t('chat.actions.copyMessage')" placement="top">
        <button
          type="button"
          class="message-action-button"
          :aria-label="t('chat.actions.copyMessage')"
          @click="emit('copy-message', index, message)"
        >
          <el-icon>
            <Check v-if="copySuccessIndex === index" />
            <CopyDocument v-else />
          </el-icon>
        </button>
      </el-tooltip>
      <el-tooltip v-if="message.raw_run" :content="copyRunSuccessIndex === index ? t('chat.actions.copied') : t('chat.actions.copyRun')" placement="top">
        <button
          type="button"
          class="message-action-button"
          :aria-label="t('chat.actions.copyRun')"
          @click="emit('copy-run', index, message)"
        >
          <el-icon>
            <Check v-if="copyRunSuccessIndex === index" />
            <CopyDocument v-else />
          </el-icon>
        </button>
      </el-tooltip>
      <el-tooltip v-if="hasSessionTrace" :content="t('chat.actions.viewTrace')" placement="top">
        <button
          type="button"
          class="message-action-button"
          :aria-label="t('chat.actions.viewTrace')"
          @click="emit('open-trace', message)"
        >
          <el-icon><DataAnalysis /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip v-if="message.final && hasUserPromptBefore" :content="t('chat.actions.retryAnswer')" placement="top">
        <button
          type="button"
          class="message-action-button"
          :aria-label="t('chat.actions.retryAnswer')"
          :disabled="loading"
          @click="emit('retry-answer', index)"
        >
          <el-icon><RefreshRight /></el-icon>
        </button>
      </el-tooltip>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import { Check, CopyDocument, DataAnalysis, RefreshRight } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import MarkdownViewer from "../common/MarkdownViewer.vue"
import type { ParsedAssistantMessage } from "../../composables/useChatMarkdownRenderer"
import type { Message } from "../../types"

const props = defineProps<{
  message: Message
  index: number
  parsedAssistantMessage: ParsedAssistantMessage
  runMetaLine: string
  hasUserPromptBefore: boolean
  loading: boolean
  copySuccessIndex: number | null
  copyRunSuccessIndex: number | null
}>()

const emit = defineEmits<{
  "copy-message": [index: number, message: Message]
  "copy-run": [index: number, message: Message]
  "open-trace": [message: Message]
  "retry-answer": [index: number]
}>()

const { t } = useI18n()
const thinkingCollapsed = ref(false)
const sourcesCollapsed = ref(false)
const hasSessionTrace = computed(() => Boolean(props.message.session_id || props.message.raw_run?.session_id))
</script>
