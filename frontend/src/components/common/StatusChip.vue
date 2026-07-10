<template>
  <el-tag
    class="ag-status-chip"
    :type="tagType"
    effect="light"
    size="small"
    :title="title"
    disable-transitions
  >
    <slot />
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(defineProps<{
  tone?: "blue" | "green" | "yellow" | "red" | "muted"
  title?: string
}>(), {
  tone: "muted",
})

const tagTypes = {
  blue: "primary",
  green: "success",
  yellow: "warning",
  red: "danger",
  muted: "info",
} as const

const tagType = computed(() => tagTypes[props.tone])
</script>

<style scoped>
.ag-status-chip {
  --el-tag-border-radius: var(--ag-radius-control);

  max-width: 100%;
  font-weight: 760;
}
</style>
