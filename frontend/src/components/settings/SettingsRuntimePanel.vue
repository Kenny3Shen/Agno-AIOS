<template>
  <section class="ag-content-panel grid gap-3">
    <SectionHeader
      :title="t('settings.runtime.sectionTitle')"
      :subtitle="t('settings.runtime.sectionDescription')"
      :count="configItems.length"
      :count-label="t('settings.runtime.sectionTitle')"
    />

    <div class="grid gap-3 md:grid-cols-2">
      <article
        v-for="item in configItems"
        :key="item.key"
        class="grid gap-2 rounded-[var(--ag-radius-panel)] border border-[var(--ag-panel-border)] bg-[var(--ag-panel-bg)] p-3"
      >
        <div class="flex min-w-0 items-start justify-between gap-3">
          <label class="grid min-w-0 gap-1">
            <span class="text-[13px] font-700 text-[var(--ag-heading)]">
              {{ item.label }}<i v-if="item.required" class="required-mark" aria-hidden="true">*</i>
            </span>
            <span class="text-xs text-[var(--ag-muted)]">{{ item.description }}</span>
          </label>
          <DataChip class="max-w-[160px]" :label="t('settings.runtime.sectionTitle')" :value="item.key" :title="item.key" />
        </div>
        <el-input
          :model-value="formData[item.key]"
          :placeholder="item.placeholder"
          :type="item.secret ? 'password' : 'text'"
          :show-password="item.secret"
          :disabled="!canWriteSettings"
          clearable
          @update:model-value="emit('updateConfig', item.key, String($event ?? ''))"
        />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import SectionHeader from "../common/SectionHeader.vue"

export interface SettingsRuntimeConfigItem {
  key: string
  label: string
  description: string
  placeholder: string
  secret: boolean
  required: boolean
}

defineProps<{
  configItems: SettingsRuntimeConfigItem[]
  formData: Record<string, string>
  canWriteSettings: boolean
}>()

const emit = defineEmits<{
  updateConfig: [key: string, value: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.required-mark {
  margin-left: 3px;
  color: var(--ag-red);
  font-style: normal;
  font-weight: 800;
}
</style>
