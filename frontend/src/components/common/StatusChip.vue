<template>
  <span :class="['ag-status-chip', toneClass]" :title="title">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(defineProps<{
  tone?: "blue" | "green" | "yellow" | "red" | "muted"
  title?: string
}>(), {
  tone: "muted",
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
