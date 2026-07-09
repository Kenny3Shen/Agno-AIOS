<template>
  <div
    ref="chatContainer"
    class="agent-stream min-h-0 flex-1 overflow-y-auto"
    @scroll="emit('scroll')"
  >
    <div class="chat-thread-frame">
      <transition-group name="msg-fade">
        <div
          v-for="(message, index) in messages"
          :key="index"
          :class="['message-row', message.role === 'user' ? 'is-user' : 'is-agent']"
        >
          <div class="message-rail">
            <div :class="['message-avatar', message.role === 'user' ? 'user' : 'agent']">
              <el-icon v-if="message.role === 'assistant'"><Cpu /></el-icon>
              <span v-else>{{ userAvatarLabel }}</span>
            </div>
            <span v-if="message.role === 'assistant'" class="rail-line" />
          </div>

          <ChatMessageCard
            :message="message"
            :index="index"
            :parsed-assistant-message="parseAssistantMessage(assistantDisplayContent(message))"
            :run-meta-line="runMetaLine(message)"
            :has-user-prompt-before="hasUserPromptBefore(index)"
            :loading="loading"
            :copy-success-index="copySuccessIndex"
            :copy-run-success-index="copyRunSuccessIndex"
            @copy-message="(messageIndex, messageItem) => emit('copy-message', messageIndex, messageItem)"
            @copy-run="(messageIndex, messageItem) => emit('copy-run', messageIndex, messageItem)"
            @open-trace="emit('open-trace', $event)"
            @retry-answer="emit('retry-answer', $event)"
          />
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
            @click="emit('scroll-to-top')"
          >
            <el-icon><Top /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip v-if="showScrollToBottom" :content="pendingNewMessages ? t('chat.actions.newMessages', { count: pendingNewMessages }) : t('chat.actions.scrollToBottom')" placement="left">
          <button
            type="button"
            class="chat-scroll-button is-bottom"
            :aria-label="t('chat.actions.scrollToBottom')"
            @click="emit('scroll-to-bottom')"
          >
            <span v-if="pendingNewMessages" class="new-message-count">{{ pendingNewMessages }}</span>
            <el-icon><Bottom /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { Bottom, Cpu, Loading, Top } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import type { ParsedAssistantMessage } from "../../composables/useChatMarkdownRenderer"
import type { Message } from "../../types"
import ChatMessageCard from "./ChatMessageCard.vue"

defineProps<{
  messages: Message[]
  loading: boolean
  userAvatarLabel: string
  copySuccessIndex: number | null
  copyRunSuccessIndex: number | null
  pendingNewMessages: number
  showScrollToBottom: boolean
  showBackToTop: boolean
  assistantDisplayContent: (message: Message) => string
  parseAssistantMessage: (content: string) => ParsedAssistantMessage
  runMetaLine: (message: Message) => string
  hasUserPromptBefore: (index: number) => boolean
}>()

const emit = defineEmits<{
  scroll: []
  "scroll-to-top": []
  "scroll-to-bottom": []
  "copy-message": [index: number, message: Message]
  "copy-run": [index: number, message: Message]
  "open-trace": [message: Message]
  "retry-answer": [index: number]
}>()

const { t } = useI18n()
const chatContainer = ref<HTMLElement | null>(null)

defineExpose({ chatContainer })
</script>
