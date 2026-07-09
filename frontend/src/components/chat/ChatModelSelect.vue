<template>
  <el-select
    :model-value="modelValue"
    :loading="modelLoading"
    :placeholder="t('chat.composer.modelPlaceholder')"
    class="agent-model-select"
    popper-class="agent-model-select-popper"
    placement="top-start"
    @update:model-value="updateModel"
    @change="emit('change')"
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
          :class="model.configured ? 'is-ready' : 'is-pending'"
        >
          {{ model.configured ? "Ready" : "Config" }}
        </span>
      </div>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { ModelConfig } from "../../types"

defineProps<{
  modelValue: string | null
  modelLoading: boolean
  modelOptions: ModelConfig[]
}>()

const emit = defineEmits<{
  "update:modelValue": [value: string | null]
  change: []
}>()

const { t } = useI18n()

const updateModel = (value: string | number | boolean | Record<string, unknown> | undefined) => {
  emit("update:modelValue", typeof value === "string" ? value : null)
}
</script>
