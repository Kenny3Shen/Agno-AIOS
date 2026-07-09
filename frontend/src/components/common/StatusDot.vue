<template>
  <span class="inline-flex min-w-0 items-center gap-1.5">
    <span :class="['ag-status-dot', toneClass]" :aria-label="label" role="img" />
    <span v-if="$slots.default" class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted-strong)]">
      <slot />
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(defineProps<{
  label: string
  tone?: "blue" | "green" | "yellow" | "red" | "muted"
}>(), {
  tone: "muted",
})

const toneClasses = {
  blue: "bg-[var(--ag-blue)]",
  green: "bg-[var(--ag-green)]",
  yellow: "bg-[var(--ag-yellow)]",
  red: "bg-[var(--ag-red)]",
  muted: "bg-[var(--ag-muted)]",
} as const

const toneClass = computed(() => toneClasses[props.tone])
</script>
