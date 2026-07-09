<template>
  <footer class="agent-chat-footer p-3">
    <div class="chat-composer-frame">
      <div v-if="showQuickPrompts" class="mb-2 flex flex-wrap gap-2">
        <button
          v-for="prompt in quickPrompts"
          :key="prompt"
          type="button"
          class="quick-prompt cursor-pointer px-2.5 py-1.5 text-xs transition-colors duration-200"
          @click="emit('update:modelValue', prompt)"
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
            :model-value="modelValue"
            :placeholder="t('chat.composer.placeholder')"
            :disabled="loading"
            :autosize="{ minRows: 1, maxRows: 4 }"
            type="textarea"
            class="chat-input"
            @update:model-value="updateMessage"
            @keyup.enter.exact="emit('send')"
          />
          <ChatModelSelect
            :model-value="selectedModelId"
            :model-loading="modelLoading"
            :model-options="modelOptions"
            @update:model-value="emit('update:selectedModelId', $event)"
            @change="emit('model-change')"
          />
          <el-tooltip :content="t('chat.composer.send')" placement="top">
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!modelValue.trim() || loading || !selectedModelReady"
              class="send-button cursor-pointer"
              @click="emit('send')"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { Promotion } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import type { ModelConfig } from "../../types"
import ChatModelSelect from "./ChatModelSelect.vue"

defineProps<{
  modelValue: string
  selectedModelId: string | null
  modelLoading: boolean
  modelOptions: ModelConfig[]
  selectedModelReady: boolean
  loading: boolean
  quickPrompts: string[]
  showQuickPrompts: boolean
  modelConfigNotice: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: string]
  "update:selectedModelId": [value: string | null]
  "model-change": []
  send: []
}>()

const { t } = useI18n()

const updateMessage = (value: string | number) => {
  emit("update:modelValue", String(value))
}
</script>
