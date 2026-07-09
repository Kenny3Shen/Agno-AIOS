<template>
  <span :class="['ag-data-chip', toneClass]" :title="title || `${label}: ${value}`">
    <span class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[var(--ag-muted)]">{{ label }}</span>
    <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono font-760 text-[var(--ag-heading)]">
      {{ value }}
    </strong>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(defineProps<{
  label: string
  value: string | number
  tone?: "blue" | "green" | "yellow" | "red" | "muted"
  title?: string
}>(), {
  tone: "muted",
  title: "",
})

const toneClasses = {
  blue: "ag-status-blue",
  green: "ag-status-green",
  yellow: "ag-status-yellow",
  red: "ag-status-red",
  muted: "ag-status-muted",
} as const

const toneClass = computed(() => toneClasses[props.tone])
</script>
