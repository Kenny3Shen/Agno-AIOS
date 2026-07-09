<template>
  <header class="ag-section-header">
    <span class="grid min-w-0 gap-1">
      <span class="flex min-w-0 items-center gap-2">
        <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-760 text-[var(--ag-heading)]">
          {{ title }}
        </strong>
        <DataChip v-if="count !== undefined" :label="countLabel" :value="count" />
        <StatusDot v-if="statusLabel" :label="statusLabel" :tone="statusTone">
          {{ statusLabel }}
        </StatusDot>
      </span>
      <em v-if="subtitle" class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs not-italic text-[var(--ag-muted)]">
        {{ subtitle }}
      </em>
    </span>
    <span v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </span>
  </header>
</template>

<script setup lang="ts">
import DataChip from "./DataChip.vue"
import StatusDot from "./StatusDot.vue"

withDefaults(defineProps<{
  title: string
  subtitle?: string
  count?: string | number
  countLabel?: string
  statusLabel?: string
  statusTone?: "blue" | "green" | "yellow" | "red" | "muted"
}>(), {
  subtitle: "",
  count: undefined,
  countLabel: "Count",
  statusLabel: "",
  statusTone: "muted",
})
</script>
