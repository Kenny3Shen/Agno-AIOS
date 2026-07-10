<template>
  <el-radio-group
    :model-value="modelValue"
    class="resource-visibility-tabs"
    :class="{ 'is-disabled': disabled, 'is-loading': loading }"
    :aria-label="ariaLabel || t('visibility.label')"
    :disabled="disabled || loading"
    size="small"
    @update:model-value="selectVisibility"
  >
    <el-radio-button
      v-for="option in resourceVisibilityOptions"
      :key="option.value"
      class="resource-visibility-tab"
      :value="option.value"
    >
      {{ t(option.labelKey) }}
    </el-radio-button>
  </el-radio-group>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { resourceVisibilityOptions } from "../../modules/resourceVisibility"
import type { ResourceVisibility } from "../../types"

const props = defineProps<{
  modelValue: ResourceVisibility
  ariaLabel?: string
  disabled?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  "update:modelValue": [value: ResourceVisibility]
  change: [value: ResourceVisibility]
}>()

const { t } = useI18n()

const selectVisibility = (value: string | number | boolean) => {
  const nextValue = String(value) as ResourceVisibility
  if (props.disabled || props.loading || nextValue === props.modelValue) return
  emit("update:modelValue", nextValue)
  emit("change", nextValue)
}
</script>

<style scoped>
.resource-visibility-tabs {
  max-width: 100%;
}

.resource-visibility-tabs :deep(.el-radio-button__inner) {
  min-height: var(--visibility-tab-height, 26px);
  min-width: var(--visibility-tab-min-width, 58px);
  border-radius: 0;
  padding: var(--visibility-tab-padding, 4px 9px);
  font-size: var(--visibility-tab-font-size, 11px);
  font-weight: 740;
}

.resource-visibility-tabs :deep(.el-radio-button:first-child .el-radio-button__inner) {
  border-radius: var(--ag-radius-control) 0 0 var(--ag-radius-control);
}

.resource-visibility-tabs :deep(.el-radio-button:last-child .el-radio-button__inner) {
  border-radius: 0 var(--ag-radius-control) var(--ag-radius-control) 0;
}

.resource-visibility-tabs :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: color-mix(in srgb, var(--ag-blue) 18%, var(--ag-panel));
  border-color: color-mix(in srgb, var(--ag-blue) 46%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ag-blue) 46%, transparent);
  color: var(--ag-heading);
}

.resource-visibility-tabs.is-disabled,
.resource-visibility-tabs.is-loading {
  opacity: 0.62;
}
</style>
