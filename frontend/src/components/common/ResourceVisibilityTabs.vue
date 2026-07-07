<template>
  <div
    class="resource-visibility-tabs"
    :class="{ 'is-disabled': disabled, 'is-loading': loading }"
    role="tablist"
    :aria-label="ariaLabel || t('visibility.label')"
  >
    <button
      v-for="option in resourceVisibilityOptions"
      :key="option.value"
      type="button"
      class="resource-visibility-tab"
      :class="{ 'is-active': modelValue === option.value }"
      role="tab"
      :aria-selected="modelValue === option.value"
      :disabled="disabled || loading"
      @click="selectVisibility(option.value)"
    >
      {{ t(option.labelKey) }}
    </button>
  </div>
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

const selectVisibility = (value: ResourceVisibility) => {
  if (props.disabled || props.loading || value === props.modelValue) return
  emit("update:modelValue", value)
  emit("change", value)
}
</script>

<style scoped>
.resource-visibility-tabs {
  display: inline-grid;
  grid-auto-columns: minmax(var(--visibility-tab-min-width, 58px), 1fr);
  grid-auto-flow: column;
  gap: 2px;
  width: fit-content;
  max-width: 100%;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  padding: 2px;
}

.resource-visibility-tab {
  min-height: var(--visibility-tab-height, 26px);
  border: 0;
  border-radius: calc(var(--ag-radius-control) - 2px);
  background: transparent;
  padding: var(--visibility-tab-padding, 4px 9px);
  color: var(--ag-muted);
  font-size: var(--visibility-tab-font-size, 11px);
  font-weight: 740;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.resource-visibility-tab:hover,
.resource-visibility-tab:focus-visible {
  color: var(--ag-heading);
}

.resource-visibility-tab:focus-visible {
  outline: 2px solid var(--ag-blue);
  outline-offset: 2px;
}

.resource-visibility-tab.is-active {
  background: color-mix(in srgb, var(--ag-blue) 18%, var(--ag-panel));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ag-blue) 46%, transparent);
  color: var(--ag-heading);
}

.resource-visibility-tabs.is-disabled,
.resource-visibility-tabs.is-loading {
  opacity: 0.62;
}

.resource-visibility-tab:disabled {
  cursor: not-allowed;
}
</style>
