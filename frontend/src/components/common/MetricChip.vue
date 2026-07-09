<template>
  <span :class="['ag-metric-chip', toneClass]" :title="title || `${label}: ${value}`">
    <span class="ag-metric-label">{{ label }}</span>
    <strong class="ag-metric-value">{{ value }}</strong>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{
  label: string
  value: string | number
  tone?: "blue" | "green" | "yellow" | "red" | "muted"
  title?: string
}>()

const toneClasses = {
  blue: "ag-status-blue",
  green: "ag-status-green",
  yellow: "ag-status-yellow",
  red: "ag-status-red",
  muted: "",
} as const

const toneClass = computed(() => {
  return toneClasses[props.tone || "muted"]
})
</script>
