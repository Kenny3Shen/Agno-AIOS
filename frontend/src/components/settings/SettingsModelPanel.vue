<template>
  <section class="ag-content-panel grid gap-3">
    <SectionHeader
      class="flex-wrap"
      :title="t('settings.models.sectionTitle')"
      :subtitle="t('settings.models.sectionDescription')"
      :count="models.length"
      :count-label="t('settings.models.sectionTitle')"
    >
      <template #actions>
        <div class="ag-settings-model-actions flex w-full flex-col justify-end gap-2 sm:w-auto sm:flex-row">
          <el-select
            :model-value="activeModelId"
            class="w-[240px] max-w-full"
            :disabled="!canWriteSettings"
            :placeholder="t('settings.models.defaultPlaceholder')"
            @update:model-value="emit('update:activeModelId', String($event ?? ''))"
          >
            <el-option
              v-for="model in enabledModels"
              :key="model.id"
              :label="model.name"
              :value="model.id"
            />
          </el-select>
          <el-button
            class="w-[240px] max-w-full cursor-pointer sm:w-auto"
            :disabled="!canWriteSettings"
            :icon="Plus"
            @click="emit('addModel')"
          >
            {{ t('settings.actions.addModel') }}
          </el-button>
        </div>
      </template>
    </SectionHeader>

    <div class="grid gap-3">
      <article
        v-for="(model, index) in models"
        :key="model.id"
        class="grid gap-3 rounded-[var(--ag-radius-panel)] border border-[var(--ag-panel-border)] bg-[var(--ag-panel-bg)] p-3"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex min-w-0 items-center gap-3">
            <DataChip :label="t('settings.models.modelIdLabel')" :value="index + 1" />
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h5 class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-sm font-700 text-[var(--ag-heading)]">
                  {{ model.name || t('settings.models.unnamed') }}
                </h5>
                <DataChip
                  v-if="model.builtin"
                  :label="t('settings.models.builtin')"
                  :value="model.id"
                  :title="model.id"
                />
                <StatusDot
                  :label="isConfigured(model) ? t('common.status.ready') : t('settings.models.unconfigured')"
                  :tone="isConfigured(model) ? 'green' : 'yellow'"
                >
                  {{ isConfigured(model) ? t('common.status.ready') : t('settings.models.unconfigured') }}
                </StatusDot>
                <StatusDot
                  v-if="activeModelId === model.id"
                  :label="t('settings.models.defaultBadge')"
                  tone="blue"
                >
                  {{ t('settings.models.defaultBadge') }}
                </StatusDot>
              </div>
              <p class="mt-1 text-xs text-[var(--ag-muted)]">
                {{ model.description || t('settings.models.customDescription') }}
              </p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <el-button
              plain
              size="small"
              class="cursor-pointer"
              :icon="Connection"
              :loading="testingModelId === model.id"
              :disabled="!canWriteSettings || !hasRequiredModelFields(model)"
              @click="emit('testModel', model)"
            >
              {{ t('settings.actions.testConnection') }}
            </el-button>
            <el-switch
              :model-value="model.enabled"
              inline-prompt
              :disabled="!canWriteSettings"
              :active-text="t('settings.models.enabled')"
              :inactive-text="t('settings.models.disabled')"
              @update:model-value="emit('updateModelField', model.id, 'enabled', Boolean($event))"
            />
            <el-button
              v-if="!model.builtin"
              text
              type="danger"
              class="cursor-pointer"
              :disabled="!canWriteSettings"
              :icon="Delete"
              @click="emit('removeModel', model.id)"
            />
          </div>
        </div>

        <div class="grid gap-3 lg:grid-cols-2">
          <label class="grid gap-1.5">
            <span class="text-xs font-650 text-[var(--ag-muted)]">
              {{ t('settings.models.displayName') }}<i class="required-mark" aria-hidden="true">*</i>
            </span>
            <el-input
              :model-value="model.name"
              :disabled="!canWriteSettings"
              :placeholder="t('settings.models.displayNamePlaceholder')"
              @update:model-value="emit('updateModelField', model.id, 'name', String($event ?? ''))"
            />
          </label>
          <label class="grid gap-1.5">
            <span class="text-xs font-650 text-[var(--ag-muted)]">
              {{ t('settings.models.modelIdLabel') }}<i class="required-mark" aria-hidden="true">*</i>
            </span>
            <el-input
              :model-value="model.model_id"
              :disabled="!canWriteSettings"
              :placeholder="t('settings.models.modelIdPlaceholder')"
              @update:model-value="emit('updateModelField', model.id, 'model_id', String($event ?? ''))"
            />
          </label>
          <label class="grid gap-1.5">
            <span class="text-xs font-650 text-[var(--ag-muted)]">
              {{ t('settings.models.baseUrlLabel') }}<i class="required-mark" aria-hidden="true">*</i>
            </span>
            <el-input
              :model-value="model.base_url"
              :disabled="!canWriteSettings"
              :placeholder="t('settings.models.baseUrlPlaceholder')"
              @update:model-value="emit('updateModelField', model.id, 'base_url', String($event ?? ''))"
            />
          </label>
          <label class="grid gap-1.5">
            <span class="text-xs font-650 text-[var(--ag-muted)]">
              {{ t('settings.models.apiKeyLabel') }}<i class="required-mark" aria-hidden="true">*</i>
            </span>
            <el-input
              :model-value="model.api_key"
              :placeholder="t('settings.models.apiKeyPlaceholder')"
              :disabled="!canWriteSettings"
              type="password"
              show-password
              @update:model-value="emit('updateModelField', model.id, 'api_key', String($event ?? ''))"
            />
          </label>
          <label class="grid gap-1.5 lg:col-span-2">
            <span class="text-xs font-650 text-[var(--ag-muted)]">{{ t('settings.models.descriptionLabel') }}</span>
            <el-input
              :model-value="model.description"
              :disabled="!canWriteSettings"
              :placeholder="t('settings.models.descriptionPlaceholder')"
              @update:model-value="emit('updateModelField', model.id, 'description', String($event ?? ''))"
            />
          </label>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { Connection, Delete, Plus } from "@element-plus/icons-vue"
import DataChip from "../common/DataChip.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusDot from "../common/StatusDot.vue"
import type { ModelConfig } from "../../types"

type EditableModelField = "name" | "model_id" | "base_url" | "api_key" | "description" | "enabled"

const props = defineProps<{
  models: ModelConfig[]
  activeModelId: string
  testingModelId: string | null
  canWriteSettings: boolean
}>()

const emit = defineEmits<{
  "update:activeModelId": [value: string]
  addModel: []
  removeModel: [modelId: string]
  testModel: [model: ModelConfig]
  updateModelField: [modelId: string, key: EditableModelField, value: string | boolean]
}>()

const { t } = useI18n()

const enabledModels = computed(() => props.models.filter((model) => model.enabled))

const hasRequiredModelFields = (model: ModelConfig) => {
  return Boolean(
    model.name.trim()
    && model.api_key.trim()
    && model.base_url.trim()
    && model.model_id.trim()
  )
}

const isConfigured = (model: ModelConfig) => {
  return Boolean(model.api_key.trim() && model.base_url.trim() && model.model_id.trim())
}
</script>

<style scoped>
.required-mark {
  margin-left: 3px;
  color: var(--ag-red);
  font-style: normal;
  font-weight: 800;
}
</style>
